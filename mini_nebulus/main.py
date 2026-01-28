import asyncio
import typer
from typing import List, Optional
from mini_nebulus.controllers.agent_controller import AgentController
from mini_nebulus.services.doc_service import DocService
from rich.markdown import Markdown
from rich.console import Console

app = typer.Typer(invoke_without_command=True)


@app.callback()
def main(
    ctx: typer.Context,
    prompt: Optional[List[str]] = typer.Argument(
        None, help="Initial prompt to execute immediately"
    ),
):
    """
    Mini-Nebulus: A professional, autonomous AI engineer CLI.
    """
    # If a subcommand (like "start") is invoked, we do nothing here.
    if ctx.invoked_subcommand is not None:
        return

    # If no subcommand, we run the default behavior (interactive mode)
    initial_prompt = " ".join(prompt) if prompt else None
    controller = AgentController()
    asyncio.run(controller.start(initial_prompt))


@app.command()
def start(
    prompt: Optional[List[str]] = typer.Argument(
        None, help="Initial prompt to execute immediately"
    ),
    tui: bool = typer.Option(False, help="Enable Interactive Dashboard (TUI)"),
):
    """
    Start the Mini-Nebulus AI Agent.
    """
    initial_prompt = " ".join(prompt) if prompt else None

    view = None
    if tui:
        from mini_nebulus.views.tui_view import TUIView

        view = TUIView()

    controller = AgentController(view=view)

    if tui:
        # Link controller to view for event callbacks
        view.set_controller(controller)

    asyncio.run(controller.start(initial_prompt))


@app.command()
def docs(
    action: str = typer.Argument(..., help="Action: 'list' or 'read'"),
    filename: Optional[str] = typer.Argument(None, help="Filename to read"),
):
    """
    Access embedded documentation.
    """
    service = DocService()
    console = Console()

    if action.lower() == "list":
        files = service.list_docs()
        if not files:
            console.print("No documentation files found.", style="yellow")
            return

        console.print("[bold cyan]Available Documentation:[/bold cyan]")
        for f in files:
            console.print(f" - {f}")

    elif action.lower() == "read":
        if not filename:
            console.print(
                "Error: Filename required for 'read' action.", style="bold red"
            )
            return

        content = service.read_doc(filename)
        if content:
            md = Markdown(content)
            console.print(md)
        else:
            console.print(f"Error: Could not read '{filename}'", style="bold red")
    else:
        console.print(
            f"Unknown action: {action}. Use 'list' or 'read'.", style="bold red"
        )


if __name__ == "__main__":
    app()
