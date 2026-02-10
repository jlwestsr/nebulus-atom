"""Overlord Project Registry — config model and YAML loader.

Manages the cross-project registry that maps the Nebulus ecosystem.
Config lives at ~/.atom/overlord.yml by default.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nebulus_atom.settings import load_yaml_config


# Valid values for role and autonomy fields
VALID_ROLES = frozenset(
    {
        "shared-library",
        "platform-deployment",
        "frontend",
        "tooling",
        "provisioning",
        "personal",
    }
)

VALID_BRANCH_MODELS = frozenset(
    {
        "develop-main",
        "trunk-based",
        "gitflow",
    }
)

VALID_AUTONOMY_LEVELS = frozenset(
    {
        "cautious",
        "proactive",
        "scheduled",
    }
)

DEFAULT_CONFIG_PATH = Path.home() / ".atom" / "overlord.yml"


@dataclass
class ProjectConfig:
    """Configuration for a single project in the ecosystem."""

    name: str
    path: Path
    remote: str
    role: str
    branch_model: str = "develop-main"
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ScheduledTask:
    """A single scheduled task definition."""

    name: str
    cron: str
    enabled: bool = True


@dataclass
class ScheduleConfig:
    """Configuration for the daemon scheduler."""

    tasks: list[ScheduledTask] = field(default_factory=list)

    @staticmethod
    def default() -> ScheduleConfig:
        """Return sensible default schedule."""
        return ScheduleConfig(
            tasks=[
                ScheduledTask(name="scan", cron="0 * * * *"),
                ScheduledTask(name="test-all", cron="0 2 * * *"),
                ScheduledTask(name="clean-stale-branches", cron="0 3 * * 0"),
            ]
        )


@dataclass
class NotificationConfig:
    """Configuration for the notification system."""

    urgent_enabled: bool = True
    digest_enabled: bool = True
    digest_cron: str = "0 8 * * *"  # 8 AM UTC daily


@dataclass
class CostControlConfig:
    """Configuration for cost controls and budget enforcement."""

    daily_ceiling_usd: float = 10.0
    warning_threshold_pct: float = 80.0
    default_task_budget_tokens: int = 100000


@dataclass
class OverlordConfig:
    """Top-level Overlord configuration."""

    workspace_root: Optional[Path] = None
    projects: dict[str, ProjectConfig] = field(default_factory=dict)
    autonomy_global: str = "cautious"
    autonomy_overrides: dict[str, str] = field(default_factory=dict)
    autonomy_pre_approved: dict[str, list[str]] = field(default_factory=dict)
    models: dict[str, dict[str, object]] = field(default_factory=dict)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    workers: dict[str, dict[str, object]] = field(default_factory=dict)
    cost_controls: CostControlConfig = field(default_factory=CostControlConfig)


def load_config(path: Optional[Path] = None) -> OverlordConfig:
    """Load Overlord config from YAML.

    Args:
        path: Path to overlord.yml. Defaults to ~/.atom/overlord.yml.

    Returns:
        Parsed OverlordConfig.

    Raises:
        ValueError: If the YAML structure is invalid.
    """
    config_path = path or DEFAULT_CONFIG_PATH
    raw = load_yaml_config(config_path)

    if not raw:
        return OverlordConfig()

    projects: dict[str, ProjectConfig] = {}
    raw_projects = raw.get("projects", {})
    if not isinstance(raw_projects, dict):
        raise ValueError("'projects' must be a mapping of project names to configs")

    for name, proj_data in raw_projects.items():
        if not isinstance(proj_data, dict):
            raise ValueError(f"Project '{name}' must be a mapping")

        raw_path = proj_data.get("path", "")
        resolved_path = Path(raw_path).expanduser().resolve()

        projects[name] = ProjectConfig(
            name=name,
            path=resolved_path,
            remote=proj_data.get("remote", ""),
            role=proj_data.get("role", "tooling"),
            branch_model=proj_data.get("branch_model", "develop-main"),
            depends_on=proj_data.get("depends_on", []),
        )

    autonomy_global = raw.get("autonomy", {}).get("global", "cautious")
    autonomy_overrides = raw.get("autonomy", {}).get("overrides", {})
    autonomy_pre_approved = raw.get("autonomy", {}).get("pre_approved", {})
    models = raw.get("models", {})

    # Parse schedule
    raw_schedule = raw.get("schedule", {})
    schedule_tasks: list[ScheduledTask] = []
    if isinstance(raw_schedule, dict):
        for task_name, task_data in raw_schedule.items():
            if isinstance(task_data, dict):
                schedule_tasks.append(
                    ScheduledTask(
                        name=task_name,
                        cron=str(task_data.get("cron", "")),
                        enabled=bool(task_data.get("enabled", True)),
                    )
                )
            elif isinstance(task_data, str):
                # Short form: task_name: "cron_expression"
                schedule_tasks.append(ScheduledTask(name=task_name, cron=task_data))
    schedule = (
        ScheduleConfig(tasks=schedule_tasks) if schedule_tasks else ScheduleConfig()
    )

    # Parse notifications
    raw_notif = raw.get("notifications", {})
    notifications = (
        NotificationConfig(
            urgent_enabled=bool(raw_notif.get("urgent_enabled", True)),
            digest_enabled=bool(raw_notif.get("digest_enabled", True)),
            digest_cron=str(raw_notif.get("digest_cron", "0 8 * * *")),
        )
        if isinstance(raw_notif, dict)
        else NotificationConfig()
    )

    # Parse workers
    raw_workers = raw.get("workers", {})
    workers = dict(raw_workers) if isinstance(raw_workers, dict) else {}

    # Parse cost controls
    raw_cc = raw.get("cost_controls", {})
    cost_controls = (
        CostControlConfig(
            daily_ceiling_usd=float(raw_cc.get("daily_ceiling_usd", 10.0)),
            warning_threshold_pct=float(raw_cc.get("warning_threshold_pct", 80.0)),
            default_task_budget_tokens=int(
                raw_cc.get("default_task_budget_tokens", 100000)
            ),
        )
        if isinstance(raw_cc, dict)
        else CostControlConfig()
    )

    # Parse workspace_root — explicit from YAML or auto-detected from project paths
    raw_ws = raw.get("workspace_root")
    if raw_ws:
        workspace_root: Optional[Path] = Path(str(raw_ws)).expanduser().resolve()
    elif projects:
        # Auto-detect: common parent of all project paths
        paths = [p.path for p in projects.values()]
        candidate = paths[0].parent
        if all(str(p).startswith(str(candidate)) for p in paths):
            workspace_root = candidate
        else:
            workspace_root = None
    else:
        workspace_root = None

    return OverlordConfig(
        workspace_root=workspace_root,
        projects=projects,
        autonomy_global=str(autonomy_global),
        autonomy_overrides={str(k): str(v) for k, v in autonomy_overrides.items()},
        autonomy_pre_approved={
            str(k): [str(action) for action in v]
            for k, v in autonomy_pre_approved.items()
        },
        models=dict(models) if isinstance(models, dict) else {},
        schedule=schedule,
        notifications=notifications,
        workers=workers,
        cost_controls=cost_controls,
    )


def validate_config(config: OverlordConfig) -> list[str]:
    """Validate an OverlordConfig and return a list of errors.

    Args:
        config: The config to validate.

    Returns:
        List of error strings. Empty means valid.
    """
    errors: list[str] = []

    # Validate global autonomy level
    if config.autonomy_global not in VALID_AUTONOMY_LEVELS:
        errors.append(
            f"Invalid global autonomy '{config.autonomy_global}'. "
            f"Must be one of: {', '.join(sorted(VALID_AUTONOMY_LEVELS))}"
        )

    # Validate autonomy overrides
    for proj_name, level in config.autonomy_overrides.items():
        if level not in VALID_AUTONOMY_LEVELS:
            errors.append(
                f"Invalid autonomy override '{level}' for project '{proj_name}'. "
                f"Must be one of: {', '.join(sorted(VALID_AUTONOMY_LEVELS))}"
            )
        if proj_name not in config.projects:
            errors.append(f"Autonomy override references unknown project '{proj_name}'")

    # Validate pre-approved actions reference valid projects
    for proj_name in config.autonomy_pre_approved:
        if proj_name not in config.projects:
            errors.append(
                f"Pre-approved actions reference unknown project '{proj_name}'"
            )

    # Validate each project
    for name, proj in config.projects.items():
        if proj.role not in VALID_ROLES:
            errors.append(
                f"Project '{name}': invalid role '{proj.role}'. "
                f"Must be one of: {', '.join(sorted(VALID_ROLES))}"
            )

        if proj.branch_model not in VALID_BRANCH_MODELS:
            errors.append(
                f"Project '{name}': invalid branch_model '{proj.branch_model}'. "
                f"Must be one of: {', '.join(sorted(VALID_BRANCH_MODELS))}"
            )

        if not proj.path.exists():
            errors.append(f"Project '{name}': path does not exist: {proj.path}")

        if not proj.remote:
            errors.append(f"Project '{name}': remote is required")

        # Validate depends_on references
        for dep in proj.depends_on:
            if dep not in config.projects:
                errors.append(
                    f"Project '{name}': depends_on references unknown project '{dep}'"
                )

    # Validate workers
    claude_worker = config.workers.get("claude")
    if isinstance(claude_worker, dict) and claude_worker.get("enabled"):
        if not claude_worker.get("binary_path"):
            errors.append("Worker 'claude': binary_path is required when enabled")

    # Check for circular dependencies
    cycle = _find_cycle(config)
    if cycle:
        errors.append(f"Circular dependency detected: {' -> '.join(cycle)}")

    return errors


def get_dependency_order(config: OverlordConfig) -> list[str]:
    """Return project names in topological order (dependencies first).

    Args:
        config: The Overlord config.

    Returns:
        List of project names sorted so that dependencies come before
        dependents. Projects with no dependencies come first.

    Raises:
        ValueError: If circular dependencies exist.
    """
    # Build adjacency map: project -> set of projects it depends on
    in_degree: dict[str, int] = {name: 0 for name in config.projects}
    dependents: dict[str, list[str]] = {name: [] for name in config.projects}

    for name, proj in config.projects.items():
        for dep in proj.depends_on:
            if dep in config.projects:
                in_degree[name] += 1
                dependents[dep].append(name)

    # Kahn's algorithm
    queue: deque[str] = deque()
    for name, degree in in_degree.items():
        if degree == 0:
            queue.append(name)

    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(order) != len(config.projects):
        raise ValueError("Circular dependency detected — cannot determine build order")

    return order


def _find_cycle(config: OverlordConfig) -> list[str]:
    """Detect a dependency cycle via DFS. Returns the cycle path or []."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {name: WHITE for name in config.projects}
    parent: dict[str, str | None] = {name: None for name in config.projects}

    def dfs(node: str) -> list[str]:
        color[node] = GRAY
        proj = config.projects[node]
        for dep in proj.depends_on:
            if dep not in config.projects:
                continue
            if color[dep] == GRAY:
                # Reconstruct cycle
                cycle = [dep, node]
                cur = node
                while parent[cur] is not None and parent[cur] != dep:
                    cur = parent[cur]  # type: ignore[assignment]
                    cycle.append(cur)
                cycle.append(dep)
                cycle.reverse()
                return cycle
            if color[dep] == WHITE:
                parent[dep] = node
                result = dfs(dep)
                if result:
                    return result
        color[node] = BLACK
        return []

    for name in config.projects:
        if color[name] == WHITE:
            result = dfs(name)
            if result:
                return result
    return []
