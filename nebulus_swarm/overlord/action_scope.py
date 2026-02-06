"""Action scope model and blast radius evaluation for the Overlord.

Provides a safety layer between "Overlord wants to do X" and
"Overlord actually does X." Evaluates proposed actions against
the current autonomy level and scope constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nebulus_swarm.overlord.graph import DependencyGraph
    from nebulus_swarm.overlord.registry import OverlordConfig


@dataclass
class ActionScope:
    """Describes the blast radius of a proposed action."""

    projects: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    destructive: bool = False
    reversible: bool = True
    affects_remote: bool = False
    estimated_impact: str = "low"  # "low", "medium", "high"


@dataclass
class ScopeVerdict:
    """Result of evaluating an ActionScope against autonomy rules."""

    approved: bool
    reason: str
    escalation_required: bool = False


# --- Pre-built scopes for common actions ---

SCOPE_READ_ONLY = ActionScope(
    projects=[],
    branches=[],
    destructive=False,
    reversible=True,
    affects_remote=False,
    estimated_impact="low",
)

SCOPE_LOCAL_MERGE = ActionScope(
    projects=[],
    branches=[],
    destructive=False,
    reversible=True,
    affects_remote=False,
    estimated_impact="medium",
)

SCOPE_PUSH = ActionScope(
    projects=[],
    branches=[],
    destructive=False,
    reversible=False,
    affects_remote=True,
    estimated_impact="medium",
)

SCOPE_RELEASE = ActionScope(
    projects=[],
    branches=[],
    destructive=False,
    reversible=False,
    affects_remote=True,
    estimated_impact="high",
)


def evaluate_scope(
    scope: ActionScope,
    autonomy_level: str,
    config: "OverlordConfig",
) -> ScopeVerdict:
    """Evaluate whether an action should proceed under the given autonomy level.

    Rules:
        - destructive + affects_remote -> always requires approval
        - cautious -> everything except read-only requires approval
        - proactive -> proposes, waits for approval on medium/high impact
        - scheduled -> auto-approves low impact, escalates medium/high

    Args:
        scope: The action scope to evaluate.
        autonomy_level: One of "cautious", "proactive", "scheduled".
        config: The Overlord config (for future per-project overrides).

    Returns:
        ScopeVerdict with approval decision and reasoning.
    """
    # Hard rule: destructive remote actions always escalate
    if scope.destructive and scope.affects_remote:
        return ScopeVerdict(
            approved=False,
            reason="Destructive remote action requires explicit approval",
            escalation_required=True,
        )

    if autonomy_level == "cautious":
        if scope.estimated_impact == "low" and not scope.affects_remote:
            return ScopeVerdict(
                approved=True,
                reason="Low-impact local action auto-approved under cautious mode",
            )
        return ScopeVerdict(
            approved=False,
            reason="Cautious mode requires approval for non-trivial actions",
            escalation_required=scope.estimated_impact in ("medium", "high"),
        )

    if autonomy_level == "proactive":
        if scope.estimated_impact == "low":
            return ScopeVerdict(
                approved=True,
                reason="Low-impact action auto-approved under proactive mode",
            )
        return ScopeVerdict(
            approved=False,
            reason=(
                f"{scope.estimated_impact.capitalize()}-impact action "
                "requires approval under proactive mode"
            ),
            escalation_required=scope.estimated_impact == "high",
        )

    if autonomy_level == "scheduled":
        if scope.estimated_impact == "low":
            return ScopeVerdict(
                approved=True,
                reason="Low-impact action auto-approved under scheduled mode",
            )
        if scope.estimated_impact == "medium" and not scope.affects_remote:
            return ScopeVerdict(
                approved=True,
                reason="Medium-impact local action auto-approved under scheduled mode",
            )
        return ScopeVerdict(
            approved=False,
            reason=(
                f"{scope.estimated_impact.capitalize()}-impact action "
                "escalated under scheduled mode"
            ),
            escalation_required=True,
        )

    # Unknown autonomy level — deny by default
    return ScopeVerdict(
        approved=False,
        reason=f"Unknown autonomy level '{autonomy_level}'",
        escalation_required=True,
    )


def scope_for_merge(project: str, source: str, target: str) -> ActionScope:
    """Build an ActionScope for merging branches locally.

    Args:
        project: Project name.
        source: Source branch.
        target: Target branch.

    Returns:
        ActionScope for the merge.
    """
    return ActionScope(
        projects=[project],
        branches=[source, target],
        destructive=False,
        reversible=True,
        affects_remote=False,
        estimated_impact="medium",
    )


def scope_for_push(projects: list[str]) -> ActionScope:
    """Build an ActionScope for pushing to remote.

    Args:
        projects: List of project names being pushed.

    Returns:
        ActionScope for the push.
    """
    impact = "high" if len(projects) > 1 else "medium"
    return ActionScope(
        projects=projects,
        branches=[],
        destructive=False,
        reversible=False,
        affects_remote=True,
        estimated_impact=impact,
    )


def scope_for_release(project: str, graph: "DependencyGraph") -> ActionScope:
    """Build an ActionScope for a release, including downstream projects.

    Args:
        project: Project being released.
        graph: DependencyGraph for impact analysis.

    Returns:
        ActionScope covering the release and all affected projects.
    """
    affected = graph.get_affected_by(project)
    return ActionScope(
        projects=affected,
        branches=["develop", "main"],
        destructive=False,
        reversible=False,
        affects_remote=True,
        estimated_impact="high",
    )
