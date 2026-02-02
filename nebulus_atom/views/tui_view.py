from typing import Dict, Any, ContextManager
from contextlib import contextmanager
import asyncio
import os

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog
from rich.panel import Panel
from rich.table import Table
from rich import box


class TextualView(App):
    """
    Main TUI View using Textual.
    Implements the BaseView interface (implicitly) to work with AgentController.
    """

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-columns: 2fr 1fr;
        grid-rows: 1 1fr 3;
    }

    Header {
        dock: top;
        column-span: 2;
    }

    #chat_log {
        width: 100%;
        height: 100%;
        border: solid cyan;
        background: $surface;
    }

    #status_log {
        width: 100%;
        height: 100%;
        border: solid green;
        background: $surface;
    }

    Input {
        dock: bottom;
        width: 100%;
        column-span: 2;
        border: heavy magenta;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear Log"),
    ]

    def __init__(self):
        super().__init__()
        self.controller = None
        self.input_future = None
        self.logger = None
        self.status_logger = None
        self.user_input_widget = None
        self.queued_messages = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="chat_log", highlight=True, markup=True)
        yield RichLog(id="status_log", highlight=True, markup=True)
        yield Input(placeholder="Type your command...", id="user_input")
        yield Footer()

    def on_mount(self) -> None:
        self.logger = self.query_one("#chat_log", RichLog)
        self.status_logger = self.query_one("#status_log", RichLog)

        self.status_logger.write("[bold underline]Status & Plan[/bold underline]")

        self.user_input_widget = self.query_one("#user_input", Input)
        self.user_input_widget.focus()

        # Flush queued messages
        for msg in self.queued_messages:
            self.logger.write(msg)
        self.queued_messages.clear()

    def set_controller(self, controller):
        self.controller = controller

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Handle input submission from the Textual widget."""
        value = message.value.strip()
        if not value:
            return

        self.user_input_widget.value = ""

        # Log the user's input as a "chat bubble"
        self.logger.write(f"\n[bold magenta]➤ User:[/bold magenta] {value}\n")

        # Logic to route input
        if self.input_future and not self.input_future.done():
            # If the agent is waiting for input (via prompt_user), resolve the future
            self.input_future.set_result(value)
            self.input_future = None
        elif self.controller:
            # Initiate a new turn if we aren't waiting for specific input
            self.run_worker(self._handle_controller_input(value))

    async def _handle_controller_input(self, value: str):
        """Helper to await controller input handling safely."""
        try:
            await self.controller.handle_tui_input(value)
        except Exception as e:
            if self.logger:
                self.logger.write(f"[bold red]Error handling input: {e}[/bold red]")

    # --- BaseView Implementation ---

    async def start_app(self):
        """Starts the Textual App."""
        # This blocks until the app exits
        await self.run_async()

    def action_quit(self):
        self.exit()

    def action_clear_log(self):
        if self.logger:
            self.logger.clear()

    async def print_welcome(self):
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            "[bold cyan]Nebulus Atom Agent[/bold cyan]",
            f"[dim]Model: {os.environ.get('NEBULUS_MODEL', 'qwen2.5-coder')}[/dim]",
        )
        panel = Panel(grid, style="cyan", box=box.ROUNDED)

        if self.logger:
            self.logger.write(panel)
        else:
            self.queued_messages.append(panel)

    # The Logic Bridge: prompt_user waits for the UI event
    async def prompt_user(self) -> str:
        # Create a future that on_input_submitted will resolve
        loop = asyncio.get_running_loop()
        self.input_future = loop.create_future()

        # Ensure input is focused
        if self.user_input_widget:
            self.user_input_widget.focus()

        # Wait for user to type something
        return await self.input_future

    async def ask_user_input(self, question: str) -> str:
        self.logger.write(f"[bold magenta]❓ {question}[/bold magenta]")
        return await self.prompt_user()

    async def print_agent_response(self, text: str):
        self.logger.write(f"[bold green]Agent:[/bold green] {text}")

    async def print_telemetry(self, metrics: Dict[str, Any]):
        pass

    async def print_tool_output(self, output: str, tool_name: str = ""):
        self.logger.write(f"[dim blue]✔ Executed: {tool_name}[/dim blue]")
        if len(output) > 500:
            self.logger.write(f"  [dim]{output[:500]}... (truncated)[/dim]")
        else:
            self.logger.write(f"  [dim]{output}[/dim]")

    async def print_plan(self, plan_data: Dict[str, Any]):
        # Reuse existing tree logic, print to STATUS log
        from rich.tree import Tree

        goal = plan_data.get("goal", "Unknown Goal")
        tasks = plan_data.get("tasks", [])

        tree = Tree(f"[bold]{goal}[/bold]")
        for task in tasks:
            icon = "⏳"
            if task["status"] == "completed":
                icon = "✅"
            elif task["status"] == "in_progress":
                icon = "🔄"
            elif task["status"] == "failed":
                icon = "❌"
            tree.add(f"{icon} {task['description']}")

        # Clear active status log and update
        if self.status_logger:
            self.status_logger.clear()
            self.status_logger.write("[bold underline]Current Plan[/bold underline]")
            self.status_logger.write(tree)

    async def print_context(self, context_list: list):
        if self.status_logger:
            self.status_logger.write("\n[bold]Pinned Files:[/bold]")
            for item in context_list:
                self.status_logger.write(f"- {item}")

    async def print_error(self, message: str):
        self.logger.write(f"[bold red]❌ {message}[/bold red]")

    async def print_goodbye(self):
        self.logger.write("[bold cyan]👋 Goodbye![/bold cyan]")
        await asyncio.sleep(1)
        self.exit()

    @contextmanager
    def create_spinner(self, text: str) -> ContextManager:
        original_sub = self.sub_title
        self.sub_title = f"⠙ {text}"
        try:
            yield
        finally:
            self.sub_title = original_sub

    # Streaming output methods (TUI accumulates and displays at end)
    def print_stream_start(self):
        """Called before streaming response begins."""
        self._stream_buffer = ""

    def print_stream_chunk(self, text: str):
        """Called for each chunk of streamed text."""
        self._stream_buffer = getattr(self, "_stream_buffer", "") + text

    def print_stream_end(self):
        """Called when streaming response is complete."""
        if hasattr(self, "_stream_buffer") and self._stream_buffer:
            self.logger.write(f"[bold green]Agent:[/bold green] {self._stream_buffer}")
            self._stream_buffer = ""
