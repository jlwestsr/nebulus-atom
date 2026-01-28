from typing import Dict, Any, ContextManager, List
from contextlib import contextmanager
import asyncio

from textual.app import App, ComposeResult
from textual.containers import Grid, Container, Vertical
from textual.widgets import Footer, Log, Tree, Label, TextArea
from textual.binding import Binding
from rich.text import Text

from mini_nebulus.views.base_view import BaseView


class Sidebar(Container):
    def compose(self) -> ComposeResult:
        yield Label("[bold]Plan[/bold]", classes="section-title")
        yield Tree("Tasks", id="plan-tree")
        yield Label("[bold]Context[/bold]", classes="section-title")
        yield Log(id="context-log")


class ChatPanel(Container):
    def compose(self) -> ComposeResult:
        yield Log(id="chat-log", markup=True)


class MiniNebulusApp(App):
    CSS = """
    Grid {
        grid-size: 2 2;
        grid-columns: 1fr 3fr;
        grid-rows: 1fr auto;
    }

    Sidebar {
        row-span: 2;
        background: $panel;
        border-right: vkey $accent;
        width: 100%;
        height: 100%;
    }

    .section-title {
        background: $accent;
        color: $text;
        padding: 0 1;
        width: 100%;
    }

    #plan-tree {
        height: 1fr;
        border-bottom: solid $accent;
    }

    #context-log {
        height: 1fr;
    }

    #main-area {
        height: 100%;
        background: $surface;
    }

    ChatPanel {
        height: 100%;
    }

    #chat-log {
        height: 100%;
        padding: 1;
    }

    TextArea {
        dock: bottom;
        height: 5;
        border-top: solid $accent;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_log", "Clear Log", show=True),
        Binding("ctrl+s", "submit_message", "Submit", show=True),
    ]

    controller = None  # To be set via TUIView
    pending_input: asyncio.Future = None

    def compose(self) -> ComposeResult:
        with Grid():
            yield Sidebar()
            with Vertical(id="main-area"):
                yield ChatPanel()
                yield TextArea(id="input-area", show_line_numbers=False)
        yield Footer()

    def action_clear_log(self):
        log = self.query_one("#chat-log", Log)
        log.clear()

    async def action_submit_message(self):
        input_area = self.query_one("#input-area", TextArea)
        user_input = input_area.text

        if not user_input.strip():
            return

        input_area.text = ""  # Clear input

        # Display user message immediately
        log = self.query_one("#chat-log", Log)
        log.write(Text(f"User: {user_input}", style="bold cyan"))

        # Check if we are waiting for specific input (ask_user)
        if self.pending_input and not self.pending_input.done():
            self.pending_input.set_result(user_input)
            return

        if self.controller:
            await self.controller.handle_tui_input(user_input)

    async def on_key(self, event) -> None:
        pass


class TUIView(BaseView):
    def __init__(self):
        self.app = MiniNebulusApp()
        self.controller = None

    def set_controller(self, controller):
        self.controller = controller
        self.app.controller = controller

    async def start_app(self):
        """Starts the Textual App."""
        await self.app.run_async()

    async def print_welcome(self):
        # Can't print to log yet if app isn't running, but can queue or ignore
        pass

    async def prompt_user(self) -> str:
        # Not used in TUI event-driven mode
        raise NotImplementedError("TUI uses event-driven input")

    async def ask_user_input(self, question: str) -> str:
        if not self.app.is_running:
            return "Error: TUI not running"

        # Display question
        log = self.app.query_one("#chat-log", Log)
        log.write(Text(f"❓ {question}", style="bold magenta"))
        log.write(Text("  (Please type your answer below)", style="dim magenta"))

        # Create future
        loop = asyncio.get_running_loop()
        self.app.pending_input = loop.create_future()

        # Wait for answer
        answer = await self.app.pending_input
        self.app.pending_input = None

        return answer

    async def print_agent_response(self, text: str):
        if self.app.is_running:
            log = self.app.query_one("#chat-log", Log)
            log.write(Text("Agent:", style="bold green"))
            log.write(text)
            log.write("")  # Newline

    async def print_telemetry(self, metrics: Dict[str, Any]):
        pass

    async def print_tool_output(self, output: str, tool_name: str = ""):
        if self.app.is_running:
            log = self.app.query_one("#chat-log", Log)
            log.write(Text(f"Tool ({tool_name}):", style="bold blue"))
            log.write(output)
            log.write("")

    async def print_plan(self, plan_data: Dict[str, Any]):
        if self.app.is_running:
            tree = self.app.query_one("#plan-tree", Tree)
            tree.clear()
            tree.root.label = f"Goal: {plan_data.get("goal", "Unknown")}"
            tree.root.expand()

            for task in plan_data.get("tasks", []):
                status_icon = "⏳"
                if task["status"] == "completed":
                    status_icon = "✅"
                elif task["status"] == "in_progress":
                    status_icon = "🔄"
                elif task["status"] == "failed":
                    status_icon = "❌"

                tree.root.add(f"{status_icon} {task["description"]}", expand=True)

    async def print_context(self, context_data: List[str]):
        if self.app.is_running:
            log = self.app.query_one("#context-log", Log)
            log.clear()
            for item in context_data:
                log.write(Text(f"• {item}", style="dim cyan"))

    async def print_error(self, message: str):
        if self.app.is_running:
            log = self.app.query_one("#chat-log", Log)
            log.write(Text(f"Error: {message}", style="bold red"))

    async def print_goodbye(self):
        if self.app.is_running:
            self.app.exit()

    @contextmanager
    def create_spinner(self, text: str) -> ContextManager:
        # TUI spinner could be a loading indicator widget
        yield
