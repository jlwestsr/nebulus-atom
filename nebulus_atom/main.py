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
def main(ctx: typer.Context):
    """
    Nebulus Atom: A professional, autonomous AI engineer CLI.
    """
    pass


@app.command()
def start(
    prompt: Optional[List[str]] = typer.Argument(
        None, help="Initial prompt to execute immediately"
    ),
    session_id: str = typer.Option("default", help="Session ID for persistence"),
):
    """
    Start the Nebulus Atom AI Agent.
    """
    _start_agent(prompt, session_id)


def _start_agent(prompt: Optional[List[str]], session_id: str = "default"):
    initial_prompt = " ".join(prompt) if prompt else None

    from nebulus_atom.views.cli_view import CLIView
    from nebulus_atom.controllers.agent_controller import AgentController

    view = CLIView()
    controller = AgentController(view=view)

    try:
        asyncio.run(controller.start(initial_prompt, session_id=session_id))
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


@app.command("review-pr")
def review_pr(
    pr_number: int = typer.Argument(..., help="Pull request number to review"),
    repo: Optional[str] = typer.Option(
        None, help="Repository in owner/name format (auto-detected from git remote)"
    ),
    no_checks: bool = typer.Option(
        False, "--no-checks", help="Skip local checks (pytest, ruff, security)"
    ),
):
    """
    Review a pull request using LLM analysis and local checks.
    """
    from rich.panel import Panel

    from nebulus_atom.commands.review_pr import (
        format_review_output,
        run_review,
    )

    console = Console()
    console.print(f"[bold cyan]Reviewing PR #{pr_number}...[/bold cyan]")

    result = run_review(
        pr_number=pr_number,
        repo=repo,
        run_checks=not no_checks,
    )

    output = format_review_output(result)

    decision = result.llm_result.decision
    if decision == "APPROVE" or (
        hasattr(decision, "value") and decision.value == "APPROVE"
    ):
        style = "green"
    elif decision == "REQUEST_CHANGES" or (
        hasattr(decision, "value") and decision.value == "REQUEST_CHANGES"
    ):
        style = "red"
    else:
        style = "yellow"

    console.print(Panel(output, title="PR Review", border_style=style))


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


@app.command()
def proposals(
    action: str = typer.Argument(
        ..., help="Action: 'list', 'approve <id>', 'reject <id>'"
    ),
    proposal_id: Optional[str] = typer.Argument(
        None, help="Proposal ID (for approve/reject)"
    ),
):
    """
    Manage enhancement proposals.
    """

    console = Console()
    console.print(f"[yellow]proposals {action} — not yet wired to store[/yellow]")


if __name__ == "__main__":
    app()
