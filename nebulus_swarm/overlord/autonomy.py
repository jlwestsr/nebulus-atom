"""Autonomy Engine for the Overlord.

Manages autonomy levels (cautious/proactive/scheduled) and determines
whether actions can auto-execute, require approval, or should be proactively
proposed to the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nebulus_swarm.overlord.action_scope import ActionScope
    from nebulus_swarm.overlord.registry import OverlordConfig


@dataclass
class AutonomyConfig:
    """Per-project autonomy configuration."""

    project: str
    level: str  # "cautious", "proactive", "scheduled"
    pre_approved_actions: list[str] = field(default_factory=list)


class AutonomyEngine:
    """Manages autonomy levels and action approval decisions."""

    def __init__(self, config: "OverlordConfig"):
        """Initialize the autonomy engine.

        Args:
            config: The Overlord configuration containing autonomy settings.
        """
        self.config = config

    def get_level(self, project: str | None = None) -> str:
        """Get effective autonomy level for a project.

        Args:
            project: Project name. If None, returns global level.

        Returns:
            One of: "cautious", "proactive", "scheduled"
        """
        if project and project in self.config.autonomy_overrides:
            return self.config.autonomy_overrides[project]
        return self.config.autonomy_global

    def can_auto_execute(
        self, action: str, scope: "ActionScope", project: str | None = None
    ) -> bool:
        """Check if action can auto-execute under current autonomy.

        Args:
            action: Action identifier (e.g., "merge develop to main").
            scope: ActionScope describing the blast radius.
            project: Project name for level lookup.

        Returns:
            True if action can proceed without approval.
        """
        level = self.get_level(project)

        # Cautious: nothing auto-executes
        if level == "cautious":
            return False

        # Proactive: only safe local operations
        if level == "proactive":
            return self._is_safe_local(scope)

        # Scheduled: check pre-approved list
        if level == "scheduled":
            return self._is_pre_approved(action, scope)

        return False

    def should_propose(
        self, action: str, scope: "ActionScope", project: str | None = None
    ) -> bool:
        """Check if Overlord should proactively propose this action.

        Args:
            action: Action identifier.
            scope: ActionScope describing the blast radius.
            project: Project name for level lookup.

        Returns:
            True if Overlord should propose this action to the user.
        """
        level = self.get_level(project)

        # Cautious: never proposes
        if level == "cautious":
            return False

        # Proactive: proposes low-medium impact actions
        if level == "proactive":
            return scope.estimated_impact in ("low", "medium")

        # Scheduled: proposes anything outside pre-approved list
        if level == "scheduled":
            return not self._is_pre_approved(action, scope)

        return False

    def should_escalate(self, scope: "ActionScope") -> bool:
        """Check if action requires escalation regardless of autonomy level.

        Certain actions always require approval:
        - Destructive operations affecting remote
        - High-impact multi-project changes

        Args:
            scope: ActionScope describing the blast radius.

        Returns:
            True if action must be escalated to user.
        """
        # Destructive + remote always escalates
        if scope.destructive and scope.affects_remote:
            return True

        # High impact affecting multiple projects
        if scope.estimated_impact == "high" and len(scope.projects) > 1:
            return True

        return False

    def get_project_config(self, project: str) -> AutonomyConfig:
        """Get full autonomy configuration for a project.

        Args:
            project: Project name.

        Returns:
            AutonomyConfig with level and pre-approved actions.
        """
        level = self.get_level(project)
        pre_approved = self.config.autonomy_pre_approved.get(project, [])

        return AutonomyConfig(
            project=project, level=level, pre_approved_actions=pre_approved
        )

    def _is_safe_local(self, scope: "ActionScope") -> bool:
        """Check if scope represents a safe local operation.

        Safe operations are:
        - Non-destructive
        - Reversible
        - Don't affect remote
        - Low or medium impact

        Args:
            scope: ActionScope to evaluate.

        Returns:
            True if operation is safe for proactive auto-execution.
        """
        return (
            not scope.destructive
            and scope.reversible
            and not scope.affects_remote
            and scope.estimated_impact in ("low", "medium")
        )

    def _is_pre_approved(self, action: str, scope: "ActionScope") -> bool:
        """Check if action is in the pre-approved list for affected projects.

        Args:
            action: Action identifier.
            scope: ActionScope containing affected projects.

        Returns:
            True if action is pre-approved for all affected projects.
        """
        if not scope.projects:
            return False

        # Action must be pre-approved for ALL affected projects
        for project in scope.projects:
            approved_actions = self.config.autonomy_pre_approved.get(project, [])
            if action not in approved_actions:
                return False

        return True


def get_autonomy_summary(config: "OverlordConfig") -> dict[str, str]:
    """Get a summary of autonomy levels across all projects.

    Args:
        config: The Overlord configuration.

    Returns:
        Dict mapping project names to their effective autonomy levels.
    """
    engine = AutonomyEngine(config)
    summary = {"__global__": config.autonomy_global}

    for project_name in config.projects:
        summary[project_name] = engine.get_level(project_name)

    return summary
