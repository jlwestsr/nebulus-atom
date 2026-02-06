"""
Agent controller orchestrating conversation flow.

Coordinates tool registry, response parsing, and turn processing
to manage CLI and TUI interactions.
"""

import asyncio
from typing import Optional

from nebulus_atom.config import Config
from nebulus_atom.models.history import HistoryManager
from nebulus_atom.models.task import TaskStatus
from nebulus_atom.services.openai_service import OpenAIService
from nebulus_atom.services.tool_executor import ToolExecutor
from nebulus_atom.services.tool_registry import ToolRegistry
from nebulus_atom.services.response_parser import ResponseParser
from nebulus_atom.controllers.turn_processor import TurnProcessor, TurnCallbacks
from nebulus_atom.views.base_view import BaseView
from nebulus_atom.views.cli_view import CLIView
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class AgentController:
    """Orchestrates conversation flow between user, LLM, and tools."""

    def __init__(self, view: Optional[BaseView] = None) -> None:
        """
        Initialize the agent controller.

        Args:
            view: Optional view for rendering. Defaults to CLIView.
        """
        logger.info("Initializing AgentController")
        ToolExecutor.initialize()

        self.auto_mode = False
        self.pending_tdd_goal: Optional[str] = None

        self._tool_registry = ToolRegistry()
        self._response_parser = ResponseParser()
        self._openai = OpenAIService()
        self.view = view if view else CLIView()

        self._turn_processor = TurnProcessor(
            self._openai, self.view, self._response_parser
        )

        system_prompt = self._build_system_prompt()
        self.history_manager = HistoryManager(system_prompt)
        ToolExecutor.history_manager = self.history_manager

        if hasattr(self.view, "set_controller"):
            self.view.set_controller(self)

    def _build_system_prompt(self) -> str:
        """Build the system prompt with current tool list."""
        tool_list = self._tool_registry.get_tool_list_string(
            skill_service=ToolExecutor.skill_service,
            mcp_service=ToolExecutor.mcp_service,
        )

        return f"""You are an autonomous coding assistant. Execute tasks using tools.

## How to Call Tools
Output a JSON object (no markdown):
{{"thought": "why", "name": "tool_name", "arguments": {{...}}}}

Example:
{{"thought": "List directory contents", "name": "run_shell_command", "arguments": {{"command": "ls -la"}}}}

## Rules
1. Use tools to act. Do not just describe what you would do.
2. One task at a time. Stop after completing the user's request.
3. Only use the tools listed below. Do not invent tools.

## Available Tools
{tool_list}
"""

    @property
    def base_tools(self):
        """Backward compatibility: access base tools from registry."""
        return self._tool_registry.base_tools

    def get_current_tools(self):
        """Get merged tool list (base + skills + MCP)."""
        return self._tool_registry.get_all_tools(
            ToolExecutor.skill_service,
            ToolExecutor.mcp_service,
        )

    async def _check_llm_health(self) -> bool:
        """Verify the LLM server is reachable before entering the chat loop.

        Returns:
            True if the server is healthy, False otherwise.
        """
        try:
            response = await self._openai.client.models.list()
            available = [m.id for m in response.data]
            if Config.NEBULUS_MODEL not in available:
                logger.warning(
                    f"Model '{Config.NEBULUS_MODEL}' not found. Available: {available}"
                )
                await self.view.print_error(
                    f"Model '{Config.NEBULUS_MODEL}' not found on server. "
                    f"Available models: {', '.join(available)}"
                )
                return False
            logger.info(f"LLM server healthy, model '{Config.NEBULUS_MODEL}' available")
            return True
        except Exception as e:
            logger.error(f"LLM server unreachable: {e}")
            await self.view.print_error(
                f"Cannot reach LLM server at {Config.NEBULUS_BASE_URL}: {e}"
            )
            return False

    async def start(
        self, initial_prompt: Optional[str] = None, session_id: str = "default"
    ) -> None:
        """
        Start the agent interaction loop.

        Args:
            initial_prompt: Optional initial user prompt.
            session_id: Session identifier.
        """
        if not await self._check_llm_health():
            return

        try:
            await self.view.print_welcome()

            if initial_prompt:
                self.history_manager.get_session(session_id).add("user", initial_prompt)
                if hasattr(self.view, "start_app") and not isinstance(
                    self.view, CLIView
                ):
                    asyncio.create_task(self.process_turn(session_id))
                else:
                    await self.process_turn(session_id)

            if hasattr(self.view, "start_app"):
                await self.view.start_app()
            else:
                await self.chat_loop(session_id)
        finally:
            await ToolExecutor.shutdown()

    async def handle_tui_input(
        self, user_input: str, session_id: str = "default"
    ) -> None:
        """
        Handle input from TUI.

        Args:
            user_input: User input text.
            session_id: Session identifier.
        """
        try:
            if user_input.lower() in Config.EXIT_COMMANDS:
                await self.view.print_goodbye()
                import sys

                sys.exit(0)

            self.history_manager.get_session(session_id).add("user", user_input)
            await self.process_turn(session_id)

            while self.pending_tdd_goal or self.auto_mode:
                if self.pending_tdd_goal:
                    await self.run_tdd_cycle(self.pending_tdd_goal, session_id)
                elif self.auto_mode:
                    await self.process_turn(session_id)

        except Exception as e:
            await self.view.print_error(f"Error in handle_tui_input: {e}")
            import traceback

            traceback.print_exc()

    async def chat_loop(self, session_id: str = "default") -> None:
        """
        Main CLI chat loop.

        Args:
            session_id: Session identifier.
        """
        while True:
            if self.pending_tdd_goal:
                await self.run_tdd_cycle(self.pending_tdd_goal, session_id)
                continue

            try:
                if self.auto_mode:
                    should_continue = await self._handle_auto_mode(session_id)
                    if not should_continue:
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

    async def _handle_auto_mode(self, session_id: str) -> bool:
        """
        Handle autonomous execution mode.

        Args:
            session_id: Session identifier.

        Returns:
            True if should continue loop, False to restart loop iteration.
        """
        task_service = ToolExecutor.task_manager.get_service(session_id)
        plan = task_service.current_plan

        if not plan:
            self.auto_mode = False
            if isinstance(self.view, CLIView):
                self.view.console.print(
                    "No active plan. Stopping auto-execution.",
                    style="bold red",
                )
            return False

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

            task_service.update_task_status(next_task.id, TaskStatus.IN_PROGRESS)

            user_input = (
                f"Execute this task: {next_task.description}. "
                "Mark it as COMPLETED when done."
            )

            self.history_manager.get_session(session_id).add("user", user_input)
            await self.process_turn(session_id)

            updated_task = task_service.get_task(next_task.id)
            if updated_task.status != TaskStatus.COMPLETED:
                if updated_task.status == TaskStatus.FAILED:
                    self.auto_mode = False
                    if isinstance(self.view, CLIView):
                        self.view.console.print(
                            "Task failed. Stopping auto-execution.",
                            style="bold red",
                        )
            return True
        else:
            self.auto_mode = False
            if isinstance(self.view, CLIView):
                self.view.console.print(
                    "All tasks completed. Stopping auto-execution.",
                    style="bold green",
                )
            return False

    async def run_tdd_cycle(self, goal: str, session_id: str) -> None:
        """
        Run a TDD cycle for the given goal.

        Args:
            goal: TDD goal description.
            session_id: Session identifier.
        """
        await self.view.print_agent_response(f"🔄 Starting TDD Cycle for: {goal}")

        prompt_test = (
            f"TDD Step 1: Write a failing pytest file for the goal: '{goal}'. "
            "Use '{write_file}' to create it in 'tests/'. "
            "Do NOT implement the logic yet."
        )
        self.history_manager.get_session(session_id).add("user", prompt_test)
        await self.process_turn(session_id)

        prompt_run_fail = (
            "Now run the test you just created using 'run_shell_command' "
            "with pytest. It should fail."
        )
        self.history_manager.get_session(session_id).add("user", prompt_run_fail)
        await self.process_turn(session_id)

        prompt_impl = (
            "TDD Step 2: Write the implementation file to satisfy the test. "
            "Use '{write_file}'."
        )
        self.history_manager.get_session(session_id).add("user", prompt_impl)
        await self.process_turn(session_id)

        prompt_run_pass = "Now run the test again. It should pass."
        self.history_manager.get_session(session_id).add("user", prompt_run_pass)
        await self.process_turn(session_id)

        self.pending_tdd_goal = None
        await self.view.print_agent_response("✅ TDD Cycle Completed.")

    async def process_turn(self, session_id: str = "default") -> None:
        """
        Process a single conversation turn.

        Args:
            session_id: Session identifier.
        """
        logger.info(f"Processing turn for session {session_id}")
        history = self.history_manager.get_session(session_id)

        context_service = ToolExecutor.context_manager.get_service(session_id)
        rag_service = ToolExecutor.rag_manager.get_service(session_id)
        pinned_content = context_service.get_context_string()

        if hasattr(self.view, "print_context"):
            context_list = context_service.list_context()
            if isinstance(context_list, list):
                await self.view.print_context(context_list)

        messages = history.get()
        last_msg = messages[-1] if messages else None
        if last_msg and last_msg["role"] == "user":
            with self.view.create_spinner("Updating Context..."):
                await rag_service.index_history("user", last_msg["content"], session_id)

        def on_tdd_start(goal: str) -> None:
            self.pending_tdd_goal = goal

        def on_auto_mode_start() -> None:
            self.auto_mode = True

        callbacks = TurnCallbacks(
            on_tdd_start=on_tdd_start,
            on_auto_mode_start=on_auto_mode_start,
        )

        await self._turn_processor.process(
            history, session_id, pinned_content, callbacks
        )
