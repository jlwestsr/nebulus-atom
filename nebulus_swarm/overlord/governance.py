"""Governance Engine — pre-dispatch policy enforcement.

Validates tasks against governance rules before allowing dispatch.
Checks root workspace protection, concurrency limits, branch policy,
strategic drift, and file conflict detection.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.work_queue import Task, WorkQueue

logger = logging.getLogger(__name__)


@dataclass
class GovernanceViolation:
    """A single governance policy violation."""

    rule: str
    severity: str  # "hard-block" or "warning"
    message: str
    project: str


@dataclass
class GovernanceResult:
    """Result of a governance check."""

    approved: bool
    violations: list[GovernanceViolation] = field(default_factory=list)


class GovernanceEngine:
    """Pre-dispatch governance policy enforcement.

    Args:
        config: Overlord configuration.
        queue: Work queue for concurrency checks.
        workspace_root: Workspace root path for root-workspace protection.
    """

    def __init__(
        self,
        config: OverlordConfig,
        queue: WorkQueue,
        workspace_root: Optional[Path] = None,
    ) -> None:
        self.config = config
        self.queue = queue
        self.workspace_root = workspace_root or config.workspace_root
        self._priority_keywords: list[str] = []

    def set_priority_keywords(self, keywords: list[str]) -> None:
        """Set priority keywords for strategic drift detection.

        Args:
            keywords: List of business priority keyword strings.
        """
        self._priority_keywords = [k.lower() for k in keywords]

    def pre_dispatch_check(
        self, task: Task, project_config: ProjectConfig
    ) -> GovernanceResult:
        """Run all governance checks before dispatching a task.

        Args:
            task: The task to check.
            project_config: Project configuration for the task's project.

        Returns:
            GovernanceResult with approval status and any violations.
        """
        violations: list[GovernanceViolation] = []

        checks = [
            self._check_root_workspace(project_config),
            self._check_concurrency(task),
            self._check_branch_policy(project_config),
            self._check_strategic_drift(task),
        ]

        for violation in checks:
            if violation:
                violations.append(violation)

        hard_blocks = [v for v in violations if v.severity == "hard-block"]
        approved = len(hard_blocks) == 0

        return GovernanceResult(approved=approved, violations=violations)

    def _check_root_workspace(
        self, project_config: ProjectConfig
    ) -> Optional[GovernanceViolation]:
        """Block dispatch if project path resolves to the workspace root."""
        if not self.workspace_root:
            return None

        try:
            project_path = Path(project_config.path).resolve()
            workspace_path = Path(self.workspace_root).resolve()

            if project_path == workspace_path:
                return GovernanceViolation(
                    rule="root-workspace",
                    severity="hard-block",
                    message=(
                        f"Cannot dispatch to workspace root: {project_path}. "
                        "The root workspace is protected from autonomous changes."
                    ),
                    project=project_config.name,
                )
        except Exception:
            logger.warning(
                "Failed to resolve paths for root workspace check",
                exc_info=True,
            )

        return None

    def _check_concurrency(self, task: Task) -> Optional[GovernanceViolation]:
        """Block dispatch if another task for the same project is in-flight."""
        dispatched = self.queue.list_tasks(status="dispatched")
        for active in dispatched:
            if active.project == task.project and active.id != task.id:
                return GovernanceViolation(
                    rule="concurrency",
                    severity="hard-block",
                    message=(
                        f"Project '{task.project}' already has a dispatched task: "
                        f"{active.id[:8]} ({active.title}). "
                        "Wait for it to complete before dispatching another."
                    ),
                    project=task.project,
                )
        return None

    def _check_branch_policy(
        self, project_config: ProjectConfig
    ) -> Optional[GovernanceViolation]:
        """Warn if the project's branch doesn't follow naming conventions."""
        if project_config.branch_model != "develop-main":
            return None

        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(project_config.path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            branch = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

        if not branch:
            return None

        valid_prefixes = ("feat/", "fix/", "docs/", "chore/", "develop", "main")
        if not branch.startswith(valid_prefixes):
            return GovernanceViolation(
                rule="branch-policy",
                severity="warning",
                message=(
                    f"Project '{project_config.name}' is on branch '{branch}' "
                    f"which doesn't follow the expected naming convention. "
                    f"Expected: feat/, fix/, docs/, chore/, develop, or main."
                ),
                project=project_config.name,
            )

        return None

    def _check_strategic_drift(self, task: Task) -> Optional[GovernanceViolation]:
        """Flag tasks that may not align with business priorities."""
        if not self._priority_keywords:
            return None

        text = f"{task.title} {task.description or ''}".lower()
        matched = any(kw in text for kw in self._priority_keywords)

        if not matched:
            return GovernanceViolation(
                rule="strategic-drift",
                severity="warning",
                message=(
                    f"Task '{task.title}' does not match any business priority "
                    f"keywords. Consider reviewing alignment with current priorities."
                ),
                project=task.project,
            )

        return None

    def check_conflict(
        self, task: Task, active_tasks: list[Task]
    ) -> Optional[GovernanceViolation]:
        """Detect potential file conflicts between a task and active dispatches.

        Args:
            task: The new task to check.
            active_tasks: Currently dispatched tasks.

        Returns:
            GovernanceViolation if conflict detected, else None.
        """
        if not task.description:
            return None

        task_paths = _extract_file_patterns(task.description)
        if not task_paths:
            task_paths = _extract_file_patterns(task.title)
        if not task_paths:
            return None

        for active in active_tasks:
            if active.id == task.id:
                continue
            active_text = f"{active.title} {active.description or ''}"
            active_paths = _extract_file_patterns(active_text)

            overlap = task_paths & active_paths
            if overlap:
                return GovernanceViolation(
                    rule="conflict",
                    severity="hard-block",
                    message=(
                        f"Potential file conflict with dispatched task "
                        f"{active.id[:8]} ({active.title}). "
                        f"Overlapping paths: {', '.join(sorted(overlap)[:5])}"
                    ),
                    project=task.project,
                )

        return None


def _extract_file_patterns(text: str) -> set[str]:
    """Extract file path-like patterns from text.

    Args:
        text: Text to search for file patterns.

    Returns:
        Set of normalized file path segments.
    """
    patterns: set[str] = set()

    # Match file paths with extensions
    path_pattern = re.compile(r"[\w./]+\.\w{1,5}")
    for match in path_pattern.finditer(text):
        path = match.group().strip("./")
        if path:
            patterns.add(path)

    # Match module-like patterns (foo/bar, foo.bar)
    module_pattern = re.compile(r"\b(\w+[/.](?:\w+[/.])*\w+)\b")
    for match in module_pattern.finditer(text):
        patterns.add(match.group(1))

    return patterns
