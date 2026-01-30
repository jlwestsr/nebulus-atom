import asyncio
import json
import re
import time
import ast
from typing import Optional, List

from nebulus_atom.config import Config
from nebulus_atom.models.history import HistoryManager
from nebulus_atom.models.task import TaskStatus
from nebulus_atom.services.openai_service import OpenAIService
from nebulus_atom.services.tool_executor import ToolExecutor
from nebulus_atom.views.base_view import BaseView
from nebulus_atom.views.cli_view import CLIView
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class AgentController:
    def __init__(self, view: Optional[BaseView] = None):
        logger.info("Initializing AgentController")
        ToolExecutor.initialize()

        self.auto_mode = False

        self.context_loaded = False
        try:
            # Context disabled to prevent overflow on local backends
            context_content = ""
            self.context_loaded = True
        except Exception:
            context_content = "Context file not found."

        self.base_tools = [
            {
                "type": "function",
                "function": {
                    "name": "run_shell_command",
                    "description": "Run shell cmd.",
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
                    "description": "Read file.",
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
                    "description": "Write file.",
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
                    "description": "Init plan.",
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
                    "name": "execute_plan",
                    "description": "Auto-execute plan.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_context",
                    "description": "List pinned files.",
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
                    "name": "pin_file",
                    "description": "Pin file.",
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
                    "name": "search_memory",
                    "description": "Search past conversation history.",
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
                    "name": "search_knowledge",
                    "description": "Search indexed codebase.",
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
                    "name": "create_skill",
                    "description": "Create a reusable Python skill (tool). The code must define a function.",
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
        ]

        self.pending_tdd_goal = None
        system_prompt = (
            "Your ONLY goal is to execute tasks. NEVER explain what you are going to do.\n"
            "NEVER use markdown code blocks like ```python unless you are calling a tool.\n"
            "ALWAYS use tools to perform actions.\n\n"
            "### PROJECT PROTOCOL (STRICT COMPLIANCE) ###\n"
            "1. **Architecture**: Python MVC. Models=DataClasses/Pydantic. Config=`config.py`. Services=Integrations.\n"
            "2. **Workflow**: Gitflow-lite. Work on `feat/<name>` or `develop`. `main` is production.\n"
            "3. **Coding**: Python 3.12+, Type Hints, AsyncIO, SOLID Principles.\n"
            "4. **Autonomy**: Execute tasks immediately. Use JSON tools. No `ask_user` unless blocked.\n"
            "5. **Context Strategy**: These rules are PRE-LOADED. Do NOT read `AI_DIRECTIVES.md`, `WORKFLOW.md`, `CONTEXT.md` unless verifying a specific line.\n\n"
            "### AUTONOMY RULES ###\n"
            "1. **INITIAL STATE**: You are IDLE. Wait for the user to provide a specific goal. Do NOT auto-start tasks.\n"
            "2. Infer goals ONLY from the user's prompt (e.g., 'Do X').\n"
            "3. **ONE SHOT RULE**: Once you have completed the user's explicit request (e.g., listed files), STOP. Do NOT perform any follow-up actions (like reading files, searching memory) unless explicitly asked.\n"
            "3. Use tools to perform actions. Output ONLY valid JSON.\n"
            "4. Do NOT hallucinate features. Stick to the request. Do NOT demonstrate features (like Context Manager) unless asked.\n"
            "5. **CRITICAL**: Do NOT read general documentation files. Trust the 'PROJECT PROTOCOL' above.\n\n"
            "### TOOL USAGE RULES ###\n"
            "1. You MUST ONLY use the provided tools. Do NOT invent new tools.\n"
            "2. To list files, use `run_shell_command` with `ls`.\n\n"
            "### HOW TO CALL TOOLS ###\n"
            "Output ONLY a raw JSON object (no markdown, no code blocks).\n"
            "Format: {\"thought\": \"<reasoning>\", \"name\": \"<tool_name>\", \"arguments\": {<args>}}\n\n"
            "Example (DO NOT EXECUTE THIS, just follow the format):\n"
            "{\"thought\": \"I need to list files.\", \"name\": \"run_shell_command\", \"arguments\": {\"command\": \"ls -la\"}}\n\n"
            "CRITICAL:\n"
            "- You MUST include a \"thought\" field explaining WHY you are taking this action.\n"
            "- Do NOT nest JSON inside JSON strings.\n"
            "- Do NOT use 'parameters' field, use 'arguments'.\n"
            "- Output valid JSON only.\n\n"
            "### PROJECT CONTEXT ###\n"
            f"{context_content}\n\n"
            "### FILE SYSTEM RULES ###\n"
            "1. You have access to a `.scratchpad/` directory for temporary files.\n"
            "2. ALWAYS use `.scratchpad/` for experiments.\n\n"
            "### MEMORY CAPABILITIES ###\n"
            "1. **Recall**: You have long-term memory. Use `search_memory` to recall past conversations.\n"
            "2. **Knowledge**: Use `search_knowledge` to find code snippets or documentation in the repo.\n"
            "3. **Pragmatism**: Only search memory or knowledge if explicitly relevant to the user request. Do not perform unprompted searches.\n\n"
            "### AVAILABLE TOOLS ###\n"
            f"{json.dumps([t['function'] for t in self.get_current_tools()], indent=2)}"
        )
        self.history_manager = HistoryManager(system_prompt)
        ToolExecutor.history_manager = self.history_manager
        self.openai = OpenAIService()
        self.view = view if view else CLIView()
        if hasattr(self.view, "set_controller"):
            self.view.set_controller(self)

    async def start(
        self, initial_prompt: Optional[str] = None, session_id: str = "default"
    ):
        await self.view.print_welcome()
        if isinstance(self.view, CLIView):
            if self.context_loaded:
                self.view.console.print("✔ Loaded @CONTEXT.md", style="dim green")
                self.view.console.print(
                    "  • Adhering to AI Directives & MVC", style="dim green"
                )

        # session_id passed from main
        if initial_prompt:
            self.history_manager.get_session(session_id).add("user", initial_prompt)
            # CLIView handles spinners synchronously, so we must AWAIT the turn.
            # Only Textual TUI needs create_task to unblock the rendering loop.
            if hasattr(self.view, "start_app") and not isinstance(self.view, CLIView):
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
        try:
            if user_input.lower() in Config.EXIT_COMMANDS:
                await self.view.print_goodbye()
                import sys

                sys.exit(0)

            self.history_manager.get_session(session_id).add("user", user_input)

            # Process the initial user input
            await self.process_turn(session_id)

            # Check for autonomous continuation (TDD or Auto Mode)
            # We loop here to handle the entire chain of autonomous actions
            while self.pending_tdd_goal or self.auto_mode:
                if self.pending_tdd_goal:
                    await self.run_tdd_cycle(self.pending_tdd_goal, session_id)
                    # run_tdd_cycle clears pending_tdd_goal when done
                elif self.auto_mode:
                    # Re-run process_turn to pick up next task
                    await self.process_turn(session_id)
        except Exception as e:
            await self.view.print_error(f"Error in handle_tui_input: {e}")
            import traceback

            traceback.print_exc()

            # Breaker: If plan is empty/done, auto_mode is set to False in process_turn
            # But we need to ensure we don't infinite loop if it fails to clear
            # process_turn logic handles auto_mode clearing.

    async def chat_loop(self, session_id: str = "default"):
        while True:
            if self.pending_tdd_goal:
                await self.run_tdd_cycle(self.pending_tdd_goal, session_id)
                continue
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

    async def run_tdd_cycle(self, goal: str, session_id: str):
        await self.view.print_agent_response(f"🔄 Starting TDD Cycle for: {goal}")

        # 1. Generate Test
        prompt_test = (
            f"TDD Step 1: Write a failing pytest file for the goal: '{goal}'. "
            "Use '{write_file}' to create it in 'tests/'. "
            "Do NOT implement the logic yet."
        )
        self.history_manager.get_session(session_id).add("user", prompt_test)
        await self.process_turn(session_id)

        # 2. Run Test (Expect Fail)
        prompt_run_fail = "Now run the test you just created using 'run_shell_command' with pytest. It should fail."
        self.history_manager.get_session(session_id).add("user", prompt_run_fail)
        await self.process_turn(session_id)

        # 3. Implement
        prompt_impl = "TDD Step 2: Write the implementation file to satisfy the test. Use '{write_file}'."
        self.history_manager.get_session(session_id).add("user", prompt_impl)
        await self.process_turn(session_id)

        # 4. Run Test (Expect Pass)
        prompt_run_pass = "Now run the test again. It should pass."
        self.history_manager.get_session(session_id).add("user", prompt_run_pass)
        await self.process_turn(session_id)

        self.pending_tdd_goal = None
        await self.view.print_agent_response("✅ TDD Cycle Completed.")

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
                # Handle list of tool calls (legacy/fallback support)
                results.extend(
                    [
                        o
                        for o in obj
                        if isinstance(o, dict) and ("name" in o or "command" in o)
                    ]
                )
            elif isinstance(obj, dict):
                # Handle single tool call with optional Thought
                if "name" in obj or "command" in obj:
                    results.append(obj)

        return results

    def get_current_tools(self):
        """Merges base tools, dynamic skills, and MCP tools."""
        # Check if services are initialized (ToolExecutor might not be fully ready during init)
        try:
            skill_defs = ToolExecutor.skill_service.get_tool_definitions()
            mcp_defs = ToolExecutor.mcp_service.get_tools()
            return self.base_tools + skill_defs + mcp_defs
        except Exception:
            return self.base_tools

    async def process_turn(self, session_id: str = "default"):
        finished_turn = False
        history = self.history_manager.get_session(session_id)
        logger.info(f"Processing turn for session {session_id}")

        # Inject Pinned Context dynamically into each turn
        context_service = ToolExecutor.context_manager.get_service(session_id)
        rag_service = ToolExecutor.rag_manager.get_service(session_id)
        # preference_service removed as unused
        pinned_content = context_service.get_context_string()

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
            with self.view.create_spinner("Updating Context..."):
                await rag_service.index_history("user", last_msg["content"], session_id)

        if pinned_content:
            messages = [m.copy() for m in messages]
            messages.append({"role": "system", "content": pinned_content})

        while not finished_turn:
            # Determine spinner text based on context
            current_messages = history.get()
            last_role = current_messages[-1]["role"] if current_messages else "user"
            spinner_text = "Thinking..."
            if last_role == "tool":
                spinner_text = "Analyzing Tool Output..."
            elif last_role == "user":
                spinner_text = "Processing Request..."

            with self.view.create_spinner(spinner_text):
                try:
                    response_stream = self.openai.create_chat_completion(
                        messages,
                        tools=None,  # FORCE PROMPT ONLY to bypass TabbyAPI 400
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
                                args = (
                                    extracted.get("arguments")
                                    or extracted.get("parameters")
                                    or extracted
                                )

                                # Handle stringified JSON (common local model hallucination)
                                if isinstance(args, str):
                                    try:
                                        args = json.loads(args)
                                    except Exception:
                                        pass  # Keep as string if parsing fails, might be intended

                                # Fallback: if 'command' is at root, treat root as args
                                if (
                                    isinstance(args, dict)
                                    and "command" not in args
                                    and "command" in extracted
                                ):
                                    args = extracted

                                tool_name = extracted.get("name", "run_shell_command")
                                thought = extracted.get("thought")

                                # Log thought telemetry
                                if thought:
                                    try:
                                        telemetry_service = (
                                            ToolExecutor.telemetry_manager.get_service(
                                                session_id
                                            )
                                        )
                                        telemetry_service.log_thought(
                                            session_id, thought
                                        )
                                    except Exception:
                                        pass  # Don't crash on telemetry failure

                                # Print thought if present
                                if thought and isinstance(self.view, CLIView):
                                    self.view.console.print(
                                        f"💭 {thought}", style="dim cyan"
                                    )

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
                                    "user",
                                    content=f"System Error: {output_str}",
                                    tool_call_id=None,
                                )
                                continue

                            if name == "ask_user":
                                question = args.get("question", "")
                                if question:
                                    output = await self.view.ask_user_input(question)
                                else:
                                    output = "Error: No question provided."
                            elif name == "start_tdd":
                                self.pending_tdd_goal = args.get("goal")
                                output = (
                                    f"TDD Loop scheduled for: {self.pending_tdd_goal}"
                                )
                                finished_turn = True
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

                                # Convert tool output to user message
                                history.add(
                                    "user",
                                    content=f"Tool '{name}' output:\n{output_str}",
                                    tool_call_id=None,
                                )
                                # FORCE STOP: Enforce strict "One Shot" behavior.
                                # The agent must return control to the user after every tool execution.
                                finished_turn = True
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
                            with self.view.create_spinner("Updating Context..."):
                                await rag_service.index_history(
                                    "assistant", full_response, session_id
                                )
                        finished_turn = True
                except Exception as e:
                    logger.error(f"Error in process_turn: {str(e)}", exc_info=True)
                    await self.view.print_error(str(e))
                    finished_turn = True
