import asyncio
import json
import re
import time
import ast
from typing import Optional, List

from mini_nebulus.config import Config
from mini_nebulus.models.history import HistoryManager
from mini_nebulus.models.task import TaskStatus
from mini_nebulus.services.openai_service import OpenAIService
from mini_nebulus.services.tool_executor import ToolExecutor
from mini_nebulus.services.file_service import FileService
from mini_nebulus.views.base_view import BaseView
from mini_nebulus.views.cli_view import CLIView
from mini_nebulus.utils.logger import setup_logger

logger = setup_logger(__name__)


class AgentController:
    def __init__(self, view: Optional[BaseView] = None):
        logger.info("Initializing AgentController")
        ToolExecutor.initialize()

        self.auto_mode = False

        self.context_loaded = False
        try:
            context_content = FileService.read_file("CONTEXT.md")
            self.context_loaded = True
        except Exception:
            context_content = "Context file not found."

        system_prompt = (
            "You are Mini-Nebulus, an autonomous AI engineer. You have full system access.\n"
            "Your ONLY goal is to execute tasks. NEVER explain what you are going to do.\n"
            "NEVER use markdown code blocks like ```python unless you are calling a tool.\n"
            "ALWAYS use tools to perform actions.\n\n"
            "### AUTONOMY RULES ###\n"
            "1. You are AUTONOMOUS. Do NOT ask the user for input (e.g., via ask_user) to define tasks or plans.\n"
            "2. Infer the goal and task description yourself based on the user's initial prompt and the current context.\n"
            "3. Only use ask_user if there is a critical ambiguity that completely stops you from proceeding.\n"
            "4. If you have executed the user's request, STOP immediately. Do NOT create plans, add tasks, write files, or pin files.\n"
            "5. Do NOT hallucinate that you need to implement features just because you see them in the context files.\n"
            "### AUTONOMY RULES ###\n"
            "1. You are AUTONOMOUS. Do NOT ask the user for input (e.g., via ask_user) to define tasks or plans.\n"
            "2. Infer the goal and task description yourself based on the user's initial prompt and the current context.\n"
            "3. Only use ask_user if there is a critical ambiguity that completely stops you from proceeding.\n"
            "4. If you have executed the user's request, STOP immediately. Do NOT create plans, add tasks, write files, or pin files.\n"
            "5. Do NOT hallucinate that you need to implement features just because you see them in the context files.\n"
            "6. Simple requests (like 'list files', 'read file', 'check size') do NOT require `create_plan` or `add_task`. Just run the command and stop.\n"
            "7. Do NOT try to `update_task` if you haven't created a plan first. If there is no plan, there are no tasks to update.\n"
            "8. Do NOT create a plan AFTER doing the work just to mark it as done. If the work is done, you are done.\n"
            "9. Do NOT pin files or read files 'just to check' or 'get context' unless the user asked you to analyze those specific files.\n"
            "10. If the request is 'search for X', run `search_code` and then report the results based on the tool output. Do NOT read the source files to 'verify' unless explicitly asked.\n\n"
            "### TOOL USAGE RULES ###\n"
            "1. You MUST ONLY use the tools provided in the `tools` list. Do NOT invent new tools (e.g., 'find_file' does NOT exist).\n"
            "2. To list files, use `run_shell_command` with `ls` or `FileService.list_dir` if available.\n\n"
            "### HOW TO CALL TOOLS ###\n"
            "To perform an action, output ONLY a JSON tool call using DOUBLE QUOTES.\n"
            'Example: {"name": "write_file", "arguments": {"path": "test.py", "content": "print(\'hi\')"}}\n\n'
            "To call multiple tools, use a list:\n"
            '[{"name": "tool1", ...}, {"name": "tool2", ...}]\n\n'
            "### PROJECT CONTEXT ###\n"
            f"{context_content}"
        )

        self.history_manager = HistoryManager(system_prompt)
        self.openai = OpenAIService()
        self.view = view if view else CLIView()
        self.base_tools = [
            {
                "type": "function",
                "function": {
                    "name": "connect_mcp_server",
                    "description": "Connects to an MCP server via stdio.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "command": {"type": "string"},
                            "args": {"type": "array", "items": {"type": "string"}},
                            "env": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                        },
                        "required": ["name", "command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_shell_command",
                    "description": "Executes a shell command.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Reads a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Writes content to a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_plan",
                    "description": "Initialize a plan.",
                    "parameters": {
                        "type": "object",
                        "properties": {"goal": {"type": "string"}},
                        "required": ["goal"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_task",
                    "description": "Add a task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "dependencies": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["description"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_task",
                    "description": "Update task status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string"},
                            "status": {"type": "string"},
                            "result": {"type": "string"},
                        },
                        "required": ["task_id", "status"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_plan",
                    "description": "Start autonomous execution of the current plan.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_preference",
                    "description": "Set a user preference.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["key", "value"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_preference",
                    "description": "Get a user preference.",
                    "parameters": {
                        "type": "object",
                        "properties": {"key": {"type": "string"}},
                        "required": ["key"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_docs",
                    "description": "List available documentation files.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_doc",
                    "description": "Read a documentation file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_skill",
                    "description": "Create a new skill.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "code": {"type": "string"},
                        },
                        "required": ["name", "code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "pin_file",
                    "description": "Pin a file to the active context.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "unpin_file",
                    "description": "Unpin a file from the active context.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_context",
                    "description": "List currently pinned files.",
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
                    "name": "ask_user",
                    "description": "Ask the user for clarification or input.",
                    "parameters": {
                        "type": "object",
                        "properties": {"question": {"type": "string"}},
                        "required": ["question"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_checkpoint",
                    "description": "Create a file system checkpoint (backup).",
                    "parameters": {
                        "type": "object",
                        "properties": {"label": {"type": "string"}},
                        "required": ["label"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "rollback_checkpoint",
                    "description": "Restore files from a checkpoint.",
                    "parameters": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                        "required": ["id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_checkpoints",
                    "description": "List available checkpoints.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "publish_skill",
                    "description": "Publish a local skill to the global library.",
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "index_codebase",
                    "description": "Index the codebase for semantic search.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_history",
                    "description": "Search the command history using a natural language query.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_code",
                    "description": "Search the codebase using a natural language query.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
        ]

    async def start(self, initial_prompt: Optional[str] = None):
        await self.view.print_welcome()
        if isinstance(self.view, CLIView):
            if self.context_loaded:
                self.view.console.print("✔ Loaded @CONTEXT.md", style="dim green")
                self.view.console.print(
                    "  • Adhering to AI Directives & MVC", style="dim green"
                )

        session_id = "default"
        if initial_prompt:
            self.history_manager.get_session(session_id).add("user", initial_prompt)
            if hasattr(self.view, "start_app"):
                asyncio.create_task(self.process_turn(session_id))
            else:
                await self.process_turn(session_id)

        # Check if we are using TUI
        if hasattr(self.view, "start_app"):
            # In TUI mode, we hand over control to the View's event loop
            await self.view.start_app()
        else:
            # CLI mode uses the standard loop
            await self.chat_loop(session_id)

    async def handle_tui_input(self, user_input: str, session_id: str = "default"):
        """Callback for TUI to push input to the controller."""
        if user_input.lower() in Config.EXIT_COMMANDS:
            await self.view.print_goodbye()
            return

        self.history_manager.get_session(session_id).add("user", user_input)
        asyncio.create_task(self.process_turn(session_id))

    async def chat_loop(self, session_id: str = "default"):
        while True:
            try:
                if self.auto_mode:
                    # Autonomous Logic
                    task_service = ToolExecutor.task_manager.get_service(session_id)
                    plan = task_service.current_plan

                    if not plan:
                        self.auto_mode = False
                        if isinstance(self.view, CLIView):
                            self.view.console.print(
                                "No active plan. Stopping auto-execution.",
                                style="bold red",
                            )
                        continue

                    # Find next PENDING task
                    next_task = None
                    for task in plan.tasks:
                        if task.status == TaskStatus.PENDING:
                            next_task = task
                            break

                    if next_task:
                        if isinstance(self.view, CLIView):
                            self.view.console.print(
                                f"🤖 Auto-Executing Task: {next_task.description}",
                                style="bold cyan",
                            )

                        # Update status to IN_PROGRESS
                        task_service.update_task_status(
                            next_task.id, TaskStatus.IN_PROGRESS
                        )

                        # Formulate prompt
                        user_input = (
                            f"Execute this task: {next_task.description}. "
                            "Mark it as COMPLETED when done."
                        )

                        self.history_manager.get_session(session_id).add(
                            "user", user_input
                        )
                        await self.process_turn(session_id)

                        # Check if task was completed by the agent
                        updated_task = task_service.get_task(next_task.id)
                        if updated_task.status != TaskStatus.COMPLETED:
                            # If task failed or wasn't completed, stop auto-execution for safety
                            if updated_task.status == TaskStatus.FAILED:
                                self.auto_mode = False
                                if isinstance(self.view, CLIView):
                                    self.view.console.print(
                                        "Task failed. Stopping auto-execution.",
                                        style="bold red",
                                    )
                    else:
                        self.auto_mode = False
                        if isinstance(self.view, CLIView):
                            self.view.console.print(
                                "All tasks completed. Stopping auto-execution.",
                                style="bold green",
                            )
                        continue

                else:
                    user_input = await self.view.prompt_user()
                    if not user_input.strip():
                        if isinstance(self.view, CLIView):
                            continue
                        else:
                            break
                    if user_input.lower() in Config.EXIT_COMMANDS:
                        await self.view.print_goodbye()
                        break
                    self.history_manager.get_session(session_id).add("user", user_input)
                    await self.process_turn(session_id)

            except (KeyboardInterrupt, EOFError):
                await self.view.print_goodbye()
                break
                if user_input.lower() in Config.EXIT_COMMANDS:
                    await self.view.print_goodbye()
                    break
                self.history_manager.get_session(session_id).add("user", user_input)
                await self.process_turn(session_id)
            except (KeyboardInterrupt, EOFError):
                await self.view.print_goodbye()
                break

    def extract_json(self, text: str) -> List[dict]:
        text = re.sub(r"<\|.*?\|>", "", text).strip()
        results = []

        def find_json_objects(s: str):
            stack = []
            start = -1
            for i, char in enumerate(s):
                if char == "{":
                    if not stack:
                        start = i
                    stack.append("{")
                elif char == "}":
                    if stack:
                        stack.pop()
                        if not stack:
                            yield s[start : i + 1]
                elif char == "[":
                    if not stack:
                        start = i
                    stack.append("[")
                elif char == "]":
                    if stack:
                        stack.pop()
                        if not stack:
                            yield s[start : i + 1]

        for cand in find_json_objects(text):
            try:
                # Try standard JSON first
                obj = json.loads(cand)
            except json.JSONDecodeError:
                try:
                    # Fallback to Python literal eval (handles single quotes)
                    obj = ast.literal_eval(cand)
                except Exception:
                    continue

            if isinstance(obj, list):
                results.extend(
                    [
                        o
                        for o in obj
                        if isinstance(o, dict) and ("name" in o or "command" in o)
                    ]
                )
            elif isinstance(obj, dict):
                if "name" in obj or "command" in obj:
                    results.append(obj)

        return results

    def get_current_tools(self):
        """Merges base tools, dynamic skills, and MCP tools."""
        skill_defs = ToolExecutor.skill_service.get_tool_definitions()
        mcp_defs = ToolExecutor.mcp_service.get_tools()
        return self.base_tools + skill_defs + mcp_defs

    async def process_turn(self, session_id: str = "default"):
        finished_turn = False
        history = self.history_manager.get_session(session_id)
        logger.info(f"Processing turn for session {session_id}")

        # Inject Pinned Context dynamically into each turn
        context_service = ToolExecutor.context_manager.get_service(session_id)
        rag_service = ToolExecutor.rag_manager.get_service(session_id)
        preference_service = ToolExecutor.preference_manager.get_service(session_id)
        pinned_content = context_service.get_context_string()
        pinned_content += preference_service.get_context_string()

        # Update TUI Context View
        if hasattr(self.view, "print_context"):
            # Assuming list_context returns a list of strings
            context_list = context_service.list_context()
            if isinstance(context_list, list):
                await self.view.print_context(context_list)

        messages = history.get()
        # Index the last user message
        last_msg = messages[-1] if messages else None
        if last_msg and last_msg["role"] == "user":
            rag_service.index_history("user", last_msg["content"], session_id)

        if pinned_content:
            messages = [m.copy() for m in messages]
            messages.append({"role": "system", "content": pinned_content})

        while not finished_turn:
            current_tools = self.get_current_tools()
            with self.view.create_spinner("Thinking..."):
                try:
                    response_stream = self.openai.create_chat_completion(
                        messages, current_tools
                    )
                    full_response = ""
                    tool_calls = []
                    tool_calls_map = {}
                    async for chunk in response_stream:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        if delta.content:
                            full_response += delta.content
                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                if tc.index not in tool_calls_map:
                                    tool_calls_map[tc.index] = {
                                        "id": tc.id or f"call_{int(time.time())}",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                if tc.function.name:
                                    tool_calls_map[tc.index]["function"][
                                        "name"
                                    ] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_map[tc.index]["function"][
                                        "arguments"
                                    ] += tc.function.arguments

                    tool_calls = list(tool_calls_map.values())

                    if not tool_calls:
                        extracted_list = self.extract_json(full_response)
                        if extracted_list:
                            for i, extracted in enumerate(extracted_list):
                                args = extracted.get("arguments", extracted)
                                if (
                                    extracted.get("command")
                                    and "arguments" not in extracted
                                ):
                                    args = extracted

                                tool_name = extracted.get("name", "run_shell_command")
                                tool_calls.append(
                                    {
                                        "id": f"manual_{int(time.time())}_{i}",
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": json.dumps(args)
                                            if isinstance(args, dict)
                                            else args,
                                        },
                                    }
                                )
                            full_response = ""

                    if tool_calls:
                        history.add(
                            "assistant",
                            content=full_response.strip() or None,
                            tool_calls=tool_calls,
                        )
                        if full_response.strip():
                            await self.view.print_agent_response(full_response)

                        for tc in tool_calls:
                            name = tc["function"]["name"]
                            args_str = tc["function"]["arguments"]
                            try:
                                args = (
                                    json.loads(args_str)
                                    if isinstance(args_str, str)
                                    else args_str
                                )
                            except Exception as e:
                                output_str = f"Error parsing JSON arguments: {str(e)}"
                                history.add(
                                    "tool", content=output_str, tool_call_id=tc["id"]
                                )
                                continue

                            if name == "ask_user":
                                question = args.get("question", "")
                                if question:
                                    output = await self.view.ask_user_input(question)
                                else:
                                    output = "Error: No question provided."
                            elif name == "execute_plan":
                                self.auto_mode = True
                                output = "Autonomous execution started. I will now proceed to execute tasks one by one."
                                finished_turn = True
                            else:
                                with self.view.create_spinner(f"Executing {name}"):
                                    output = await ToolExecutor.dispatch(
                                        name, args, session_id=session_id
                                    )
                            if isinstance(self.view, CLIView):
                                self.view.console.print(
                                    f"✔ Executed: {name}", style="dim green"
                                )
                            if isinstance(output, dict):
                                await self.view.print_plan(output)
                                output_str = json.dumps(output)
                            else:
                                output_str = str(output)
                                await self.view.print_tool_output(
                                    output_str, tool_name=name
                                )

                            history.add(
                                "tool", content=output_str, tool_call_id=tc["id"]
                            )
                    else:
                        if full_response.strip():
                            full_response = re.sub(
                                r"<\|.*?\|>", "", full_response
                            ).strip()
                            if full_response:
                                await self.view.print_agent_response(full_response)
                                await self.view.print_telemetry(
                                    getattr(self.openai, "last_telemetry", {})
                                )
                                history.add("assistant", full_response)
                            rag_service.index_history(
                                "assistant", full_response, session_id
                            )
                        finished_turn = True
                except Exception as e:
                    logger.error(f"Error in process_turn: {str(e)}", exc_info=True)
                    await self.view.print_error(str(e))
                    finished_turn = True
