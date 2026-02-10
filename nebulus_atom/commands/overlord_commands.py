"""CLI commands for the Overlord cross-project orchestrator."""

from __future__ import annotations

import re
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from nebulus_swarm.overlord.action_scope import (
    ActionScope,
    ScopeVerdict,
    evaluate_scope,
    scope_for_merge,
    scope_for_push,
    scope_for_release,
)
from nebulus_swarm.overlord.autonomy import AutonomyEngine
from nebulus_swarm.overlord.dispatch import DispatchEngine
from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.memory import OverlordMemory
from nebulus_swarm.overlord.model_router import ModelRouter
from nebulus_swarm.overlord.registry import (
    DEFAULT_CONFIG_PATH,
    OverlordConfig,
    get_dependency_order,
    load_config,
    validate_config,
)
from nebulus_swarm.overlord.release import (
    ReleaseCoordinator,
    ReleaseSpec,
    validate_release_spec,
)
from nebulus_swarm.overlord.scanner import (
    ProjectStatus,
    scan_ecosystem,
    scan_project,
)
from nebulus_swarm.overlord.task_parser import TaskParser

overlord_app = typer.Typer(help="Cross-project ecosystem orchestrator.")
console = Console()


@overlord_app.command()
def status(
    project: Optional[str] = typer.Argument(None, help="Single project to check"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show extra detail"),
) -> None:
    """Show ecosystem health summary."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    if project:
        if project not in registry.projects:
            console.print(f"[red]Unknown project: {project}[/red]")
            console.print(f"Available: {', '.join(sorted(registry.projects.keys()))}")
            return
        results = [scan_project(registry.projects[project])]
    else:
        results = scan_ecosystem(registry)

    _render_status_table(results, verbose)


@overlord_app.command()
def scan(
    project: Optional[str] = typer.Argument(None, help="Single project to scan"),
) -> None:
    """Deep scan projects for issues."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    if project:
        if project not in registry.projects:
            console.print(f"[red]Unknown project: {project}[/red]")
            return
        results = [scan_project(registry.projects[project])]
    else:
        results = scan_ecosystem(registry)

    _render_scan_detail(results)


@overlord_app.command()
def discover(
    workspace: Optional[str] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace directory to scan (default: ~/projects/west_ai_labs)",
    ),
) -> None:
    """Auto-discover repos and generate overlord.yml."""
    workspace_path = (
        Path(workspace).expanduser()
        if workspace
        else (Path.home() / "projects" / "west_ai_labs")
    )

    if not workspace_path.is_dir():
        console.print(f"[red]Workspace not found: {workspace_path}[/red]")
        return

    console.print(f"[cyan]Scanning {workspace_path} for git repos...[/cyan]")
    discovered = _discover_repos(workspace_path)

    if not discovered:
        console.print("[yellow]No git repositories found.[/yellow]")
        return

    config_yaml = _generate_config_yaml(discovered)

    # Write to file or print to stdout
    if not DEFAULT_CONFIG_PATH.exists():
        DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_CONFIG_PATH.write_text(config_yaml)
        console.print(f"[green]Config written to {DEFAULT_CONFIG_PATH}[/green]")
    else:
        console.print(
            f"[yellow]Config already exists at {DEFAULT_CONFIG_PATH}. "
            f"Printing to stdout instead:[/yellow]\n"
        )
        console.print(config_yaml)

    console.print(f"\n[cyan]Discovered {len(discovered)} projects.[/cyan]")


@overlord_app.command("config")
def show_config() -> None:
    """Show current Overlord configuration."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    errors = validate_config(registry)

    # Build config tree
    tree = Tree("[bold cyan]Overlord Configuration[/bold cyan]")

    # Autonomy settings
    autonomy_branch = tree.add("[bold]Autonomy[/bold]")
    autonomy_branch.add(f"Global: {registry.autonomy_global}")
    if registry.autonomy_overrides:
        for proj, level in registry.autonomy_overrides.items():
            autonomy_branch.add(f"{proj}: {level}")

    # Projects
    projects_branch = tree.add("[bold]Projects[/bold]")
    try:
        order = get_dependency_order(registry)
    except ValueError:
        order = sorted(registry.projects.keys())

    for name in order:
        proj = registry.projects[name]
        proj_branch = projects_branch.add(f"[bold]{name}[/bold]")
        proj_branch.add(f"Path: {proj.path}")
        proj_branch.add(f"Remote: {proj.remote}")
        proj_branch.add(f"Role: {proj.role}")
        proj_branch.add(f"Branch model: {proj.branch_model}")
        if proj.depends_on:
            proj_branch.add(f"Depends on: {', '.join(proj.depends_on)}")

    console.print(tree)

    if errors:
        console.print()
        console.print(
            Panel(
                "\n".join(f"  - {e}" for e in errors),
                title="Validation Errors",
                border_style="red",
            )
        )
    else:
        console.print("\n[green]Config is valid.[/green]")


@overlord_app.command("graph")
def show_graph(
    project: Optional[str] = typer.Argument(
        None, help="Project to analyze (shows full graph if omitted)"
    ),
) -> None:
    """Show dependency graph or impact analysis for a project."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    dep_graph = DependencyGraph(registry)

    if project:
        if project not in registry.projects:
            console.print(f"[red]Unknown project: {project}[/red]")
            console.print(f"Available: {', '.join(sorted(registry.projects.keys()))}")
            return

        upstream = dep_graph.get_upstream(project)
        downstream = dep_graph.get_downstream(project)
        affected = dep_graph.get_affected_by(project)

        console.print(f"\n[bold cyan]Impact Analysis: {project}[/bold cyan]\n")
        console.print(
            f"[bold]Upstream[/bold] (dependencies): "
            f"{', '.join(upstream) if upstream else '(none)'}"
        )
        console.print(
            f"[bold]Downstream[/bold] (dependents): "
            f"{', '.join(downstream) if downstream else '(none)'}"
        )
        console.print(f"[bold]Affected by change[/bold]: {', '.join(affected)}")
    else:
        console.print("\n[bold cyan]Dependency Graph[/bold cyan]\n")
        console.print(dep_graph.render_ascii())


@overlord_app.command("memory")
def manage_memory(
    action: str = typer.Argument(help="Action: search, recent, forget, prune"),
    query: Optional[str] = typer.Argument(None, help="Search query or entry ID"),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Filter by project"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Manage cross-project memory."""
    mem = OverlordMemory()

    if action == "search":
        if not query:
            console.print("[red]Search requires a query argument.[/red]")
            return
        results = mem.search(query, project=project, limit=limit)
        _render_memory_entries(results)

    elif action == "recent":
        results = mem.get_recent(limit=limit)
        _render_memory_entries(results)

    elif action == "forget":
        if not query:
            console.print("[red]Forget requires an entry ID argument.[/red]")
            return
        if mem.forget(query):
            console.print(f"[green]Deleted memory {query}[/green]")
        else:
            console.print(f"[yellow]No memory found with ID {query}[/yellow]")

    elif action == "prune":
        days = int(query) if query else 90
        deleted = mem.prune(older_than_days=days)
        console.print(
            f"[green]Pruned {deleted} entries older than {days} days.[/green]"
        )

    else:
        console.print(
            f"[red]Unknown action: {action}[/red]\n"
            "Valid actions: search, recent, forget, prune"
        )


@overlord_app.command("scope")
def show_scope(
    action: str = typer.Argument(help="Action to preview: merge, push, release"),
    project: str = typer.Argument(help="Target project"),
) -> None:
    """Preview blast radius for an action."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    if project not in registry.projects:
        console.print(f"[red]Unknown project: {project}[/red]")
        console.print(f"Available: {', '.join(sorted(registry.projects.keys()))}")
        return

    dep_graph = DependencyGraph(registry)

    if action == "merge":
        scope = scope_for_merge(project, "develop", "main")
    elif action == "push":
        scope = scope_for_push([project])
    elif action == "release":
        scope = scope_for_release(project, dep_graph)
    else:
        console.print(
            f"[red]Unknown action: {action}[/red]\nValid actions: merge, push, release"
        )
        return

    # Evaluate against current autonomy level
    autonomy = registry.autonomy_overrides.get(project, registry.autonomy_global)
    verdict = evaluate_scope(scope, autonomy, registry)

    _render_scope(scope, verdict, autonomy)


@overlord_app.command("autonomy")
def manage_autonomy(
    global_level: Optional[str] = typer.Option(
        None, "--global", help="Set global autonomy level"
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project to configure"
    ),
    level: Optional[str] = typer.Option(
        None, "--level", "-l", help="Autonomy level for project"
    ),
    list_approved: bool = typer.Option(
        False, "--list-approved", help="Show pre-approved actions"
    ),
) -> None:
    """Manage autonomy settings."""
    from nebulus_swarm.overlord.autonomy import AutonomyEngine, get_autonomy_summary

    registry = _load_registry_or_exit()
    if registry is None:
        return

    engine = AutonomyEngine(registry)

    # List pre-approved actions
    if list_approved:
        if not registry.autonomy_pre_approved:
            console.print("[dim]No pre-approved actions configured.[/dim]")
            return

        table = Table(title="Pre-Approved Actions")
        table.add_column("Project", style="bold")
        table.add_column("Level")
        table.add_column("Pre-Approved Actions")

        for proj_name in sorted(registry.autonomy_pre_approved.keys()):
            level = engine.get_level(proj_name)
            actions = registry.autonomy_pre_approved[proj_name]
            table.add_row(
                proj_name,
                level,
                "\n".join(f"  • {a}" for a in actions) if actions else "-",
            )

        console.print(table)
        return

    # Set global level
    if global_level:
        console.print(
            f"[yellow]Setting global autonomy level requires editing "
            f"{DEFAULT_CONFIG_PATH}[/yellow]\n"
            f"Current global level: {registry.autonomy_global}\n"
            f"Requested level: {global_level}\n\n"
            f"To apply, edit autonomy.global in the config file."
        )
        return

    # Set project-specific level
    if project and level:
        console.print(
            f"[yellow]Setting project autonomy level requires editing "
            f"{DEFAULT_CONFIG_PATH}[/yellow]\n"
            f"Current level for {project}: {engine.get_level(project)}\n"
            f"Requested level: {level}\n\n"
            f"To apply, add to autonomy.overrides in the config file."
        )
        return

    # Show current settings (default behavior)
    summary = get_autonomy_summary(registry)

    table = Table(title="Autonomy Settings")
    table.add_column("Project", style="bold")
    table.add_column("Level")
    table.add_column("Source")

    # Global row first
    table.add_row("(global)", summary["__global__"], "config default")

    # Per-project rows
    for proj_name in sorted(registry.projects.keys()):
        level = summary[proj_name]
        source = (
            "project override" if proj_name in registry.autonomy_overrides else "global"
        )
        table.add_row(proj_name, level, source)

    console.print(table)


# --- Helpers ---


def _load_registry_or_exit() -> Optional[OverlordConfig]:
    """Load the registry config, printing an error if it fails."""
    try:
        registry = load_config()
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        return None

    if not registry.projects:
        console.print(
            "[yellow]No projects registered. "
            f"Run 'overlord discover' or create {DEFAULT_CONFIG_PATH}[/yellow]"
        )
        return None

    return registry


def _render_status_table(results: list[ProjectStatus], verbose: bool) -> None:
    """Render a Rich table of project statuses."""
    table = Table(title="Ecosystem Status")
    table.add_column("Project", style="bold")
    table.add_column("Branch")
    table.add_column("Status")
    table.add_column("Last Commit")
    table.add_column("Issues")

    if verbose:
        table.add_column("Tags")

    for r in results:
        # Status indicator
        if not r.issues:
            status_str = "[green]OK[/green]"
        else:
            status_str = f"[yellow]{len(r.issues)} issue(s)[/yellow]"

        # Clean/dirty indicator in branch
        branch_str = r.git.branch
        if not r.git.clean:
            branch_str += " [red]*[/red]"

        issues_str = "; ".join(r.issues) if r.issues else "-"

        row = [
            r.name,
            branch_str,
            status_str,
            r.git.last_commit[:50] if r.git.last_commit else "-",
            issues_str,
        ]

        if verbose:
            row.append(", ".join(r.git.tags) if r.git.tags else "-")

        table.add_row(*row)

    console.print(table)


def _render_scan_detail(results: list[ProjectStatus]) -> None:
    """Render detailed scan results with Rich panels."""
    for r in results:
        # Determine border style based on issues
        if not r.issues:
            border = "green"
        elif any("Dirty" in i for i in r.issues):
            border = "red"
        else:
            border = "yellow"

        lines = [
            f"[bold]Branch:[/bold] {r.git.branch}",
            f"[bold]Clean:[/bold] {'Yes' if r.git.clean else '[red]No[/red]'}",
            f"[bold]Ahead/Behind:[/bold] {r.git.ahead}/{r.git.behind}",
            f"[bold]Last Commit:[/bold] {r.git.last_commit}",
            f"[bold]Commit Date:[/bold] {r.git.last_commit_date}",
            f"[bold]Role:[/bold] {r.config.role}",
            f"[bold]Branch Model:[/bold] {r.config.branch_model}",
        ]

        if r.git.tags:
            lines.append(f"[bold]Tags:[/bold] {', '.join(r.git.tags)}")

        if r.git.stale_branches:
            lines.append(
                f"[bold]Stale Branches:[/bold] {', '.join(r.git.stale_branches)}"
            )

        if r.tests.has_tests:
            lines.append(f"[bold]Test Command:[/bold] {r.tests.test_command}")
        else:
            lines.append("[bold]Tests:[/bold] [dim]Not detected[/dim]")

        if r.issues:
            lines.append("")
            lines.append("[bold yellow]Issues:[/bold yellow]")
            for issue in r.issues:
                lines.append(f"  - {issue}")

        console.print(
            Panel(
                "\n".join(lines),
                title=f"[bold]{r.name}[/bold]",
                subtitle=r.config.remote,
                border_style=border,
            )
        )


def _discover_repos(workspace_path: Path) -> list[dict]:
    """Discover git repos in a workspace directory.

    Returns a list of dicts with name, path, remote info.
    """
    discovered = []

    for child in sorted(workspace_path.iterdir()):
        if not child.is_dir():
            continue
        git_dir = child / ".git"
        if not git_dir.exists():
            continue

        # Get remote URL
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(child),
                capture_output=True,
                text=True,
                timeout=5,
            )
            remote_url = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            remote_url = ""

        # Parse remote to owner/repo format
        remote = _parse_remote_url(remote_url)

        # Infer role from directory name and contents
        role = _infer_role(child)

        discovered.append(
            {
                "name": child.name,
                "path": str(child),
                "remote": remote,
                "role": role,
            }
        )

    return discovered


def _parse_remote_url(url: str) -> str:
    """Parse a git remote URL into owner/repo format."""
    if not url:
        return ""

    # Handle SSH format: git@github.com:owner/repo.git
    if url.startswith("git@"):
        parts = url.split(":")
        if len(parts) == 2:
            return parts[1].removesuffix(".git")

    # Handle HTTPS format: https://github.com/owner/repo.git
    if "github.com" in url:
        parts = url.rstrip("/").split("/")
        if len(parts) >= 2:
            repo = parts[-1].removesuffix(".git")
            owner = parts[-2]
            return f"{owner}/{repo}"

    return url


def _infer_role(project_path: Path) -> str:
    """Infer a project role from its contents."""
    name = project_path.name.lower()

    if "core" in name:
        return "shared-library"
    if "gantry" in name or "frontend" in name or "ui" in name:
        return "frontend"
    if "prime" in name or "edge" in name:
        return "platform-deployment"
    if "forge" in name or "atom" in name:
        return "tooling"
    if "mac-mini" in name or "lnx" in name or "ansible" in name:
        return "provisioning"

    return "tooling"


def _generate_config_yaml(discovered: list[dict]) -> str:
    """Generate overlord.yml content from discovered repos."""
    projects = {}
    for repo in discovered:
        name = repo["name"]
        projects[name] = {
            "path": repo["path"],
            "remote": repo["remote"],
            "role": repo["role"],
            "branch_model": "develop-main",
            "depends_on": [],
        }

    # Inject known dependency relationships
    known_deps = {
        "nebulus-prime": ["nebulus-core"],
        "nebulus-edge": ["nebulus-core"],
        "nebulus-atom": ["nebulus-core"],
        "nebulus-gantry": ["nebulus-core", "nebulus-prime"],
        "nebulus-forge": ["nebulus-core"],
    }
    for name, deps in known_deps.items():
        if name in projects:
            existing_projects = set(projects.keys())
            projects[name]["depends_on"] = [d for d in deps if d in existing_projects]

    config = {
        "projects": projects,
        "autonomy": {
            "global": "cautious",
            "overrides": {},
        },
    }

    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def _render_memory_entries(entries: list) -> None:
    """Render a list of MemoryEntry objects as a Rich table."""
    if not entries:
        console.print("[dim]No memories found.[/dim]")
        return

    table = Table(title="Overlord Memory")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Timestamp", max_width=20)
    table.add_column("Category")
    table.add_column("Project")
    table.add_column("Content")

    for entry in entries:
        table.add_row(
            entry.id[:8],
            entry.timestamp[:19],
            entry.category,
            entry.project or "(global)",
            entry.content[:80],
        )

    console.print(table)


@overlord_app.command("worker")
def show_worker() -> None:
    """Show Claude Code worker status and configuration."""
    import shutil

    from nebulus_swarm.overlord.worker_claude import ClaudeWorker, load_worker_config

    registry = _load_registry_or_exit()
    if registry is None:
        return

    worker_cfg = load_worker_config(registry.workers)

    if not worker_cfg:
        console.print(
            "[dim]No Claude worker configured.[/dim]\n"
            "Add a 'workers.claude' section to ~/.atom/overlord.yml to enable."
        )
        return

    # Status table
    table = Table(title="Claude Code Worker")
    table.add_column("Setting", style="bold")
    table.add_column("Value")

    table.add_row(
        "Enabled", "[green]yes[/green]" if worker_cfg.enabled else "[dim]no[/dim]"
    )
    table.add_row("Binary path", worker_cfg.binary_path)

    binary_found = shutil.which(worker_cfg.binary_path)
    if binary_found:
        table.add_row("Binary resolved", f"[green]{binary_found}[/green]")
    else:
        table.add_row("Binary resolved", "[red]NOT FOUND[/red]")

    table.add_row("Default model", worker_cfg.default_model)
    table.add_row("Timeout", f"{worker_cfg.timeout}s")

    if worker_cfg.model_overrides:
        overrides = ", ".join(
            f"{k}={v}" for k, v in sorted(worker_cfg.model_overrides.items())
        )
        table.add_row("Model overrides", overrides)
    else:
        table.add_row("Model overrides", "[dim](none)[/dim]")

    console.print(table)

    if not worker_cfg.enabled:
        console.print(
            "\n[yellow]Worker is disabled. Set enabled: true to activate.[/yellow]"
        )
        return

    if not binary_found:
        console.print(
            "\n[red]Claude binary not found.[/red] "
            "Install Claude Code or update binary_path in config."
        )
        return

    # Quick connectivity test
    console.print("\n[cyan]Running quick test...[/cyan]")
    worker = ClaudeWorker(worker_cfg)
    if worker.available:
        console.print("[green]Worker is ready.[/green]")
    else:
        console.print("[red]Worker initialization failed.[/red]")


@overlord_app.command()
def dispatch(
    task: str = typer.Argument(
        ..., help="Task to execute (e.g., 'merge Core develop to main')"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Plan only, don't execute"
    ),
    auto_approve: bool = typer.Option(
        False, "--yes", "-y", help="Skip approval prompts"
    ),
) -> None:
    """Execute a task across projects using natural language dispatch."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    # Build dependencies
    graph = DependencyGraph(registry)
    autonomy = AutonomyEngine(registry)
    router = ModelRouter(registry)
    engine = DispatchEngine(registry, autonomy, graph, router)
    parser = TaskParser(graph)

    console.print(f"\n[bold]Parsing task:[/bold] {task}")

    try:
        plan = parser.parse(task)
    except ValueError as e:
        console.print(f"[red]Failed to parse task:[/red] {e}")
        raise typer.Exit(1)

    # Show plan
    console.print(f"\n[bold]Execution Plan:[/bold] {plan.task}")
    console.print(f"Steps: {len(plan.steps)}")
    console.print(f"Estimated duration: {plan.estimated_duration}s")
    console.print(f"Requires approval: {plan.requires_approval}")

    table = Table(title="Steps", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Action", style="white")
    table.add_column("Project", style="green")
    table.add_column("Deps", style="yellow")
    table.add_column("Tier", style="magenta")

    for step in plan.steps:
        deps = ", ".join(step.dependencies) if step.dependencies else "-"
        tier = step.model_tier or "direct"
        table.add_row(step.id, step.action, step.project, deps, tier)

    console.print(table)

    # Show scope
    console.print("\n[bold]Blast Radius:[/bold]")
    console.print(f"  Projects: {', '.join(plan.scope.projects)}")
    console.print(f"  Impact: {plan.scope.estimated_impact}")
    console.print(f"  Destructive: {plan.scope.destructive}")
    console.print(f"  Affects remote: {plan.scope.affects_remote}")

    if dry_run:
        console.print("\n[yellow]Dry run — execution skipped[/yellow]")
        return

    # Execute
    console.print("\n[bold]Executing plan...[/bold]\n")
    result = engine.execute(plan, auto_approve=auto_approve)

    if result.status == "success":
        console.print("\n[green bold]✓ Plan completed successfully[/green bold]")
        for step_result in result.steps:
            console.print(f"  [{step_result.step_id}] {step_result.output}")
    elif result.status == "cancelled":
        console.print(f"\n[yellow]✗ Plan cancelled:[/yellow] {result.reason}")
        raise typer.Exit(1)
    else:
        console.print(f"\n[red bold]✗ Plan failed:[/red bold] {result.reason}")
        for step_result in result.steps:
            if not step_result.success:
                console.print(f"  [{step_result.step_id}] {step_result.error}")
        raise typer.Exit(1)


@overlord_app.command()
def release(
    project: str = typer.Argument(..., help="Project to release"),
    version: str = typer.Argument(..., help="Version to release (e.g., v0.1.0)"),
    source: str = typer.Option("develop", "--source", "-s", help="Source branch"),
    target: str = typer.Option("main", "--target", "-t", help="Target branch"),
    no_dependents: bool = typer.Option(
        False, "--no-dependents", help="Skip updating dependent projects"
    ),
    push: bool = typer.Option(False, "--push", help="Push to remote after release"),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Plan only, don't execute"
    ),
    auto_approve: bool = typer.Option(
        False, "--yes", "-y", help="Skip approval prompts"
    ),
) -> None:
    """Execute a coordinated release across dependent projects."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    # Build spec
    spec = ReleaseSpec(
        project=project,
        version=version,
        source_branch=source,
        target_branch=target,
        update_dependents=not no_dependents,
        push_to_remote=push,
    )

    # Validate spec
    errors = validate_release_spec(spec, registry)
    if errors:
        console.print("[red bold]Invalid release specification:[/red bold]")
        for error in errors:
            console.print(f"  • {error}")
        raise typer.Exit(1)

    # Build dependencies
    graph = DependencyGraph(registry)
    autonomy = AutonomyEngine(registry)
    router = ModelRouter(registry)
    dispatch = DispatchEngine(registry, autonomy, graph, router)
    memory = OverlordMemory()
    coordinator = ReleaseCoordinator(registry, graph, dispatch, memory)

    console.print(f"\n[bold]Planning release:[/bold] {project} {version}")
    console.print(f"  Source: {source} → Target: {target}")
    console.print(f"  Update dependents: {spec.update_dependents}")
    console.print(f"  Push to remote: {push}")

    try:
        plan = coordinator.plan_release(spec)
    except ValueError as e:
        console.print(f"[red]Failed to plan release:[/red] {e}")
        raise typer.Exit(1)

    # Show plan
    console.print("\n[bold]Release Plan:[/bold]")
    console.print(f"Steps: {len(plan.steps)}")
    console.print(f"Estimated duration: {plan.estimated_duration}s")

    table = Table(title="Steps", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Action", style="white")
    table.add_column("Project", style="green")
    table.add_column("Deps", style="yellow")

    for step in plan.steps:
        deps = ", ".join(step.dependencies) if step.dependencies else "-"
        table.add_row(step.id, step.action, step.project, deps)

    console.print(table)

    # Show affected projects
    console.print("\n[bold]Affected Projects:[/bold]")
    for proj in plan.scope.projects:
        console.print(f"  • {proj}")

    if dry_run:
        console.print("\n[yellow]Dry run — execution skipped[/yellow]")
        return

    # Execute
    console.print("\n[bold yellow]⚠ This is a high-impact operation![/bold yellow]")
    console.print("[bold]Executing release...[/bold]\n")
    result = coordinator.execute_release(spec, auto_approve=auto_approve)

    if result.status == "success":
        console.print("\n[green bold]✓ Release completed successfully[/green bold]")
        console.print("\n[bold]Release logged to memory:[/bold]")
        console.print(f"  Project: {project}")
        console.print(f"  Version: {version}")
        if spec.update_dependents:
            downstream = graph.get_downstream(project)
            console.print(f"  Downstream updated: {', '.join(downstream)}")
    elif result.status == "cancelled":
        console.print(f"\n[yellow]✗ Release cancelled:[/yellow] {result.reason}")
        raise typer.Exit(1)
    else:
        console.print(f"\n[red bold]✗ Release failed:[/red bold] {result.reason}")
        for step_result in result.steps:
            if not step_result.success:
                console.print(f"  [{step_result.step_id}] {step_result.error}")
        raise typer.Exit(1)


@overlord_app.command()
def daemon(
    action: str = typer.Argument("start", help="Action: start, status, stop, restart"),
) -> None:
    """Manage the Overlord background daemon."""
    import asyncio

    from nebulus_swarm.overlord.overlord_daemon import OverlordDaemon

    if action == "status":
        pid = OverlordDaemon.read_pid()
        if pid is not None and OverlordDaemon.check_running():
            console.print(f"[bold green]Daemon is running[/bold green] (PID {pid})")
        elif pid is not None:
            console.print(f"[yellow]Stale PID file[/yellow] (PID {pid} is not running)")
        else:
            console.print("[dim]Daemon is not running.[/dim]")
        return

    if action == "stop":
        if not OverlordDaemon.check_running():
            console.print("[dim]Daemon is not running.[/dim]")
            return
        pid = OverlordDaemon.read_pid()
        console.print(f"[yellow]Stopping daemon (PID {pid})...[/yellow]")
        if OverlordDaemon.stop_daemon():
            console.print("[green]Daemon stopped.[/green]")
        else:
            console.print("[red]Failed to stop daemon within timeout.[/red]")
            raise typer.Exit(1)
        return

    if action == "restart":
        if OverlordDaemon.check_running():
            pid = OverlordDaemon.read_pid()
            console.print(f"[yellow]Stopping daemon (PID {pid})...[/yellow]")
            if not OverlordDaemon.stop_daemon():
                console.print("[red]Failed to stop daemon within timeout.[/red]")
                raise typer.Exit(1)
            console.print("[green]Daemon stopped.[/green]")
        # Fall through to start
        action = "start"

    if action == "start":
        import os

        from dotenv import load_dotenv

        from nebulus_swarm.logging import configure_logging

        if OverlordDaemon.check_running():
            pid = OverlordDaemon.read_pid()
            console.print(
                f"[yellow]Daemon is already running[/yellow] (PID {pid}). "
                "Use 'overlord daemon restart' to restart."
            )
            return

        # Auto-load .env from current working directory
        env_path = os.path.join(os.getcwd(), ".env")
        loaded = load_dotenv(env_path)
        if loaded:
            console.print(f"[green]Loaded .env from {env_path}[/green]")
        else:
            console.print(f"[yellow]No .env found at {env_path}[/yellow]")

        # Show env var detection status
        slack_bot = "yes" if os.environ.get("SLACK_BOT_TOKEN") else "no"
        slack_app = "yes" if os.environ.get("SLACK_APP_TOKEN") else "no"
        slack_channel = "yes" if os.environ.get("SLACK_CHANNEL_ID") else "no"
        console.print(
            f"[dim]SLACK_BOT_TOKEN: {slack_bot} | "
            f"SLACK_APP_TOKEN: {slack_app} | "
            f"SLACK_CHANNEL_ID: {slack_channel}[/dim]"
        )

        # Configure logging for daemon mode
        log_dir = os.path.expanduser("~/.atom/overlord")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "daemon.log")
        log_level = os.environ.get("LOG_LEVEL", "INFO")
        configure_logging(level=log_level, log_file=log_file)
        console.print(f"[dim]Logging to {log_file} (level={log_level})[/dim]")

        registry = _load_registry_or_exit()
        if registry is None:
            return

        console.print("[bold cyan]Starting Overlord daemon...[/bold cyan]")

        schedule = registry.schedule
        if schedule.tasks:
            table = Table(title="Scheduled Tasks")
            table.add_column("Task", style="bold")
            table.add_column("Cron")
            table.add_column("Enabled")
            for task in schedule.tasks:
                table.add_row(
                    task.name,
                    task.cron or "(default)",
                    "yes" if task.enabled else "no",
                )
            console.print(table)
        else:
            console.print(
                "[dim]No scheduled tasks configured — scheduler will idle[/dim]"
            )

        d = OverlordDaemon(registry)
        try:
            asyncio.run(d.run())
        except KeyboardInterrupt:
            console.print("\n[yellow]Daemon stopped.[/yellow]")
    else:
        console.print(f"[red]Unknown daemon action: {action}[/red]")
        console.print("Valid actions: start, status, stop, restart")


VALID_REPORT_STATUSES = ("started", "in_progress", "blocked", "completed")


@overlord_app.command("report")
def report(
    status: str = typer.Argument(
        help="Status: started, in_progress, blocked, completed"
    ),
    message: str = typer.Argument(help="Status update text"),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project name (auto-detected from CWD)"
    ),
    task_id: Optional[str] = typer.Option(None, "--task-id", help="Task identifier"),
    track: Optional[str] = typer.Option(
        None, "--track", help="Track name for grouping"
    ),
    agent: Optional[str] = typer.Option(
        None, "--agent", help="Agent name (default: hostname)"
    ),
) -> None:
    """Report agent status to the Dispatch Board."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    # Validate status
    if status not in VALID_REPORT_STATUSES:
        console.print(
            f"[red]Invalid status: {status}[/red]\n"
            f"Must be one of: {', '.join(VALID_REPORT_STATUSES)}"
        )
        return

    # Auto-detect project from CWD if not provided
    if not project:
        cwd = Path.cwd()
        for name, proj_cfg in registry.projects.items():
            proj_path = Path(proj_cfg.path).resolve()
            try:
                cwd.resolve().relative_to(proj_path)
                project = name
                break
            except ValueError:
                continue

    if not project:
        console.print(
            "[red]Could not detect project from CWD. Use --project to specify.[/red]"
        )
        return

    if project not in registry.projects:
        console.print(f"[red]Unknown project: {project}[/red]")
        console.print(f"Available: {', '.join(sorted(registry.projects.keys()))}")
        return

    # Auto-generate task_id and agent name
    if not task_id:
        now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        task_id = f"{project}-{now}"

    if not agent:
        agent = socket.gethostname()

    # Write to memory
    mem = OverlordMemory()
    entry_id = mem.remember(
        category="dispatch",
        content=f"[{status.upper()}] {message}",
        project=project,
        status=status,
        agent_name=agent,
        task_id=task_id,
        track=track or "",
    )

    # Render confirmation
    lines = [
        f"[bold]Status:[/bold] {status.upper()}",
        f"[bold]Project:[/bold] {project}",
        f"[bold]Agent:[/bold] {agent}",
        f"[bold]Task ID:[/bold] {task_id}",
        f"[bold]Message:[/bold] {message}",
    ]
    if track:
        lines.append(f"[bold]Track:[/bold] {track}")
    lines.append(f"[dim]Memory ID: {entry_id[:8]}[/dim]")

    console.print(Panel("\n".join(lines), title="Dispatch Report", border_style="cyan"))

    # Post to Slack if configured
    _post_report_to_slack(status, message, project, agent, task_id, track)


def _post_report_to_slack(
    status: str,
    message: str,
    project: str,
    agent: str,
    task_id: str,
    track: Optional[str],
) -> None:
    """Post a dispatch report to #nebulus-ops via Slack."""
    import asyncio
    import os

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    channel_id = os.environ.get("SLACK_CHANNEL_ID")

    if not all([bot_token, app_token, channel_id]):
        console.print("[dim]Slack not configured — skipping notification.[/dim]")
        return

    from nebulus_swarm.overlord.slack_bot import SlackBot

    status_emoji = {
        "started": ":rocket:",
        "in_progress": ":construction:",
        "blocked": ":warning:",
        "completed": ":white_check_mark:",
    }
    emoji = status_emoji.get(status, ":memo:")
    track_line = f"\n*Track:* {track}" if track else ""
    text = (
        f"{emoji} *Dispatch Report*\n"
        f"*Status:* {status.upper()}\n"
        f"*Project:* {project}\n"
        f"*Agent:* {agent}{track_line}\n"
        f"> {message}"
    )

    try:
        bot = SlackBot(
            bot_token=bot_token,
            app_token=app_token,
            channel_id=channel_id,
        )
        asyncio.run(bot.post_message(text))
        console.print("[dim]Posted to #nebulus-ops.[/dim]")
    except Exception as e:
        console.print(f"[yellow]Slack notification failed: {e}[/yellow]")


@overlord_app.command("board")
def board(
    sync: bool = typer.Option(False, "--sync", help="Write to OVERLORD.md"),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Preview sync without writing"
    ),
    days: int = typer.Option(7, "--days", help="Show entries from last N days"),
    all_entries: bool = typer.Option(False, "--all", help="Include completed entries"),
) -> None:
    """Show or sync the Dispatch Board."""
    registry = _load_registry_or_exit()
    if registry is None:
        return

    mem = OverlordMemory()
    entries = mem.search("", category="dispatch", limit=200)

    # Filter by time window
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()
    entries = [e for e in entries if e.timestamp >= cutoff_iso]

    # Separate active vs completed
    active = []
    completed = []
    for entry in entries:
        entry_status = entry.metadata.get("status", "")
        if entry_status == "completed":
            completed.append(entry)
        else:
            active.append(entry)

    display_entries = active + completed if all_entries else active

    # Build and display table
    table = Table(title="Dispatch Board")
    table.add_column("Track / Task", style="bold")
    table.add_column("Project")
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Started", max_width=16)

    for entry in display_entries:
        entry_track = entry.metadata.get("track", "")
        entry_task_id = entry.metadata.get("task_id", "")
        label = entry_track if entry_track else entry_task_id
        entry_status = entry.metadata.get("status", "unknown")
        agent_name = entry.metadata.get("agent_name", "")
        started = entry.timestamp[:16].replace("T", " ")

        status_style = {
            "started": "[cyan]Started[/cyan]",
            "in_progress": "[yellow]In Progress[/yellow]",
            "blocked": "[red]Blocked[/red]",
            "completed": "[green]Completed[/green]",
        }

        table.add_row(
            label,
            entry.project or "",
            agent_name,
            status_style.get(entry_status, entry_status),
            started,
        )

    console.print(table)

    # Build agent roster
    agents: dict[str, list[str]] = {}
    for entry in active:
        agent_name = entry.metadata.get("agent_name", "Unknown")
        proj = entry.project or "unknown"
        entry_track = entry.metadata.get("track", "")
        desc = f"{proj} ({entry_track})" if entry_track else proj
        agents.setdefault(agent_name, []).append(desc)

    if agents:
        console.print("\n[bold]Agent Roster[/bold]")
        for agent_name, assignments in sorted(agents.items()):
            console.print(f"  - [bold]{agent_name}[/bold]: {', '.join(assignments)}")

    if not display_entries:
        console.print("[dim]No dispatch entries found.[/dim]")

    # Sync to OVERLORD.md
    if sync or dry_run:
        _sync_overlord_md(registry, active, completed, agents, dry_run)


def _sync_overlord_md(
    registry: "OverlordConfig",
    active: list,
    completed: list,
    agents: dict[str, list[str]],
    dry_run: bool,
) -> None:
    """Rewrite the Dispatch Board and Agent Roster between markers in OVERLORD.md."""
    if not registry.workspace_root:
        console.print("[red]workspace_root not set in config — cannot sync.[/red]")
        return

    md_path = registry.workspace_root / "OVERLORD.md"
    if not md_path.exists():
        console.print(f"[red]OVERLORD.md not found at {md_path}[/red]")
        return

    content = md_path.read_text()

    # Build dispatch board markdown
    board_lines = [
        "| Track / Task | Project | Assigned Agent | Status | Started |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for entry in active + completed:
        entry_track = entry.metadata.get("track", "")
        entry_task_id = entry.metadata.get("task_id", "")
        label = entry_track if entry_track else entry_task_id
        entry_status = entry.metadata.get("status", "unknown").capitalize()
        agent_name = entry.metadata.get("agent_name", "")
        started = entry.timestamp[:10]
        board_lines.append(
            f"| {label} | {entry.project or ''} | {agent_name} | {entry_status} | {started} |"
        )
    board_md = "\n".join(board_lines) + "\n"

    # Build agent roster markdown
    roster_lines = []
    for agent_name, assignments in sorted(agents.items()):
        roster_lines.append(f"- **{agent_name}**: {', '.join(assignments)}")
    if not roster_lines:
        roster_lines.append("- *(no active agents)*")
    roster_md = "\n".join(roster_lines) + "\n"

    # Replace between markers
    new_content = content
    board_pattern = r"(<!-- DISPATCH_BOARD_START -->\n).*?(<!-- DISPATCH_BOARD_END -->)"
    roster_pattern = r"(<!-- AGENT_ROSTER_START -->\n).*?(<!-- AGENT_ROSTER_END -->)"

    if not re.search(board_pattern, new_content, re.DOTALL):
        console.print("[red]DISPATCH_BOARD markers not found in OVERLORD.md[/red]")
        return
    if not re.search(roster_pattern, new_content, re.DOTALL):
        console.print("[red]AGENT_ROSTER markers not found in OVERLORD.md[/red]")
        return

    new_content = re.sub(
        board_pattern, rf"\g<1>{board_md}\2", new_content, flags=re.DOTALL
    )
    new_content = re.sub(
        roster_pattern, rf"\g<1>{roster_md}\2", new_content, flags=re.DOTALL
    )

    if dry_run:
        console.print("\n[bold cyan]--- Dry Run: OVERLORD.md changes ---[/bold cyan]")
        if content == new_content:
            console.print("[dim]No changes.[/dim]")
        else:
            console.print(new_content)
        return

    # Create backup and write
    backup_path = md_path.with_suffix(".md.bak")
    backup_path.write_text(content)
    md_path.write_text(new_content)
    console.print(f"[green]OVERLORD.md synced. Backup at {backup_path}[/green]")


def _render_scope(scope: ActionScope, verdict: ScopeVerdict, autonomy: str) -> None:
    """Render an ActionScope and its verdict as a Rich panel."""
    lines = [
        f"[bold]Projects:[/bold] {', '.join(scope.projects) if scope.projects else '(none)'}",
        f"[bold]Branches:[/bold] {', '.join(scope.branches) if scope.branches else '(none)'}",
        f"[bold]Destructive:[/bold] {'Yes' if scope.destructive else 'No'}",
        f"[bold]Reversible:[/bold] {'Yes' if scope.reversible else 'No'}",
        f"[bold]Affects Remote:[/bold] {'Yes' if scope.affects_remote else 'No'}",
        f"[bold]Estimated Impact:[/bold] {scope.estimated_impact}",
        "",
        f"[bold]Autonomy Level:[/bold] {autonomy}",
    ]

    if verdict.approved:
        lines.append("[green bold]Verdict: APPROVED[/green bold]")
    else:
        lines.append("[red bold]Verdict: REQUIRES APPROVAL[/red bold]")

    lines.append(f"[bold]Reason:[/bold] {verdict.reason}")

    if verdict.escalation_required:
        lines.append("[yellow bold]Escalation required[/yellow bold]")

    border = "green" if verdict.approved else "red"
    console.print(Panel("\n".join(lines), title="Blast Radius", border_style=border))


# --- Budget commands ---

budget_app = typer.Typer(help="Manage cost controls and budget.")
overlord_app.add_typer(budget_app, name="budget")


@budget_app.command("status")
def budget_status() -> None:
    """Show current daily budget usage."""
    from nebulus_swarm.overlord.work_queue import WorkQueue

    queue = WorkQueue()
    usage = queue.get_daily_usage()

    if not usage:
        console.print("[dim]No token usage recorded today.[/dim]")
        return

    ceiling = usage["ceiling_usd"]
    spent = usage["estimated_cost_usd"]
    pct = (spent / ceiling * 100) if ceiling > 0 else 0.0

    color = "green" if pct < 80 else "yellow" if pct < 100 else "red"

    table = Table(title="Daily Budget Status")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Date", usage["date"])
    table.add_row("Input tokens", f"{usage['tokens_input']:,}")
    table.add_row("Output tokens", f"{usage['tokens_output']:,}")
    table.add_row("Estimated cost", f"${spent:.4f}")
    table.add_row("Ceiling", f"${ceiling:.2f}")
    table.add_row("Usage", f"[{color}]{pct:.1f}%[/{color}]")

    console.print(table)


@budget_app.command("set-ceiling")
def budget_set_ceiling(
    amount: float = typer.Argument(..., help="Daily ceiling in USD"),
) -> None:
    """Set the daily budget ceiling."""

    if amount < 0:
        console.print("[red]Ceiling must be non-negative.[/red]")
        return

    console.print(
        f"[green]Daily ceiling set to ${amount:.2f}[/green]\n"
        f"[dim]Note: Update overlord.yml cost_controls.daily_ceiling_usd "
        f"to persist this value.[/dim]"
    )


@budget_app.command("history")
def budget_history(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to show"),
) -> None:
    """Show budget usage history."""
    from datetime import timedelta

    from nebulus_swarm.overlord.work_queue import WorkQueue

    queue = WorkQueue()

    table = Table(title=f"Budget History (last {days} days)")
    table.add_column("Date", style="bold")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Ceiling", justify="right")
    table.add_column("Usage %", justify="right")

    today = datetime.now(timezone.utc).date()
    found = 0

    for i in range(days):
        date = (today - timedelta(days=i)).isoformat()
        usage = queue.get_daily_usage(date)
        if usage:
            found += 1
            ceiling = usage["ceiling_usd"]
            spent = usage["estimated_cost_usd"]
            pct = (spent / ceiling * 100) if ceiling > 0 else 0.0
            color = "green" if pct < 80 else "yellow" if pct < 100 else "red"
            table.add_row(
                date,
                f"{usage['tokens_input']:,}",
                f"{usage['tokens_output']:,}",
                f"${spent:.4f}",
                f"${ceiling:.2f}",
                f"[{color}]{pct:.1f}%[/{color}]",
            )

    if found == 0:
        console.print(f"[dim]No usage data found in the last {days} days.[/dim]")
        return

    console.print(table)
