"""CLI commands for the Overlord cross-project orchestrator."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from nebulus_swarm.overlord.registry import (
    DEFAULT_CONFIG_PATH,
    OverlordConfig,
    get_dependency_order,
    load_config,
    validate_config,
)
from nebulus_swarm.overlord.scanner import (
    ProjectStatus,
    scan_ecosystem,
    scan_project,
)

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
