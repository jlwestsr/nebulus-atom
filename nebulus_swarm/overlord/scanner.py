"""Overlord Ecosystem Scanner — git state and test health inspection.

Pure data gathering — never modifies anything. Uses subprocess for git
commands and returns structured dataclasses for the CLI layer to format.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from nebulus_swarm.overlord.registry import (
    OverlordConfig,
    ProjectConfig,
    get_dependency_order,
)


@dataclass
class GitState:
    """Git repository state for a single project."""

    branch: str
    clean: bool
    ahead: int = 0
    behind: int = 0
    last_commit: str = ""
    last_commit_date: str = ""
    stale_branches: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class TestHealth:
    """Test infrastructure state for a single project."""

    has_tests: bool = False
    test_command: Optional[str] = None
    last_run: Optional[str] = None  # placeholder for Phase 2


@dataclass
class ProjectStatus:
    """Combined status for a single project."""

    name: str
    config: ProjectConfig
    git: GitState
    tests: TestHealth
    issues: list[str] = field(default_factory=list)


def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _get_git_state(project_path: Path) -> GitState:
    """Gather git state for a project directory."""
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], project_path)

    # Check for clean working tree
    status_output = _run_git(["status", "--porcelain"], project_path)
    clean = len(status_output) == 0

    # Ahead/behind remote
    ahead = 0
    behind = 0
    rev_list = _run_git(
        ["rev-list", "--left-right", "--count", f"{branch}...origin/{branch}"],
        project_path,
    )
    if rev_list and "\t" in rev_list:
        parts = rev_list.split("\t")
        ahead = int(parts[0])
        behind = int(parts[1])

    # Last commit
    last_commit = _run_git(
        ["log", "-1", "--format=%h %s"],
        project_path,
    )
    last_commit_date = _run_git(
        ["log", "-1", "--format=%ci"],
        project_path,
    )

    # Stale branches (local branches with last commit >30 days old)
    stale_branches = _detect_stale_branches(project_path)

    # Recent tags (most recent 3)
    tags_output = _run_git(
        ["tag", "--sort=-creatordate", "--list"],
        project_path,
    )
    tags = tags_output.splitlines()[:3] if tags_output else []

    return GitState(
        branch=branch,
        clean=clean,
        ahead=ahead,
        behind=behind,
        last_commit=last_commit,
        last_commit_date=last_commit_date,
        stale_branches=stale_branches,
        tags=tags,
    )


def _detect_stale_branches(project_path: Path, days: int = 30) -> list[str]:
    """Find local branches whose last commit is older than `days` days."""
    stale: list[str] = []
    branches_output = _run_git(
        [
            "for-each-ref",
            "--format=%(refname:short) %(committerdate:iso8601)",
            "refs/heads/",
        ],
        project_path,
    )
    if not branches_output:
        return stale

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for line in branches_output.splitlines():
        parts = line.rsplit(" ", 3)
        if len(parts) < 2:
            continue
        branch_name = parts[0]
        try:
            # Parse ISO 8601 date from git
            date_str = " ".join(parts[1:])
            # git outputs like "2026-01-15 10:30:00 -0500"
            commit_date = datetime.fromisoformat(date_str)
            if commit_date < cutoff:
                stale.append(branch_name)
        except (ValueError, IndexError):
            continue

    return stale


def detect_test_command(project_path: Path) -> Optional[str]:
    """Detect the test command for a project via heuristics.

    Checks for:
    1. pytest in pyproject.toml
    2. bin/gantry test script
    3. Makefile with test target
    4. tests/ directory with pytest fallback

    Args:
        project_path: Root directory of the project.

    Returns:
        Detected test command string, or None if unknown.
    """
    # Check pyproject.toml for pytest
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            if "pytest" in content:
                return "python -m pytest tests/"
        except OSError:
            pass

    # Check for bin/gantry script
    gantry_script = project_path / "bin" / "gantry"
    if gantry_script.exists():
        return "bin/gantry test"

    # Check Makefile for test target
    makefile = project_path / "Makefile"
    if makefile.exists():
        try:
            content = makefile.read_text()
            if "test:" in content or "test :" in content:
                return "make test"
        except OSError:
            pass

    # Fallback: if tests/ directory exists, assume pytest
    tests_dir = project_path / "tests"
    if tests_dir.is_dir():
        return "python -m pytest tests/"

    return None


def scan_project(config: ProjectConfig) -> ProjectStatus:
    """Scan a single project for git state and test health.

    Args:
        config: Project configuration from the registry.

    Returns:
        ProjectStatus with all gathered data.
    """
    issues: list[str] = []

    # Check if path exists
    if not config.path.exists():
        return ProjectStatus(
            name=config.name,
            config=config,
            git=GitState(branch="", clean=False),
            tests=TestHealth(),
            issues=[f"Project path does not exist: {config.path}"],
        )

    # Gather git state
    git = _get_git_state(config.path)

    # Detect issues
    if not git.clean:
        issues.append("Dirty working tree")
    if git.behind > 0:
        issues.append(f"Behind remote by {git.behind} commit(s)")
    if git.stale_branches:
        issues.append(
            f"{len(git.stale_branches)} stale branch(es): "
            f"{', '.join(git.stale_branches[:3])}"
        )

    # Check branch alignment with branch model
    if config.branch_model == "develop-main":
        if git.branch not in ("develop", "main"):
            issues.append(f"On branch '{git.branch}' (expected develop or main)")

    # Gather test health
    test_cmd = detect_test_command(config.path)
    tests = TestHealth(
        has_tests=test_cmd is not None,
        test_command=test_cmd,
    )

    return ProjectStatus(
        name=config.name,
        config=config,
        git=git,
        tests=tests,
        issues=issues,
    )


def scan_ecosystem(registry: OverlordConfig) -> list[ProjectStatus]:
    """Scan all registered projects in dependency order.

    Args:
        registry: The Overlord config with all project registrations.

    Returns:
        List of ProjectStatus objects sorted by dependency order.
    """
    try:
        order = get_dependency_order(registry)
    except ValueError:
        # Circular deps — fall back to alphabetical
        order = sorted(registry.projects.keys())

    results: list[ProjectStatus] = []
    for name in order:
        config = registry.projects[name]
        status = scan_project(config)
        results.append(status)

    return results
