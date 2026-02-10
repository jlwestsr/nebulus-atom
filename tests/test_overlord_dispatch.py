"""Tests for Overlord Dispatch Engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from nebulus_swarm.overlord.action_scope import ActionScope
from nebulus_swarm.overlord.autonomy import AutonomyEngine
from nebulus_swarm.overlord.dispatch import (
    DispatchEngine,
    DispatchPlan,
    DispatchStep,
    build_simple_plan,
)
from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.model_router import ModelRouter
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Build a test config."""
    projects = {}
    for name in ("core", "prime", "edge"):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name, path=d, remote=f"test/{name}", role="tooling"
        )

    return OverlordConfig(
        projects=projects,
        autonomy_global="proactive",
        models={
            "local": {
                "endpoint": "http://localhost:5000",
                "model": "test",
                "tier": "local",
            }
        },
        workers={},
    )


def _make_engine(config: OverlordConfig) -> DispatchEngine:
    """Build a dispatch engine with dependencies."""
    autonomy = AutonomyEngine(config)
    graph = DependencyGraph(config)
    router = ModelRouter(config)
    return DispatchEngine(config, autonomy, graph, router)


class TestDispatchStep:
    """Tests for DispatchStep dataclass."""

    def test_creates_with_required_fields(self) -> None:
        step = DispatchStep(id="step-1", action="test action", project="core")
        assert step.id == "step-1"
        assert step.action == "test action"
        assert step.project == "core"
        assert step.dependencies == []
        assert step.model_tier is None
        assert step.timeout == 300

    def test_creates_with_all_fields(self) -> None:
        step = DispatchStep(
            id="step-2",
            action="complex action",
            project="prime",
            dependencies=["step-1"],
            model_tier="cloud-fast",
            timeout=600,
        )
        assert step.dependencies == ["step-1"]
        assert step.model_tier == "cloud-fast"
        assert step.timeout == 600


class TestDispatchPlan:
    """Tests for DispatchPlan dataclass."""

    def test_creates_plan(self) -> None:
        scope = ActionScope(projects=["core"], estimated_impact="low")
        steps = [DispatchStep(id="s1", action="test", project="core")]
        plan = DispatchPlan(
            task="test task",
            steps=steps,
            scope=scope,
            estimated_duration=300,
            requires_approval=False,
        )
        assert plan.task == "test task"
        assert len(plan.steps) == 1
        assert plan.requires_approval is False


class TestTopologicalOrder:
    """Tests for topological ordering of steps."""

    def test_single_step_no_deps(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        steps = [DispatchStep(id="s1", action="test", project="core")]
        ordered = engine._topological_order(steps)
        assert len(ordered) == 1
        assert ordered[0].id == "s1"

    def test_linear_chain(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        steps = [
            DispatchStep(id="s1", action="first", project="core"),
            DispatchStep(id="s2", action="second", project="core", dependencies=["s1"]),
            DispatchStep(id="s3", action="third", project="core", dependencies=["s2"]),
        ]
        ordered = engine._topological_order(steps)
        assert [s.id for s in ordered] == ["s1", "s2", "s3"]

    def test_parallel_steps(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        steps = [
            DispatchStep(id="s1", action="first", project="core"),
            DispatchStep(id="s2", action="parallel-1", project="prime"),
            DispatchStep(id="s3", action="parallel-2", project="edge"),
        ]
        ordered = engine._topological_order(steps)
        assert len(ordered) == 3
        # All have no deps, so original order is maintained

    def test_diamond_dependency(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        steps = [
            DispatchStep(id="s1", action="root", project="core"),
            DispatchStep(
                id="s2", action="branch-1", project="prime", dependencies=["s1"]
            ),
            DispatchStep(
                id="s3", action="branch-2", project="edge", dependencies=["s1"]
            ),
            DispatchStep(
                id="s4", action="merge", project="core", dependencies=["s2", "s3"]
            ),
        ]
        ordered = engine._topological_order(steps)
        ids = [s.id for s in ordered]
        # s1 must come first
        assert ids[0] == "s1"
        # s2 and s3 can be in any order but must come before s4
        assert ids[3] == "s4"
        assert set(ids[1:3]) == {"s2", "s3"}

    def test_circular_dependency_returns_original_order(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        steps = [
            DispatchStep(id="s1", action="first", project="core", dependencies=["s2"]),
            DispatchStep(id="s2", action="second", project="core", dependencies=["s1"]),
        ]
        ordered = engine._topological_order(steps)
        # Should return original order as fallback
        assert len(ordered) == 2


class TestExecuteStep:
    """Tests for single step execution."""

    def test_execute_direct_step_unmapped(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        step = DispatchStep(
            id="s1", action="custom unmapped action", project="core", model_tier=None
        )
        result = engine._execute_step(step)
        assert result.step_id == "s1"
        assert result.success is True
        assert "Simulated" in result.output

    def test_execute_llm_step(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        step = DispatchStep(
            id="s1", action="review code", project="core", model_tier="cloud-fast"
        )
        result = engine._execute_step(step)
        assert result.step_id == "s1"
        assert result.success is True
        assert "Dispatched" in result.output


class TestExecutePlan:
    """Tests for full plan execution."""

    def test_execute_single_step_plan(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        scope = ActionScope(projects=["core"], estimated_impact="low")
        plan = DispatchPlan(
            task="custom task",
            steps=[
                DispatchStep(id="s1", action="custom unmapped action", project="core")
            ],
            scope=scope,
            estimated_duration=300,
            requires_approval=False,
        )
        result = engine.execute(plan, auto_approve=True)
        assert result.status == "success"
        assert len(result.steps) == 1

    def test_execute_multi_step_plan(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        scope = ActionScope(projects=["core"], estimated_impact="low")
        plan = DispatchPlan(
            task="multi-step",
            steps=[
                DispatchStep(id="s1", action="first", project="core"),
                DispatchStep(
                    id="s2", action="second", project="core", dependencies=["s1"]
                ),
            ],
            scope=scope,
            estimated_duration=600,
            requires_approval=False,
        )
        result = engine.execute(plan, auto_approve=True)
        assert result.status == "success"
        assert len(result.steps) == 2

    def test_execute_stops_on_failure(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)

        # Simulate failure by having no model available
        engine.router.endpoints.clear()

        scope = ActionScope(projects=["core"], estimated_impact="low")
        plan = DispatchPlan(
            task="test",
            steps=[
                DispatchStep(
                    id="s1", action="first", project="core", model_tier="cloud-fast"
                ),
                DispatchStep(
                    id="s2", action="second", project="core", dependencies=["s1"]
                ),
            ],
            scope=scope,
            estimated_duration=600,
            requires_approval=False,
        )
        result = engine.execute(plan, auto_approve=True)
        assert result.status == "failed"
        assert len(result.steps) == 1  # Only first step attempted


class TestAutonomyIntegration:
    """Tests for autonomy engine integration."""

    def test_cautious_blocks_without_approval(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.autonomy_global = "cautious"
        engine = _make_engine(config)
        scope = ActionScope(projects=["core"], estimated_impact="low")
        plan = DispatchPlan(
            task="test",
            steps=[DispatchStep(id="s1", action="test", project="core")],
            scope=scope,
            estimated_duration=300,
            requires_approval=True,
        )
        result = engine.execute(plan, auto_approve=False)
        assert result.status == "cancelled"
        assert "approval" in result.reason.lower()

    def test_proactive_allows_safe_local(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.autonomy_global = "proactive"
        engine = _make_engine(config)
        scope = ActionScope(
            projects=["core"],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        plan = DispatchPlan(
            task="test",
            steps=[DispatchStep(id="s1", action="test", project="core")],
            scope=scope,
            estimated_duration=300,
            requires_approval=True,
        )
        # Check if can auto-approve
        can_approve = engine._can_auto_approve(plan)
        assert can_approve is True


class TestInferTaskType:
    """Tests for task type inference."""

    def test_infers_format_task(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._infer_task_type("format code") == "format"
        assert engine._infer_task_type("lint files") == "format"

    def test_infers_review_task(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._infer_task_type("review pull request") == "review"
        assert engine._infer_task_type("check code quality") == "review"

    def test_infers_feature_task(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._infer_task_type("add new feature") == "feature"
        assert engine._infer_task_type("implement API") == "feature"

    def test_infers_architecture_task(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._infer_task_type("design system") == "architecture"
        assert engine._infer_task_type("plan migration") == "architecture"

    def test_defaults_to_feature(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._infer_task_type("unknown action") == "feature"


class TestActionToCommand:
    """Tests for _action_to_command static method."""

    def test_maps_run_tests(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._action_to_command("run tests") == "pytest -v"

    def test_maps_run_test_singular(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._action_to_command("run test suite") == "pytest -v"

    def test_maps_lint(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._action_to_command("lint") == "ruff check ."

    def test_maps_format_code(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._action_to_command("format code") == "ruff format ."

    def test_bare_test_does_not_match(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._action_to_command("test") is None

    def test_validate_tests_does_not_match(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._action_to_command("validate tests") is None

    def test_maps_merge_to(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        cmd = engine._action_to_command("merge develop to main")
        assert cmd == "git checkout main && git merge --no-ff develop"

    def test_maps_merge_into(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        cmd = engine._action_to_command("merge feature/x into develop")
        assert cmd == "git checkout develop && git merge --no-ff feature/x"

    def test_maps_checkout(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._action_to_command("checkout develop") == "git checkout develop"

    def test_returns_none_for_unknown(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine._action_to_command("do something custom") is None


class TestExecuteDirectMapped:
    """Tests for _execute_direct with mapped commands."""

    def test_execute_mapped_command_success(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        # Create pyproject.toml so _can_execute_in passes for pytest
        (tmp_path / "core" / "pyproject.toml").write_text("[project]\nname='core'\n")
        engine = _make_engine(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="all tests passed", stderr=""
            )
            step = DispatchStep(
                id="s1", action="run tests", project="core", model_tier=None
            )
            result = engine._execute_direct(step)
            assert result["success"] is True
            assert result["output"] == "all tests passed"

    def test_execute_mapped_command_failure(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        # Create pyproject.toml so _can_execute_in passes for pytest
        (tmp_path / "core" / "pyproject.toml").write_text("[project]\nname='core'\n")
        engine = _make_engine(config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="2 tests failed"
            )
            step = DispatchStep(
                id="s1", action="run tests", project="core", model_tier=None
            )
            result = engine._execute_direct(step)
            assert result["success"] is False
            assert "2 tests failed" in result["error"]


class TestWorkerInitialization:
    """Tests for worker initialization in DispatchEngine."""

    def test_no_workers_config(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = _make_engine(config)
        assert engine.claude_worker is None

    def test_worker_disabled_by_default(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.workers = {"claude": {"enabled": False}}
        engine = _make_engine(config)
        assert engine.claude_worker is None

    def test_worker_enabled_binary_found(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.workers = {
            "claude": {
                "enabled": True,
                "binary_path": "claude",
                "default_model": "sonnet",
            }
        }
        with patch("shutil.which", return_value="/usr/bin/claude"):
            engine = _make_engine(config)
        assert engine.claude_worker is not None

    def test_worker_enabled_binary_missing(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.workers = {"claude": {"enabled": True, "binary_path": "nonexistent"}}
        engine = _make_engine(config)
        assert engine.claude_worker is None


class TestBuildSimplePlan:
    """Tests for build_simple_plan helper."""

    def test_builds_single_step_plan(self) -> None:
        scope = ActionScope(projects=["core"], estimated_impact="low")
        plan = build_simple_plan("test task", "core", scope, requires_approval=False)
        assert plan.task == "test task"
        assert len(plan.steps) == 1
        assert plan.steps[0].project == "core"
        assert plan.requires_approval is False
