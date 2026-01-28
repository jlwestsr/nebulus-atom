from typing import Dict, Any, ContextManager
from rich.console import Console
from rich.prompt import Prompt
from rich.theme import Theme
from rich.panel import Panel
from rich.tree import Tree
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

    async def print_welcome(self):
        self.console.print("[bold cyan]🦞 Mini-Nebulus Agent[/bold cyan]")
        self.console.print(
            f"[dim]Connected to {Config.NEBULUS_BASE_URL} using {Config.NEBULUS_MODEL}[/dim]\n"
        )

    async def prompt_user(self) -> str:
        return Prompt.ask("[user]You[/user]")

    async def ask_user_input(self, question: str) -> str:
        self.console.print(f"[question]Agent asks:[/question] {question}")
        return Prompt.ask("[question]Answer[/question]")

    async def print_agent_response(self, text: str):
        if text.strip():
            if len(text) > 200:
                self.console.print(
                    Panel(text.strip(), title="Mini-Nebulus", border_style="blue")
                )
            else:
                self.console.print(f"[agent]Agent:[/agent] {text.strip()}")

    async def print_telemetry(self, metrics: Dict[str, Any]):
        """Displays performance telemetry in a footer."""
        if not metrics:
            return

        ttft = f"{metrics.get('ttft', 0):.2f}s" if metrics.get("ttft") else "N/A"
        total = (
            f"{metrics.get('total_time', 0):.2f}s"
            if metrics.get("total_time")
            else "N/A"
        )
        usage = metrics.get("usage", {})

        # Format: Latency: 0.12s / 2.3s | Tokens: 50 / 120 (170) | Model: qwen3...
        status = (
            f"[dim]"
            f"⏱️  {ttft} / {total}  |  "
            f"🪙  {usage.get('prompt_tokens', '?')} + {usage.get('completion_tokens', '?')} = {usage.get('total_tokens', '?')}  |  "
            f"🤖 {metrics.get('model', 'Unknown')}"
            f"[/dim]"
        )
        self.console.print(Panel(status, style="dim white", border_style="dim"))

    async def print_tool_output(self, output: str, tool_name: str = ""):
        if not output:
            return

        if tool_name == "read_file":
            syntax = Syntax(output, "python", theme="monokai", line_numbers=True)
            self.console.print(Panel(syntax, title="File Content", border_style="dim"))
        else:
            formatted = "\n".join([f"  {line}" for line in output.strip().split("\n")])
            self.console.print(f"[tool]{formatted}[/tool]")

    async def print_plan(self, plan_data: Dict[str, Any]):
        """Displays the current plan as a dependency tree."""
        goal = plan_data.get("goal", "Unknown Goal")
        tree = Tree(f"[bold cyan]Plan: {goal}[/bold cyan]")

        tasks = plan_data.get("tasks", [])
        if not tasks:
            self.console.print(tree)
            return

        # Map tasks by ID for easy lookup

        # Identify "roots" of the dependency graph (tasks with no dependencies)
        # Note: If A depends on B, B comes first.
        # But for visualizing "Execution Flow", we might want to show B -> A
        # Roots = Tasks that depend on NOTHING (start here)

        roots = [t for t in tasks if not t.get("dependencies")]

        # Helper to recursively add nodes
        # This handles a Tree structure. If it is a DAG (A->C, B->C), C appears twice.
        def add_nodes(parent_node, current_tasks):
            for task in current_tasks:
                status = task.get("status", "pending").lower()
                status_style = f"task.{status}"
                icon = "○"
                if status == "completed":
                    icon = "✔"
                elif status == "in_progress":
                    icon = "▶"
                elif status == "failed":
                    icon = "✖"

                label = f"[{status_style}]{icon} {task['description']} ({task['id'][:8]})[/{status_style}]"
                node = parent_node.add(label)

                # Find tasks that depend on THIS task
                dependents = [
                    t for t in tasks if task["id"] in t.get("dependencies", [])
                ]
                add_nodes(node, dependents)

        add_nodes(tree, roots)
        self.console.print(tree)

    async def print_error(self, message: str):
        self.console.print(f"[error]\nError: {message}[/error]")

    async def print_goodbye(self):
        self.console.print("[warning]Goodbye![/warning]")

    def create_spinner(self, text: str) -> ContextManager:
        return self.console.status(f"[blue]{text}[/blue]", spinner="dots")
