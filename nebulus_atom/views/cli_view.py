from typing import Dict, Any, ContextManager, List
from contextlib import contextmanager

from rich.console import Console
from rich.tree import Tree

# Prompt Toolkit Imports
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PromptStyle
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

import sys
import os
import subprocess
import asyncio

from nebulus_atom.config import Config
from nebulus_atom.views.base_view import BaseView


class CLIView(BaseView):
    async def print_welcome(self):
        """Displays the welcome message in a panel."""
        from rich.panel import Panel
        from rich.text import Text
        from rich import box

        model = os.environ.get("NEBULUS_MODEL", Config.NEBULUS_MODEL)

        welcome_text = Text()
        welcome_text.append("Nebulus Atom", style="bold cyan")
        welcome_text.append(" · ", style="dim")
        welcome_text.append(model, style="dim")

        self.console.print(
            Panel(
                welcome_text,
                style="cyan",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )

        # Quick help
        self.console.print(
            "[dim]Ask me to read files, run commands, write code, or search the codebase.[/dim]"
        )
        self.console.print("[dim]Type [bold]exit[/bold] to quit · History: ↑/↓[/dim]\n")

    def __init__(self):
        # Force writing to the real stdout to avoid patch_stdout/Typer encoding issues
        self.console = Console(file=sys.__stdout__, force_terminal=True)

        # Ensure config directory exists and initialize history
        Config.ensure_config_dir()
        self.session = PromptSession(history=FileHistory(Config.HISTORY_FILE))

        self.controller = None
        self.status_message = ""
        self.is_thinking = False

        # input_future is used to pause the main loop and return value to ask_user_input
        self.input_future = None
        self.input_prompt = ""

    def set_controller(self, controller):
        self.controller = controller

    def get_prompt_message(self):
        # Determine prompt style and label based on state
        # Priority: Agent Asking Input > Agent Thinking > Standard User Input
        # Use simple standard XML tags for colors which are more robust

        if self.input_future and not self.input_future.done():
            # Agent needs input - Magenta Box
            return HTML(
                "<ansimagenta>╭─ Answer ──────────────╮</ansimagenta>\n"
                "<ansimagenta>│</ansimagenta> ➤ "
            )
        elif self.is_thinking:
            # Agent is busy - Grey Box
            return HTML(
                "<ansigray>╭─ Processing... ───────╮</ansigray>\n"
                "<ansigray>│</ansigray> ➤ "
            )
        else:
            # Standard - Blue Box
            return HTML(
                "<ansiblue>╭─ Input ───────────────╮</ansiblue>\n"
                "<ansiblue>│</ansiblue> ➤ "
            )

    def create_key_bindings(self):
        kb = KeyBindings()

        @kb.add(Keys.Up)
        def _(event):
            event.current_buffer.auto_up(
                count=1, go_to_start_of_line_if_history_changes=True
            )

        @kb.add(Keys.Down)
        def _(event):
            event.current_buffer.auto_down(
                count=1, go_to_start_of_line_if_history_changes=True
            )

        return kb

    async def start_app(self):
        """Starts the persistent REPL loop with streaming output."""
        from prompt_toolkit.patch_stdout import patch_stdout

        kb = self.create_key_bindings()

        # We apply patch_stdout ONLY during the prompt phase to catch background logs.
        # We release it during execution so Rich can render the spinner correctly without interference.
        while True:
            try:
                # 1. Prompt Phase (Logs patched)
                with patch_stdout():
                    # Wait for input using dynamic prompt message
                    user_input = await self.session.prompt_async(
                        self.get_prompt_message,
                        bottom_toolbar=self.get_bottom_toolbar,
                        style=PromptStyle.from_dict(
                            {
                                "bottom-toolbar": "#444444 bg:#222222",
                            }
                        ),
                        refresh_interval=0.5,
                        key_bindings=kb,
                    )

                if not user_input.strip():
                    continue

                # Handle slash commands
                if user_input.strip().startswith("/"):
                    if await self._handle_slash_command(user_input.strip()):
                        continue  # Command handled, prompt again

                # 2. Execution Phase (No patch, direct stdout)
                # Handle Input Routing
                if self.input_future and not self.input_future.done():
                    # Route to waiting agent
                    self.input_future.set_result(user_input.strip())
                    self.input_future = None
                else:
                    # Route to controller (New Command)
                    if self.controller:
                        # Await the controller. Rich spinner will run cleanly here.
                        await self.controller.handle_tui_input(user_input)

            except (EOFError, KeyboardInterrupt):
                self.console.print("[bold cyan]👋 Goodbye![/bold cyan]")
                break
            except Exception as e:
                self.console.print(f"[bold red]Error in REPL loop: {e}[/bold red]")
                import traceback

                traceback.print_exc()

    async def _handle_slash_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if command was handled."""
        parts = command.split()
        cmd = parts[0].lower()
        # args = parts[1:] if len(parts) > 1 else []  # Reserved for future use

        if cmd in ("/exit", "/quit", "/q"):
            self.console.print("[bold cyan]👋 Goodbye![/bold cyan]")
            import sys

            sys.exit(0)

        elif cmd in ("/clear", "/cls"):
            self.console.clear()
            return True

        elif cmd in ("/help", "/?"):
            self._print_help()
            return True

        elif cmd == "/context":
            # Show pinned context files
            if self.controller and hasattr(self.controller, "history_manager"):
                from nebulus_atom.services.tool_executor import ToolExecutor

                ctx_service = ToolExecutor.context_manager.get_service("default")
                files = ctx_service.list_context()
                if files:
                    self.console.print("[bold]Pinned files:[/bold]")
                    for f in files:
                        self.console.print(f"  • {f}", style="dim")
                else:
                    self.console.print("[dim]No files pinned to context[/dim]")
            return True

        elif cmd == "/model":
            self.console.print(f"[bold]Model:[/bold] {Config.NEBULUS_MODEL}")
            return True

        else:
            self.console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
            self.console.print("[dim]Type /help for available commands[/dim]")
            return True

    def _print_help(self):
        """Print help information."""
        from rich.table import Table
        from rich.panel import Panel

        help_table = Table(show_header=False, box=None, padding=(0, 2))
        help_table.add_column("Command", style="cyan")
        help_table.add_column("Description")

        help_table.add_row("/help", "Show this help message")
        help_table.add_row("/clear", "Clear the screen")
        help_table.add_row("/context", "Show pinned context files")
        help_table.add_row("/model", "Show current model")
        help_table.add_row("/exit", "Exit the CLI")
        help_table.add_row("", "")
        help_table.add_row("[dim]exit[/dim]", "[dim]Also exits the CLI[/dim]")

        self.console.print(
            Panel(
                help_table,
                title="[bold]Commands[/bold]",
                border_style="dim",
            )
        )

        self.console.print("\n[bold]Capabilities:[/bold]")
        self.console.print("  • Read and write files")
        self.console.print("  • Run shell commands")
        self.console.print("  • Search codebase (RAG)")
        self.console.print("  • Create and execute plans")
        self.console.print("  • Pin files to context")
        self.console.print()

    def _get_rich_toolbar(self):
        """Generates a Rich renderable for the bottom toolbar."""
        from rich.table import Table
        from rich.text import Text

        cwd = os.getcwd().replace(os.path.expanduser("~"), "~")
        branch = self._get_git_branch()
        branch_str = f"({branch})" if branch else ""
        model = Config.NEBULUS_MODEL

        # Create a table to mimic the PTK toolbar layout
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")

        # Left side: CWD + Branch
        left_text = Text()
        left_text.append(f"{cwd} ", style="bold default")
        left_text.append(f"{branch_str}", style="cyan")

        # Right side: Model + App Name + Status
        right_text = Text()
        right_text.append("Model: ", style="dim")
        right_text.append(f"{model} ", style="bold default")
        right_text.append("│ ", style="dim")
        right_text.append("Nebulus Atom", style="bold default")

        if self.status_message:
            right_text.append(f" {self.status_message} ", style="black on yellow")

        grid.add_row(left_text, right_text)

        # Wrap in a style to match the PTK toolbar background
        from rich.panel import Panel
        from rich import box

        return Panel(grid, style="white on #222222", box=box.SIMPLE, padding=(0, 1))

    def create_spinner(self, text: str) -> ContextManager:
        if os.environ.get("MINI_NEBULUS_HEADLESS") == "1":
            # Headless mode: Simple log, no Rich Live
            self.console.print(f"[dim]Thinking: {text}[/dim]")

            @contextmanager
            def dummy():
                yield

            return dummy()

        # Simplified to use standard Rich Status for maximum reliability
        return self.console.status(f"[bold cyan]{text}[/bold cyan]", spinner="dots")

    def _get_git_branch(self):
        try:
            return (
                subprocess.check_output(
                    ["git", "branch", "--show-current"], stderr=subprocess.DEVNULL
                )
                .decode()
                .strip()
            )
        except Exception:
            return ""

    def get_bottom_toolbar(self):
        cwd = os.getcwd().replace(os.path.expanduser("~"), "~")
        branch = self._get_git_branch()
        branch_str = f"({branch})" if branch else ""
        model = Config.NEBULUS_MODEL

        status_part = ""
        if self.status_message:
            status_part = (
                f" <style bg='ansiyellow' color='black'> {self.status_message} </style>"
            )

        # Simple status bar: Path (Branch) ... Model ... Status
        return HTML(
            f"<b>{cwd}</b> <style color='ansicyan'>{branch_str}</style> "
            f"<style color='ansigray'>│</style> Model: <b>{model}</b> "
            f"<style color='ansigray'>│</style> <b>Nebulus Atom</b>"
            f"{status_part}"
        )

    # Legacy method shim for Controller compatibility if it calls prompt_user directly
    # But in start_app mode, controller shouldn't call this.
    async def prompt_user(self) -> str:
        return await self.session.prompt_async("> ")

    async def ask_user_input(self, question: str) -> str:
        # Event-driven: Print question, set state, wait for Future
        self.console.print(f"[bold magenta]❓ {question}[/bold magenta]")

        loop = asyncio.get_running_loop()
        self.input_future = loop.create_future()
        self.input_prompt = "Answer"

        # Force refresh of prompt app to pick up state change immediately
        if hasattr(self.session, "app"):
            self.session.app.invalidate()

        # Wait for the main loop to fulfill the future
        return await self.input_future

    async def print_agent_response(self, text: str):
        """Print agent's natural language response."""
        # Clean, indented response with subtle styling
        self.console.print()
        for line in text.split("\n"):
            self.console.print(f"  {line}", style="default")
        self.console.print()

    def print_thought(self, thought: str):
        """Print agent's reasoning/thought (very subtle)."""
        self.console.print(f"  [dim italic]💭 {thought}[/dim italic]")

    async def print_telemetry(self, metrics: Dict[str, Any]):
        """Print performance metrics (if any)."""
        if metrics:
            ttft = metrics.get("ttft_ms")
            if ttft:
                self.console.print(f"  [dim]⏱ {ttft:.0f}ms to first token[/dim]")

    async def print_tool_output(self, output: str, tool_name: str = ""):
        """Print tool execution result - compact format."""
        # Compact one-liner for successful execution
        preview = output.replace("\n", " ")[:80]
        if len(output) > 80:
            preview += "…"
        self.console.print(
            f"  [green]✓[/green] [dim]{tool_name}[/dim] → [dim]{preview}[/dim]"
        )

    async def print_plan(self, plan_data: Dict[str, Any]):
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

        self.console.print(tree)

    async def print_context(self, context_data: List[str]):
        # Optional: Print context if needed by CLI
        pass

    async def print_error(self, message: str):
        """Print error message with prominent styling."""
        from rich.panel import Panel

        self.console.print(
            Panel(
                f"[white]{message}[/white]",
                title="[bold]Error[/bold]",
                border_style="red",
                padding=(0, 1),
            )
        )

    async def print_goodbye(self):
        self.console.print("[bold cyan]👋 Goodbye![/bold cyan]")

    # Streaming output methods
    def print_stream_start(self):
        """Called before streaming response begins."""
        self.console.print("[bold green]Agent:[/bold green] ", end="")

    def print_stream_chunk(self, text: str):
        """Called for each chunk of streamed text."""
        self.console.print(text, end="", highlight=False)

    def print_stream_end(self):
        """Called when streaming response is complete."""
        self.console.print()  # Final newline
