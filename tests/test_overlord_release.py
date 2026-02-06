"""Tests for Overlord Release Coordinator."""

from __future__ import annotations

from pathlib import Path

import pytest

from nebulus_swarm.overlord.autonomy import AutonomyEngine
from nebulus_swarm.overlord.dispatch import DispatchEngine
from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.memory import OverlordMemory
from nebulus_swarm.overlord.model_router import ModelRouter
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.release import (
    ReleaseCoordinator,
    ReleaseSpec,
    parse_version_string,
    suggest_next_version,
    validate_release_spec,
)


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Build a test config with dependencies."""
    projects = {}

    # Core has no dependencies
    core_dir = tmp_path / "core"
    core_dir.mkdir(exist_ok=True)
    projects["core"] = ProjectConfig(
        name="core",
        path=core_dir,
        remote="test/core",
        role="shared-library",
        depends_on=[],
    )

    # Prime depends on Core
    prime_dir = tmp_path / "prime"
    prime_dir.mkdir(exist_ok=True)
    projects["prime"] = ProjectConfig(
        name="prime",
        path=prime_dir,
        remote="test/prime",
        role="platform-deployment",
        depends_on=["core"],
    )

    # Edge depends on Core
    edge_dir = tmp_path / "edge"
    edge_dir.mkdir(exist_ok=True)
    projects["edge"] = ProjectConfig(
        name="edge",
        path=edge_dir,
        remote="test/edge",
        role="platform-deployment",
        depends_on=["core"],
    )

    return OverlordConfig(
        projects=projects,
        models={
            "local": {
                "endpoint": "http://localhost:5000",
                "model": "test",
                "tier": "local",
            }
        },
    )


def _make_coordinator(config: OverlordConfig, tmp_path: Path) -> ReleaseCoordinator:
    """Build a release coordinator with dependencies."""
    graph = DependencyGraph(config)
    autonomy = AutonomyEngine(config)
    router = ModelRouter(config)
    dispatch = DispatchEngine(config, autonomy, graph, router)
    memory = OverlordMemory(tmp_path / "memory.db")
    return ReleaseCoordinator(config, graph, dispatch, memory)


class TestReleaseSpec:
    """Tests for ReleaseSpec dataclass."""

    def test_creates_with_required_fields(self) -> None:
        spec = ReleaseSpec(project="core", version="v0.1.0")
        assert spec.project == "core"
        assert spec.version == "v0.1.0"
        assert spec.source_branch == "develop"
        assert spec.target_branch == "main"
        assert spec.update_dependents is True
        assert spec.push_to_remote is False

    def test_creates_with_all_fields(self) -> None:
        spec = ReleaseSpec(
            project="prime",
            version="v1.0.0",
            source_branch="release/1.0",
            target_branch="production",
            update_dependents=False,
            push_to_remote=True,
        )
        assert spec.source_branch == "release/1.0"
        assert spec.target_branch == "production"
        assert spec.update_dependents is False
        assert spec.push_to_remote is True


class TestPlanRelease:
    """Tests for release planning."""

    def test_plan_basic_release(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="core", version="v0.1.0", update_dependents=False)
        plan = coordinator.plan_release(spec)

        assert plan.task == "Release core v0.1.0"
        assert len(plan.steps) == 3  # validate, merge, tag
        assert plan.requires_approval is True

    def test_plan_includes_validate_step(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="core", version="v0.1.0", update_dependents=False)
        plan = coordinator.plan_release(spec)

        validate_step = plan.steps[0]
        assert "validate" in validate_step.action.lower()
        assert validate_step.project == "core"
        assert len(validate_step.dependencies) == 0

    def test_plan_includes_merge_step(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="core", version="v0.1.0", update_dependents=False)
        plan = coordinator.plan_release(spec)

        merge_step = plan.steps[1]
        assert "merge" in merge_step.action.lower()
        assert "develop" in merge_step.action
        assert "main" in merge_step.action
        assert plan.steps[0].id in merge_step.dependencies

    def test_plan_includes_tag_step(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="core", version="v0.1.0", update_dependents=False)
        plan = coordinator.plan_release(spec)

        tag_step = plan.steps[2]
        assert "tag" in tag_step.action.lower()
        assert "v0.1.0" in tag_step.action
        assert plan.steps[1].id in tag_step.dependencies

    def test_plan_with_dependents(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="core", version="v0.1.0", update_dependents=True)
        plan = coordinator.plan_release(spec)

        # Should have: validate, merge, tag, update-prime, test-prime, update-edge, test-edge
        assert len(plan.steps) >= 7
        # Check that downstream projects are updated
        projects_in_plan = {step.project for step in plan.steps}
        assert "prime" in projects_in_plan
        assert "edge" in projects_in_plan

    def test_plan_with_push(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(
            project="core",
            version="v0.1.0",
            update_dependents=False,
            push_to_remote=True,
        )
        plan = coordinator.plan_release(spec)

        # Should include push step
        push_steps = [s for s in plan.steps if "push" in s.action.lower()]
        assert len(push_steps) >= 1
        assert plan.scope.affects_remote is True

    def test_plan_with_push_and_dependents(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(
            project="core",
            version="v0.1.0",
            update_dependents=True,
            push_to_remote=True,
        )
        plan = coordinator.plan_release(spec)

        # Should push core and all dependents
        push_steps = [s for s in plan.steps if "push" in s.action.lower()]
        push_projects = {step.project for step in push_steps}
        assert "core" in push_projects
        assert "prime" in push_projects
        assert "edge" in push_projects

    def test_plan_unknown_project_raises(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="unknown", version="v1.0.0")
        with pytest.raises(ValueError, match="Unknown project"):
            coordinator.plan_release(spec)

    def test_plan_scope_is_high_impact(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="core", version="v0.1.0")
        plan = coordinator.plan_release(spec)
        assert plan.scope.estimated_impact == "high"

    def test_plan_scope_includes_affected_projects(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="core", version="v0.1.0", update_dependents=True)
        plan = coordinator.plan_release(spec)

        # Core affects itself, Prime, and Edge
        assert "core" in plan.scope.projects
        assert "prime" in plan.scope.projects
        assert "edge" in plan.scope.projects


class TestExecuteRelease:
    """Tests for release execution."""

    def test_execute_logs_to_memory_on_success(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        coordinator = _make_coordinator(config, tmp_path)
        spec = ReleaseSpec(project="core", version="v0.2.0", update_dependents=False)

        result = coordinator.execute_release(spec, auto_approve=True)
        assert result.status == "success"

        # Check memory was logged
        recent = coordinator.memory.get_recent(limit=5)
        assert len(recent) > 0
        assert recent[0].category == "release"
        assert "core" in recent[0].content
        assert "v0.2.0" in recent[0].content


class TestValidateReleaseSpec:
    """Tests for release spec validation."""

    def test_valid_spec_returns_no_errors(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        spec = ReleaseSpec(project="core", version="v0.1.0")
        errors = validate_release_spec(spec, config)
        assert len(errors) == 0

    def test_unknown_project_returns_error(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        spec = ReleaseSpec(project="unknown", version="v0.1.0")
        errors = validate_release_spec(spec, config)
        assert len(errors) > 0
        assert "Unknown project" in errors[0]

    def test_empty_version_returns_error(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        spec = ReleaseSpec(project="core", version="")
        errors = validate_release_spec(spec, config)
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_version_without_v_prefix_returns_error(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        spec = ReleaseSpec(project="core", version="0.1.0")
        errors = validate_release_spec(spec, config)
        assert len(errors) > 0
        assert any("must start with 'v'" in e.lower() for e in errors)

    def test_same_source_and_target_returns_error(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        spec = ReleaseSpec(
            project="core", version="v0.1.0", source_branch="main", target_branch="main"
        )
        errors = validate_release_spec(spec, config)
        assert len(errors) > 0
        assert any("cannot be the same" in e.lower() for e in errors)


class TestParseVersionString:
    """Tests for version string parsing."""

    def test_parse_with_v_prefix(self) -> None:
        major, minor, patch = parse_version_string("v1.2.3")
        assert (major, minor, patch) == (1, 2, 3)

    def test_parse_without_v_prefix(self) -> None:
        major, minor, patch = parse_version_string("1.2.3")
        assert (major, minor, patch) == (1, 2, 3)

    def test_parse_zeros(self) -> None:
        major, minor, patch = parse_version_string("v0.0.0")
        assert (major, minor, patch) == (0, 0, 0)

    def test_parse_large_numbers(self) -> None:
        major, minor, patch = parse_version_string("v10.20.30")
        assert (major, minor, patch) == (10, 20, 30)

    def test_parse_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version_string("v1.2")

    def test_parse_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version_string("v1.a.3")


class TestSuggestNextVersion:
    """Tests for version suggestion."""

    def test_suggest_patch_bump(self) -> None:
        next_ver = suggest_next_version("v0.1.0", "patch")
        assert next_ver == "v0.1.1"

    def test_suggest_minor_bump(self) -> None:
        next_ver = suggest_next_version("v0.1.5", "minor")
        assert next_ver == "v0.2.0"

    def test_suggest_major_bump(self) -> None:
        next_ver = suggest_next_version("v0.3.7", "major")
        assert next_ver == "v1.0.0"

    def test_suggest_default_is_patch(self) -> None:
        next_ver = suggest_next_version("v1.0.0")
        assert next_ver == "v1.0.1"

    def test_suggest_invalid_bump_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid bump type"):
            suggest_next_version("v1.0.0", "invalid")
