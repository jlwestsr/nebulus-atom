"""CLI commands for dispatching tasks from the work queue."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

dispatch_app = typer.Typer(help="Dispatch tasks from the work queue.")


@dispatch_app.command("run")
def dispatch_run(
    task_id: str = typer.Argument(..., help="UUID of the task to dispatch"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Generate brief only, skip execution"
    ),
    worker: Optional[str] = typer.Option(
        None, "--worker", "-w", help="Explicit worker override"
    ),
    skip_review: bool = typer.Option(
        False, "--skip-review", help="Skip the review step"
    ),
) -> None:
    """Dispatch a single task through the full lifecycle."""
    from nebulus_swarm.overlord.dispatcher import Dispatcher
    from nebulus_swarm.overlord.mirrors import MirrorManager
    from nebulus_swarm.overlord.registry import load_config
    from nebulus_swarm.overlord.work_queue import WorkQueue
    from nebulus_swarm.overlord.workers import load_all_workers

    console = Console()

    try:
        config = load_config()
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        raise typer.Exit(1)

    queue = WorkQueue()
    mirrors = MirrorManager(config)
    workers = load_all_workers(config.workers)

    if not workers:
        console.print(
            "[red]No workers available. Check overlord.yml workers config.[/red]"
        )
        raise typer.Exit(1)

    dispatcher = Dispatcher(
        queue,
        config,
        mirrors,
        workers,
        daily_ceiling_usd=config.cost_controls.daily_ceiling_usd,
        warning_threshold_pct=config.cost_controls.warning_threshold_pct,
    )

    try:
        result = dispatcher.dispatch_task(
            task_id,
            dry_run=dry_run,
            worker_name=worker,
            skip_review=skip_review,
        )
        console.print(f"[green]Dispatch complete:[/green] {task_id[:8]}")
        console.print(f"  Worker: {result.worker_id}")
        console.print(f"  Branch: {result.branch_name}")
        console.print(f"  Review: {result.review_status}")
        if result.tokens_used:
            console.print(f"  Tokens: {result.tokens_used:,}")
        if dry_run:
            console.print(f"  Brief: {result.mission_brief_path}")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]Runtime error: {e}[/red]")
        raise typer.Exit(1)


@dispatch_app.command("cleanup")
def dispatch_cleanup(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Filter by project"
    ),
    all_worktrees: bool = typer.Option(False, "--all", help="Clean up all worktrees"),
) -> None:
    """Clean up stale worktrees."""
    from nebulus_swarm.overlord.mirrors import MirrorManager
    from nebulus_swarm.overlord.registry import load_config

    console = Console()

    try:
        config = load_config()
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        raise typer.Exit(1)

    mgr = MirrorManager(config)
    worktrees = mgr.list_worktrees(project=project)

    if not worktrees:
        console.print("[dim]No worktrees found.[/dim]")
        return

    total = sum(len(paths) for paths in worktrees.values())
    console.print(f"Found {total} worktree(s) across {len(worktrees)} project(s)")

    if not all_worktrees:
        console.print("[yellow]Use --all to clean up all worktrees.[/yellow]")
        for proj, paths in worktrees.items():
            for p in paths:
                console.print(f"  {proj}: {p}")
        return

    cleaned = 0
    for proj, paths in worktrees.items():
        for wt_path in paths:
            ok = mgr.cleanup_worktree(proj, wt_path)
            status = "[green]removed[/green]" if ok else "[red]failed[/red]"
            console.print(f"  {proj}/{wt_path.name}: {status}")
            if ok:
                cleaned += 1

    console.print(f"Cleaned {cleaned}/{total} worktrees.")
