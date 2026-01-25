from rich.console import Console
from rich.prompt import Prompt
from rich.theme import Theme
from mini_nebulus.config import Config

custom_theme = Theme(
    {
        "info": "dim cyan",
        "warning": "yellow",
        "error": "bold red",
        "user": "green",
        "agent": "blue",
        "tool": "dim white",
    }
)

console = Console(theme=custom_theme)


class CLIView:
    def __init__(self):
        self.console = console

    def print_welcome(self):
        self.console.print("[bold cyan]🦞 Mini-Nebulus Agent[/bold cyan]")
        self.console.print(
            f"[dim]Connected to {Config.NEBULUS_BASE_URL} using {Config.NEBULUS_MODEL}[/dim]\n"
        )

    def prompt_user(self) -> str:
        return Prompt.ask("[user]You[/user]")

    def print_agent_response(self, text: str):
        if text.strip():
            self.console.print(f"[agent]Agent:[/agent] {text.strip()}")

    def print_tool_output(self, output: str):
        formatted = "\n".join([f"  {line}" for line in output.strip().split("\n")])
        self.console.print(f"[tool]{formatted}[/tool]")

    def print_error(self, message: str):
        self.console.print(f"[error]\nError: {message}[/error]")

    def print_goodbye(self):
        self.console.print("[warning]Goodbye![/warning]")

    def create_spinner(self, text: str):
        return self.console.status(f"[blue]{text}[/blue]", spinner="dots")
