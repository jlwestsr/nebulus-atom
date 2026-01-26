from typing import Dict, Any, ContextManager
from rich.console import Console
from rich.prompt import Prompt
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from mini_nebulus.config import Config
from mini_nebulus.views.base_view import BaseView

custom_theme = Theme(
    {
        "info": "dim cyan",
        "warning": "yellow",
        "error": "bold red",
        "user": "bold green",
        "agent": "bold blue",
        "tool": "dim white",
        "task.pending": "dim white",
        "task.in_progress": "yellow",
        "task.completed": "green",
        "task.failed": "red",
        "question": "bold magenta",
    }
)

console = Console(theme=custom_theme)


class CLIView(BaseView):
    def __init__(self):
        self.console = console

    def print_welcome(self):
        self.console.print("[bold cyan]🦞 Mini-Nebulus Agent[/bold cyan]")
        self.console.print(
            f"[dim]Connected to {Config.NEBULUS_BASE_URL} using {Config.NEBULUS_MODEL}[/dim]\n"
        )

    def prompt_user(self) -> str:
        return Prompt.ask("[user]You[/user]")

    def ask_user_input(self, question: str) -> str:
        self.console.print(f"[question]Agent asks:[/question] {question}")
        return Prompt.ask("[question]Answer[/question]")

    async def print_agent_response(self, text: str):
        if text.strip():
            # Use a panel for longer agent responses to give it that "Gemini CLI" feel
            if len(text) > 200:
                self.console.print(
                    Panel(text.strip(), title="Mini-Nebulus", border_style="blue")
                )
            else:
                self.console.print(f"[agent]Agent:[/agent] {text.strip()}")

    async def print_tool_output(self, output: str, tool_name: str = ""):
        if not output:
            return

        # If output looks like code/file content, use Syntax highlighting
        if tool_name == "read_file":
            syntax = Syntax(output, "python", theme="monokai", line_numbers=True)
            self.console.print(Panel(syntax, title="File Content", border_style="dim"))
        else:
            formatted = "\n".join([f"  {line}" for line in output.strip().split("\n")])
            self.console.print(f"[tool]{formatted}[/tool]")

    async def print_plan(self, plan_data: Dict[str, Any]):
        """Displays the current plan in a Table."""
        table = Table(
            title=f"Plan: {plan_data.get('goal', 'Unknown Goal')}", border_style="cyan"
        )
        table.add_column("ID", justify="right", style="dim", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Task")

        for task in plan_data.get("tasks", []):
            status = task.get("status", "pending").lower()
            status_style = f"task.{status}"
            icon = "○"
            if status == "completed":
                icon = "✔"
            elif status == "in_progress":
                icon = "▶"
            elif status == "failed":
                icon = "✖"

            table.add_row(
                task.get("id", "")[:8],
                f"[{status_style}]{icon} {status.upper()}[/{status_style}]",
                task.get("description", ""),
            )

        self.console.print(table)

    async def print_error(self, message: str):
        self.console.print(f"[error]\nError: {message}[/error]")

    def print_goodbye(self):
        self.console.print("[warning]Goodbye![/warning]")

    def create_spinner(self, text: str) -> ContextManager:
        return self.console.status(f"[blue]{text}[/blue]", spinner="dots")
