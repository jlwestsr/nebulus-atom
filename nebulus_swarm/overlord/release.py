"""Overlord Release Coordinator — automated multi-repo releases."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nebulus_swarm.overlord.action_scope import ActionScope
from nebulus_swarm.overlord.dispatch import DispatchPlan, DispatchStep

if TYPE_CHECKING:
    from nebulus_swarm.overlord.dispatch import DispatchEngine, DispatchResult
    from nebulus_swarm.overlord.graph import DependencyGraph
    from nebulus_swarm.overlord.memory import OverlordMemory
    from nebulus_swarm.overlord.registry import OverlordConfig

logger = logging.getLogger(__name__)


@dataclass
class ReleaseSpec:
    """Specification for a coordinated release."""

    project: str
    version: str
    source_branch: str = "develop"
    target_branch: str = "main"
    update_dependents: bool = True
    push_to_remote: bool = False


class ReleaseCoordinator:
    """Coordinates releases across dependent projects."""

    def __init__(
        self,
        config: OverlordConfig,
        graph: DependencyGraph,
        dispatch: DispatchEngine,
        memory: OverlordMemory,
    ):
        """Initialize the release coordinator.

        Args:
            config: Overlord configuration.
            graph: Dependency graph for project relationships.
            dispatch: Dispatch engine for executing plans.
            memory: Memory store for logging releases.
        """
        self.config = config
        self.graph = graph
        self.dispatch = dispatch
        self.memory = memory

    def plan_release(self, spec: ReleaseSpec) -> DispatchPlan:
        """Plan a coordinated release.

        Args:
            spec: Release specification.

        Returns:
            DispatchPlan ready for execution.

        Raises:
            ValueError: If project is unknown or invalid.
        """
        # Validate project
        if spec.project not in self.config.projects:
            raise ValueError(f"Unknown project: {spec.project}")

        logger.info(
            f"Planning release: {spec.project} {spec.version} "
            f"({spec.source_branch} → {spec.target_branch})"
        )

        steps: list[DispatchStep] = []
        step_counter = 0

        def next_step_id() -> str:
            nonlocal step_counter
            step_counter += 1
            return f"step-{step_counter}"

        # Step 1: Validate tests on source project
        validate_id = next_step_id()
        steps.append(
            DispatchStep(
                id=validate_id,
                action="validate tests",
                project=spec.project,
                dependencies=[],
                model_tier=None,
                timeout=300,
            )
        )

        # Step 2: Merge source → target
        merge_id = next_step_id()
        steps.append(
            DispatchStep(
                id=merge_id,
                action=f"merge {spec.source_branch} to {spec.target_branch}",
                project=spec.project,
                dependencies=[validate_id],
                model_tier=None,
                timeout=60,
            )
        )

        # Step 3: Tag version
        tag_id = next_step_id()
        steps.append(
            DispatchStep(
                id=tag_id,
                action=f"tag {spec.version}",
                project=spec.project,
                dependencies=[merge_id],
                model_tier=None,
                timeout=30,
            )
        )

        # Step 4: Update dependents (if requested)
        dependent_test_ids: list[str] = []
        if spec.update_dependents:
            downstream = self.graph.get_downstream(spec.project)
            for dep_project in downstream:
                # Update dependency version
                update_id = next_step_id()
                steps.append(
                    DispatchStep(
                        id=update_id,
                        action=f"update {spec.project} to {spec.version}",
                        project=dep_project,
                        dependencies=[tag_id],
                        model_tier=None,
                        timeout=120,
                    )
                )

                # Validate dependent's tests
                test_id = next_step_id()
                steps.append(
                    DispatchStep(
                        id=test_id,
                        action="validate tests",
                        project=dep_project,
                        dependencies=[update_id],
                        model_tier=None,
                        timeout=300,
                    )
                )
                dependent_test_ids.append(test_id)

        # Step 5: Push to remote (if requested)
        if spec.push_to_remote:
            push_deps = [tag_id] + dependent_test_ids
            push_id = next_step_id()
            steps.append(
                DispatchStep(
                    id=push_id,
                    action="push to remote",
                    project=spec.project,
                    dependencies=push_deps,
                    model_tier=None,
                    timeout=60,
                )
            )

            # Also push dependents
            if spec.update_dependents:
                downstream = self.graph.get_downstream(spec.project)
                for dep_project in downstream:
                    dep_push_id = next_step_id()
                    steps.append(
                        DispatchStep(
                            id=dep_push_id,
                            action="push to remote",
                            project=dep_project,
                            dependencies=[push_id],
                            model_tier=None,
                            timeout=60,
                        )
                    )

        # Build scope
        affected = self.graph.get_affected_by(spec.project)
        scope = ActionScope(
            projects=affected,
            branches=[spec.source_branch, spec.target_branch],
            destructive=False,
            reversible=False if spec.push_to_remote else True,
            affects_remote=spec.push_to_remote,
            estimated_impact="high",
        )

        return DispatchPlan(
            task=f"Release {spec.project} {spec.version}",
            steps=steps,
            scope=scope,
            estimated_duration=sum(s.timeout for s in steps),
            requires_approval=True,  # Releases always need approval
        )

    def execute_release(
        self, spec: ReleaseSpec, auto_approve: bool = False
    ) -> DispatchResult:
        """Execute a coordinated release.

        Args:
            spec: Release specification.
            auto_approve: If True, skip approval prompts.

        Returns:
            DispatchResult with execution status.
        """
        plan = self.plan_release(spec)
        result = self.dispatch.execute(plan, auto_approve=auto_approve)

        # Log to memory on success
        if result.status == "success":
            downstream = self.graph.get_downstream(spec.project)
            self.memory.remember(
                category="release",
                content=f"{spec.project} {spec.version} released",
                project=spec.project,
                version=spec.version,
                downstream_updated=downstream if spec.update_dependents else [],
                pushed=spec.push_to_remote,
            )
            logger.info(f"Release logged to memory: {spec.project} {spec.version}")

        return result


def validate_release_spec(spec: ReleaseSpec, config: OverlordConfig) -> list[str]:
    """Validate a release specification.

    Args:
        spec: Release specification to validate.
        config: Overlord configuration.

    Returns:
        List of error messages. Empty list means valid.
    """
    errors: list[str] = []

    # Validate project exists
    if spec.project not in config.projects:
        errors.append(f"Unknown project: {spec.project}")
        return errors  # Can't continue validation without valid project

    # Validate version format (basic semver check)
    if not spec.version:
        errors.append("Version cannot be empty")
    elif not spec.version.startswith("v"):
        errors.append("Version must start with 'v' (e.g., v0.1.0)")

    # Validate branch names
    if not spec.source_branch:
        errors.append("Source branch cannot be empty")
    if not spec.target_branch:
        errors.append("Target branch cannot be empty")
    if spec.source_branch == spec.target_branch:
        errors.append("Source and target branches cannot be the same")

    return errors


def parse_version_string(version: str) -> tuple[int, int, int]:
    """Parse a semantic version string.

    Args:
        version: Version string (e.g., "v0.1.0" or "0.1.0").

    Returns:
        Tuple of (major, minor, patch).

    Raises:
        ValueError: If version format is invalid.
    """
    # Strip 'v' prefix if present
    if version.startswith("v"):
        version = version[1:]

    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version} (expected X.Y.Z)")

    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
    except ValueError as e:
        raise ValueError(
            f"Invalid version format: {version} (parts must be integers)"
        ) from e

    return (major, minor, patch)


def suggest_next_version(current: str, bump: str = "patch") -> str:
    """Suggest next version based on current version and bump type.

    Args:
        current: Current version (e.g., "v0.1.0").
        bump: Bump type - "major", "minor", or "patch".

    Returns:
        Next version string with 'v' prefix.

    Raises:
        ValueError: If current version or bump type is invalid.
    """
    major, minor, patch = parse_version_string(current)

    if bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump == "minor":
        minor += 1
        patch = 0
    elif bump == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid bump type: {bump} (must be major, minor, or patch)")

    return f"v{major}.{minor}.{patch}"
