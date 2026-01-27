from typing import Dict, Any, ContextManager, List
from contextlib import contextmanager

from textual.app import App, ComposeResult
from textual.containers import Grid, Container, Vertical
from textual.widgets import Footer, Input, Log, Tree, Label
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

    Input {
        dock: bottom;
        height: 3;
        border-top: solid $accent;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_log", "Clear Log", show=True),
    ]

    controller = None  # To be set via TUIView

    def compose(self) -> ComposeResult:
        with Grid():
            yield Sidebar()
            with Vertical(id="main-area"):
                yield ChatPanel()
                yield Input(placeholder="Type your command...", id="input-area")
        yield Footer()

    def action_clear_log(self):
        log = self.query_one("#chat-log", Log)
        log.clear()

    async def on_input_submitted(self, message: Input.Submitted):
        if not message.value.strip():
            return

        user_input = message.value
        message.input.value = ""  # Clear input

        # Display user message immediately
        log = self.query_one("#chat-log", Log)
        log.write(Text(f"User: {user_input}", style="bold cyan"))

        if self.controller:
            await self.controller.handle_tui_input(user_input)


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

    def print_welcome(self):
        # Can't print to log yet if app isn't running, but can queue or ignore
        pass

    def prompt_user(self) -> str:
        # Not used in TUI event-driven mode
        raise NotImplementedError("TUI uses event-driven input")

    def ask_user_input(self, question: str) -> str:
        # TODO: Implement a modal or input request in TUI
        # For now, return a placeholder or implement blocking logic (hard in async)
        return "User input via TUI (Not Implemented)"

    async def print_agent_response(self, text: str):
        if self.app.is_running:
            log = self.app.query_one("#chat-log", Log)
            log.write(Text("Agent:", style="bold green"))
            log.write(text)
            log.write("")  # Newline

    def print_telemetry(self, metrics: Dict[str, Any]):
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
            tree.root.label = f"Goal: {plan_data.get('goal', 'Unknown')}"
            tree.root.expand()

            for task in plan_data.get("tasks", []):
                status_icon = "⏳"
                if task["status"] == "completed":
                    status_icon = "✅"
                elif task["status"] == "in_progress":
                    status_icon = "🔄"
                elif task["status"] == "failed":
                    status_icon = "❌"

                tree.root.add(f"{status_icon} {task['description']}", expand=True)

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

    def print_goodbye(self):
        if self.app.is_running:
            self.app.exit()

    @contextmanager
    def create_spinner(self, text: str) -> ContextManager:
        # TUI spinner could be a loading indicator widget
        yield
