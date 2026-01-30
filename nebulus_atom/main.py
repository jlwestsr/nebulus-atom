import os
import asyncio
import typer
from typing import List, Optional
from nebulus_atom.services.doc_service import DocService
from rich.markdown import Markdown
from rich.console import Console

# Silence HuggingFace warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

app = typer.Typer(invoke_without_command=True)


@app.callback()
def main(
    ctx: typer.Context,
    prompt: Optional[List[str]] = typer.Argument(
        None, help="Initial prompt to execute immediately"
    ),
    tui: bool = typer.Option(False, help="Enable Interactive Dashboard (TUI)"),
    session_id: str = typer.Option("default", help="Session ID"),
):
    """
    Nebulus Atom: A professional, autonomous AI engineer CLI.
    """
    # If a subcommand (like "start") is invoked, we do nothing here.
    if ctx.invoked_subcommand is not None:
        return

    # If no subcommand, we run the default behavior (interactive mode)
    _start_agent(prompt, tui, session_id)


@app.command()
def start(
    prompt: Optional[List[str]] = typer.Argument(
        None, help="Initial prompt to execute immediately"
    ),
    tui: bool = typer.Option(False, help="Enable Interactive Dashboard (Deprecated)"),
    session_id: str = typer.Option("default", help="Session ID for persistence"),
):
    """
    Start the Nebulus Atom AI Agent.
    """
    _start_agent(prompt, tui, session_id)


def _start_agent(prompt: Optional[List[str]], tui: bool, session_id: str = "default"):
    initial_prompt = " ".join(prompt) if prompt else None

    if tui:
        from nebulus_atom.views.tui_view import TextualView

        view = TextualView()
    else:
        from nebulus_atom.views.cli_view import CLIView

        view = CLIView()

    # from nebulus_atom.controllers.agent_controller import AgentController
    from nebulus_atom.swarm.orchestrator import SwarmOrchestrator

    # controller = AgentController(view=view)
    # view.set_controller(controller)

    # Swarm Mode
    orchestrator = SwarmOrchestrator(view=view)
    # We bridge the view to the CoderAgent inside the orchestrator
    coder = orchestrator.agents["coder"]
    view.set_controller(coder)

    # Start the orchestrator loop
    try:
        asyncio.run(orchestrator.start(initial_prompt, session_id=session_id))
    except (KeyboardInterrupt, SystemExit):
        pass


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


@app.command()
def dashboard():
    """
    Launch the Flight Recorder Dashboard (Streamlit).
    """
    import os
    import subprocess
    import sys

    # Path to dashboard.py
    dashboard_path = os.path.join(os.path.dirname(__file__), "ui", "dashboard.py")

    if not os.path.exists(dashboard_path):
        console = Console()
        console.print(
            f"Error: Dashboard file not found at {dashboard_path}", style="bold red"
        )
        return

    # Run streamlit
    cmd = [sys.executable, "-m", "streamlit", "run", dashboard_path]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    app()
