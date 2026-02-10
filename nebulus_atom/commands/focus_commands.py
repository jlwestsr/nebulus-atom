"""CLI commands for ecosystem-aware queries with business context."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown

focus_app = typer.Typer(help="Ecosystem-aware queries with business context.")


@focus_app.command("query")
def focus_query(
    query: str = typer.Argument(..., help="Natural language question"),
    role: str = typer.Option("pm", "--role", help="Role: pm or default"),
    worker: Optional[str] = typer.Option(
        None, "--worker", "-w", help="Worker to use for the query"
    ),
) -> None:
    """Ask a question with full ecosystem context."""
    from pathlib import Path

    from nebulus_swarm.overlord.focus import build_focus_context
    from nebulus_swarm.overlord.registry import load_config
    from nebulus_swarm.overlord.workers import load_all_workers

    console = Console()

    try:
        config = load_config()
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        raise typer.Exit(1)

    # Build focus context
    workspace = config.workspace_root or Path.cwd()
    ctx = build_focus_context(workspace)
    context_str = ctx.format_for_prompt()

    # Build prompt
    system_parts = []
    if role == "pm":
        system_parts.append(
            "You are a Project Manager for the Nebulus AI ecosystem.\n"
            "Prioritize: sequencing, dependency analysis, risk assessment, "
            "business alignment.\n"
            "Deprioritize: code generation, implementation details, "
            "file-level changes."
        )
    system_parts.append(context_str)

    prompt = "\n\n".join(system_parts) + f"\n\n## User Query\n{query}"

    # Select worker
    workers = load_all_workers(config.workers)
    if not workers:
        console.print(
            "[red]No workers available. Check overlord.yml workers config.[/red]"
        )
        raise typer.Exit(1)

    worker_name = worker
    if worker_name and worker_name not in workers:
        console.print(f"[red]Unknown worker: {worker_name}[/red]")
        raise typer.Exit(1)

    if not worker_name:
        # Prefer claude, then gemini, then local
        for candidate in ("claude", "gemini", "local"):
            if candidate in workers and workers[candidate].available:
                worker_name = candidate
                break
        if not worker_name:
            worker_name = next(iter(workers))

    selected = workers[worker_name]
    console.print(f"[dim]Querying with {worker_name} (role={role})...[/dim]")

    try:
        result = selected.execute(
            prompt=prompt,
            project_path=workspace,
            task_type="planning" if role == "pm" else "feature",
        )

        if result.success:
            console.print()
            console.print(Markdown(result.output))
        else:
            console.print(f"[red]Query failed: {result.error}[/red]")
    except Exception as e:
        console.print(f"[red]Error executing query: {e}[/red]")
        raise typer.Exit(1)


@focus_app.command("show")
def focus_show() -> None:
    """Display parsed ecosystem context."""
    from pathlib import Path

    from nebulus_swarm.overlord.focus import build_focus_context
    from nebulus_swarm.overlord.registry import load_config

    console = Console()

    try:
        config = load_config()
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        raise typer.Exit(1)

    workspace = config.workspace_root or Path.cwd()
    ctx = build_focus_context(workspace)
    output = ctx.format_for_prompt()

    console.print(Markdown(output))
