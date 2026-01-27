import asyncio
import typer
from typing import List, Optional
from mini_nebulus.controllers.agent_controller import AgentController

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


if __name__ == "__main__":
    app()
