"""CLI commands for the Overlord work queue.

Provides `atom queue list|triage|sync|log` subcommands.
Follows the same Typer/Rich patterns as overlord_commands.py.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

queue_app = typer.Typer(help="Manage the Overlord work queue.")
console = Console()

# Status → Rich color mapping
STATUS_COLORS: dict[str, str] = {
    "backlog": "dim",
    "active": "cyan",
    "dispatched": "yellow",
    "in_review": "magenta",
    "completed": "green",
    "failed": "red",
}


def _resolve_task_id(queue, short_id: str) -> Optional[str]:
    """Resolve a short ID prefix to a full task UUID.

    Supports first-8-char matching like git short hashes.

    Args:
        queue: WorkQueue instance.
        short_id: Full or prefix of a task UUID.

    Returns:
        Full task ID if exactly one match, None otherwise.
    """
    # Try exact match first
    task = queue.get_task(short_id)
    if task:
        return short_id

    # Prefix match
    tasks = queue.list_tasks(limit=500)
    matches = [t for t in tasks if t.id.startswith(short_id)]
    if len(matches) == 1:
        return matches[0].id
    if len(matches) > 1:
        console.print(
            f"[yellow]Ambiguous ID prefix '{short_id}' "
            f"— matches {len(matches)} tasks[/yellow]"
        )
        return None
    return None


def _load_queue():
    """Load the work queue, printing an error on failure."""
    from nebulus_swarm.overlord.work_queue import WorkQueue

    try:
        return WorkQueue()
    except Exception as e:
        console.print(f"[red]Failed to open work queue: {e}[/red]")
        return None


@queue_app.command("list")
def queue_list(
    status: Optional[str] = typer.Option(
        None, "--status", "-s", help="Filter by status"
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Filter by project"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
) -> None:
    """List tasks in the work queue."""
    queue = _load_queue()
    if not queue:
        return

    tasks = queue.list_tasks(status=status, project=project, limit=limit)

    if not tasks:
        console.print("[dim]No tasks found.[/dim]")
        return

    table = Table(title="Work Queue")
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("Status")
    table.add_column("Priority")
    table.add_column("Project")
    table.add_column("Title", max_width=50)
    table.add_column("Retries", justify="right")
    table.add_column("Locked By")

    for t in tasks:
        color = STATUS_COLORS.get(t.status, "white")
        table.add_row(
            t.id[:8],
            f"[{color}]{t.status}[/{color}]",
            t.priority,
            t.project,
            t.title,
            str(t.retry_count),
            t.locked_by or "[dim]-[/dim]",
        )

    console.print(table)
    console.print(f"[dim]{len(tasks)} task(s)[/dim]")


@queue_app.command("triage")
def queue_triage(
    task_id: str = typer.Argument(..., help="Task ID (or first 8 chars)"),
    status: str = typer.Option(..., "--status", "-s", help="Target status"),
    reason: Optional[str] = typer.Option(
        None, "--reason", "-r", help="Reason for transition"
    ),
) -> None:
    """Transition a task to a new status."""
    queue = _load_queue()
    if not queue:
        return

    full_id = _resolve_task_id(queue, task_id)
    if not full_id:
        console.print(f"[red]Task not found: {task_id}[/red]")
        return

    try:
        task = queue.transition(full_id, status, "cli-user", reason=reason)
        color = STATUS_COLORS.get(task.status, "white")
        console.print(
            f"[green]Task {full_id[:8]} → [{color}]{task.status}[/{color}][/green]"
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@queue_app.command("sync")
def queue_sync(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Sync single project"
    ),
    label: str = typer.Option(
        "nebulus-ready", "--label", help="GitHub label to filter"
    ),
) -> None:
    """Sync GitHub issues into the work queue."""
    from nebulus_swarm.overlord.queue_sync import sync_github_issues
    from nebulus_swarm.overlord.registry import load_config

    queue = _load_queue()
    if not queue:
        return

    try:
        config = load_config()
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        return

    result = sync_github_issues(queue, config, label=label, project_filter=project)

    console.print(
        f"[green]Sync complete:[/green] "
        f"{result.new_count} new, "
        f"{result.updated_count} updated, "
        f"{result.skipped_count} skipped"
    )
    if result.errors:
        for err in result.errors:
            console.print(f"  [red]{err}[/red]")


@queue_app.command("log")
def queue_log(
    task_id: str = typer.Argument(..., help="Task ID (or first 8 chars)"),
) -> None:
    """Show the audit trail for a task."""
    queue = _load_queue()
    if not queue:
        return

    full_id = _resolve_task_id(queue, task_id)
    if not full_id:
        console.print(f"[red]Task not found: {task_id}[/red]")
        return

    entries = queue.get_task_log(full_id)
    if not entries:
        console.print(f"[dim]No log entries for {full_id[:8]}[/dim]")
        return

    table = Table(title=f"Audit Log — {full_id[:8]}")
    table.add_column("Timestamp", no_wrap=True)
    table.add_column("From")
    table.add_column("To")
    table.add_column("By")
    table.add_column("Reason")

    for e in entries:
        from_color = STATUS_COLORS.get(e.old_status, "white")
        to_color = STATUS_COLORS.get(e.new_status, "white")
        table.add_row(
            e.timestamp[:19],
            f"[{from_color}]{e.old_status}[/{from_color}]",
            f"[{to_color}]{e.new_status}[/{to_color}]",
            e.changed_by,
            e.reason or "[dim]-[/dim]",
        )

    console.print(table)
