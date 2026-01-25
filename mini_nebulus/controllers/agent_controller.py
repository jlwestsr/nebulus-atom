import json
import re
import time
from typing import Optional

from mini_nebulus.config import Config
from mini_nebulus.models.history import HistoryManager
from mini_nebulus.services.openai_service import OpenAIService
from mini_nebulus.services.tool_executor import ToolExecutor
from mini_nebulus.services.input_preprocessor import InputPreprocessor
from mini_nebulus.services.file_service import FileService
from mini_nebulus.views.base_view import BaseView
from mini_nebulus.views.cli_view import CLIView


class AgentController:
    def __init__(self, view: Optional[BaseView] = None):
        # Initialize skills
        ToolExecutor.initialize()

        # Load Project Context
        try:
            context_content = FileService.read_file("CONTEXT.md")
        except Exception:
            context_content = "Context file not found. Proceed with caution."

        system_prompt = (
            "You are Mini-Nebulus, a strictly autonomous AI engineer CLI. You have full access to the local system. "
            "Your goal is to COMPLETE tasks yourself. NEVER suggest manual steps to the user. "
            "NEVER ask for permission to execute a tool. "
            "You can CREATE your own tools using 'create_skill' if you need a specific capability (e.g., complex calculation, data processing). "
            "When given a goal: \n"
            "1. Call 'create_plan' immediately.\n"
            "2. Call 'add_task' for each required step.\n"
            "3. Execute steps sequentially using 'run_shell_command', 'write_file', or your own skills.\n"
            "4. Update task status with 'update_task' AFTER each step.\n"
            "5. Continue until the entire plan is COMPLETED.\n"
            "DO NOT stop until the mission is finished. DO NOT wrap tool calls in text.\n\n"
            "### PROJECT CONTEXT AND RULES ###\n"
            f"{context_content}"
        )

        self.history_manager = HistoryManager(system_prompt)
        self.openai = OpenAIService()
        self.view = view if view else CLIView()
        self.base_tools = [
            {
                "type": "function",
                "function": {
                    "name": "run_shell_command",
                    "description": "Executes a shell command on the local machine.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute.",
                            }
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Reads the content of a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file.",
                            }
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Writes content to a file. Overwrites if exists.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file.",
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write.",
                            },
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_dir",
                    "description": "Lists files in a directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path (default .).",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_plan",
                    "description": "Initialize a new plan with a goal.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "goal": {
                                "type": "string",
                                "description": "The overall goal.",
                            }
                        },
                        "required": ["goal"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_task",
                    "description": "Add a task to the current plan.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Task description.",
                            }
                        },
                        "required": ["description"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_task",
                    "description": "Update the status of a task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "The ID of the task.",
                            },
                            "status": {
                                "type": "string",
                                "description": "One of: PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED",
                            },
                            "result": {
                                "type": "string",
                                "description": "Optional result or error message.",
                            },
                        },
                        "required": ["task_id", "status"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_plan",
                    "description": "Get the current plan status.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_skill",
                    "description": "Create a new Python skill (tool). The code must be a valid python module containing a function.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name of the skill module (e.g., 'calculator').",
                            },
                            "code": {
                                "type": "string",
                                "description": "Python code defining the function.",
                            },
                        },
                        "required": ["name", "code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "refresh_skills",
                    "description": "Reloads all skills from the skills directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ]

    async def start(self, initial_prompt: Optional[str] = None):
        self.view.print_welcome()

        session_id = "default"

        if initial_prompt:
            processed = InputPreprocessor.process(initial_prompt)
            history = self.history_manager.get_session(session_id)
            history.add("user", processed)

            # Only print for CLI view - now strictly for CLIView instance check
            if isinstance(self.view, CLIView):
                self.view.console.print(f"[user]You:[/user] {initial_prompt}")

            await self.process_turn(session_id)

        await self.chat_loop(session_id)

    async def chat_loop(self, session_id: str = "default"):
        while True:
            try:
                user_input = self.view.prompt_user()
                if not user_input.strip():
                    # If prompt_user returns empty (like in DiscordView), break loop
                    if isinstance(self.view, CLIView):
                        continue
                    else:
                        break

                if user_input.lower() in Config.EXIT_COMMANDS:
                    self.view.print_goodbye()
                    break

                processed = InputPreprocessor.process(user_input)
                history = self.history_manager.get_session(session_id)
                history.add("user", processed)

                await self.process_turn(session_id)
            except (KeyboardInterrupt, EOFError):
                self.view.print_goodbye()
                break

    def extract_json(self, text: str) -> Optional[dict]:
        text = re.sub(r"<\|.*?\|>", "", text).strip()
        clean = re.sub(r"```\w*\n?", "", text)
        clean = re.sub(r"```$", "", clean).strip()

        if clean.startswith("{") and clean.endswith("}"):
            try:
                return json.loads(clean)
            except json.JSONDecodeError:
                pass

        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            try:
                cand = match.group(1)
                obj = json.loads(cand)
                if "name" in obj or "command" in obj:
                    return obj
            except json.JSONDecodeError:
                pass

        return None

    def get_current_tools(self):
        """Merges base tools with dynamically loaded skills."""
        skill_defs = ToolExecutor.skill_service.get_tool_definitions()
        return self.base_tools + skill_defs

    async def process_turn(self, session_id: str = "default"):
        finished_turn = False
        history = self.history_manager.get_session(session_id)

        while not finished_turn:
            tool_calls = []
            full_response = ""

            current_tools = self.get_current_tools()

            with self.view.create_spinner("Thinking..."):
                try:
                    response_stream = self.openai.create_chat_completion(
                        history.get(), current_tools
                    )

                    tool_calls_map = {}

                    for chunk in response_stream:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            full_response += delta.content

                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                if tc.index not in tool_calls_map:
                                    tool_calls_map[tc.index] = {
                                        "index": tc.index,
                                        "id": tc.id
                                        or f"call_{int(time.time())}_{tc.index}",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                if tc.id:
                                    tool_calls_map[tc.index]["id"] = tc.id
                                if tc.function and tc.function.name:
                                    tool_calls_map[tc.index]["function"][
                                        "name"
                                    ] += tc.function.name
                                if tc.function and tc.function.arguments:
                                    tool_calls_map[tc.index]["function"][
                                        "arguments"
                                    ] += tc.function.arguments

                    tool_calls = list(tool_calls_map.values())

                    # Heuristic extraction fallback
                    if not tool_calls:
                        extracted = self.extract_json(full_response)
                        if extracted:
                            args = extracted.get("arguments", extracted)
                            if (
                                extracted.get("command")
                                and "arguments" not in extracted
                            ):
                                args = extracted

                            tool_name = extracted.get("name", "run_shell_command")
                            tool_calls = [
                                {
                                    "id": f"call_manual_{int(time.time())}",
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(args)
                                        if isinstance(args, dict)
                                        else args,
                                    },
                                }
                            ]
                            if len(full_response) < 300:
                                full_response = ""

                    if tool_calls:
                        unique_tool_calls = []
                        seen_calls = set()
                        for tc in tool_calls:
                            key = f"{tc['function']['name']}:{tc['function']['arguments']}"
                            if key not in seen_calls:
                                seen_calls.add(key)
                                unique_tool_calls.append(tc)

                        tool_calls = unique_tool_calls

                        history.add(
                            "assistant",
                            content=full_response.strip() or None,
                            tool_calls=tool_calls,
                        )
                        await self.view.print_agent_response(full_response)
                    else:
                        if full_response.strip():
                            full_response = re.sub(
                                r"<\|.*?\|>", "", full_response
                            ).strip()
                            if full_response:
                                await self.view.print_agent_response(full_response)
                                history.add("assistant", full_response)
                        finished_turn = True

                except Exception as e:
                    await self.view.print_error(str(e))
                    finished_turn = True
                    return

            # Tool execution phase
            if tool_calls:
                for tc in tool_calls:
                    try:
                        args_str = tc["function"]["arguments"]
                        args = (
                            json.loads(args_str)
                            if isinstance(args_str, str)
                            else args_str
                        )
                        tool_name = tc["function"]["name"]

                        with self.view.create_spinner(f"Executing: {tool_name}"):
                            output = await ToolExecutor.dispatch(
                                tool_name, args, session_id=session_id
                            )

                        # Check if running in CLI mode for rich console printing
                        if isinstance(self.view, CLIView):
                            self.view.console.print(
                                f"✔ Executed: {tool_name}", style="dim green"
                            )

                        if isinstance(output, dict) and tool_name == "get_plan":
                            await self.view.print_plan(output)
                            output_str = json.dumps(output)
                        else:
                            output_str = str(output)
                            await self.view.print_tool_output(
                                output_str, tool_name=tool_name
                            )

                    except Exception as e:
                        output_str = f"Error: {str(e)}"
                        if isinstance(self.view, CLIView):
                            self.view.console.print(
                                f"✖ Failed: {str(e)}", style="bold red"
                            )
                        else:
                            await self.view.print_error(output_str)

                    history.add("tool", content=output_str, tool_call_id=tc["id"])
            else:
                finished_turn = True
