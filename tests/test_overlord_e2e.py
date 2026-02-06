"""End-to-end integration tests for Overlord orchestration.

These tests exercise the full Overlord stack including autonomy, model routing,
dispatch, task parsing, and release coordination.
"""

from __future__ import annotations

from pathlib import Path

from nebulus_swarm.overlord.action_scope import ActionScope
from nebulus_swarm.overlord.autonomy import AutonomyEngine
from nebulus_swarm.overlord.dispatch import DispatchEngine, DispatchPlan, DispatchStep
from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.memory import OverlordMemory
from nebulus_swarm.overlord.model_router import ModelRouter
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.release import ReleaseCoordinator, ReleaseSpec
from nebulus_swarm.overlord.task_parser import TaskParser


def _make_config(tmp_path: Path, **autonomy_kwargs) -> OverlordConfig:
    """Build a test config with full dependency chain."""
    projects = {}

    # Core (base library)
    core_dir = tmp_path / "core"
    core_dir.mkdir(exist_ok=True)
    projects["core"] = ProjectConfig(
        name="core",
        path=core_dir,
        remote="test/core",
        role="shared-library",
        depends_on=[],
    )

    # Prime (depends on Core)
    prime_dir = tmp_path / "prime"
    prime_dir.mkdir(exist_ok=True)
    projects["prime"] = ProjectConfig(
        name="prime",
        path=prime_dir,
        remote="test/prime",
        role="platform-deployment",
        depends_on=["core"],
    )

    # Edge (depends on Core)
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
                "model": "llama",
                "tier": "local",
            },
            "cloud-fast": {
                "endpoint": "https://api.anthropic.com",
                "model": "haiku",
                "tier": "cloud-fast",
            },
            "cloud-heavy": {
                "endpoint": "https://api.anthropic.com",
                "model": "sonnet",
                "tier": "cloud-heavy",
            },
        },
        **autonomy_kwargs,
    )


def _build_stack(config: OverlordConfig, tmp_path: Path):
    """Build the full Overlord stack."""
    graph = DependencyGraph(config)
    autonomy = AutonomyEngine(config)
    router = ModelRouter(config)
    dispatch = DispatchEngine(config, autonomy, graph, router)
    memory = OverlordMemory(tmp_path / "memory.db")
    release = ReleaseCoordinator(config, graph, dispatch, memory)
    parser = TaskParser(graph)

    return {
        "config": config,
        "graph": graph,
        "autonomy": autonomy,
        "router": router,
        "dispatch": dispatch,
        "memory": memory,
        "release": release,
        "parser": parser,
    }


class TestCautiousMode:
    """E2E tests for cautious autonomy mode."""

    def test_cautious_blocks_all_execution(self, tmp_path: Path) -> None:
        """Cautious mode requires approval for everything."""
        config = _make_config(tmp_path, autonomy_global="cautious")
        stack = _build_stack(config, tmp_path)

        # Even safe local operations require approval
        scope = ActionScope(
            projects=["core"],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        plan = DispatchPlan(
            task="run tests",
            steps=[DispatchStep(id="s1", action="test", project="core")],
            scope=scope,
            estimated_duration=300,
            requires_approval=True,
        )

        result = stack["dispatch"].execute(plan, auto_approve=False)
        assert result.status == "cancelled"
        assert "approval" in result.reason.lower()

    def test_cautious_allows_with_approval(self, tmp_path: Path) -> None:
        """Cautious mode executes when approval is granted."""
        config = _make_config(tmp_path, autonomy_global="cautious")
        stack = _build_stack(config, tmp_path)

        scope = ActionScope(projects=["core"], estimated_impact="low")
        plan = DispatchPlan(
            task="run tests",
            steps=[DispatchStep(id="s1", action="test", project="core")],
            scope=scope,
            estimated_duration=300,
            requires_approval=True,
        )

        result = stack["dispatch"].execute(plan, auto_approve=True)
        assert result.status == "success"


class TestProactiveMode:
    """E2E tests for proactive autonomy mode."""

    def test_proactive_auto_approves_safe_local(self, tmp_path: Path) -> None:
        """Proactive mode auto-approves safe local operations."""
        config = _make_config(tmp_path, autonomy_global="proactive")
        stack = _build_stack(config, tmp_path)

        scope = ActionScope(
            projects=["core"],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        plan = DispatchPlan(
            task="run tests",
            steps=[DispatchStep(id="s1", action="test", project="core")],
            scope=scope,
            estimated_duration=300,
            requires_approval=True,
        )

        # Should auto-approve and execute
        result = stack["dispatch"].execute(plan, auto_approve=False)
        assert result.status == "success"

    def test_proactive_blocks_remote_operations(self, tmp_path: Path) -> None:
        """Proactive mode blocks operations affecting remote."""
        config = _make_config(tmp_path, autonomy_global="proactive")
        stack = _build_stack(config, tmp_path)

        scope = ActionScope(
            projects=["core"],
            destructive=False,
            affects_remote=True,
            estimated_impact="medium",
        )
        plan = DispatchPlan(
            task="push to remote",
            steps=[DispatchStep(id="s1", action="push", project="core")],
            scope=scope,
            estimated_duration=60,
            requires_approval=True,
        )

        result = stack["dispatch"].execute(plan, auto_approve=False)
        assert result.status == "cancelled"

    def test_proactive_blocks_destructive_operations(self, tmp_path: Path) -> None:
        """Proactive mode blocks destructive operations."""
        config = _make_config(tmp_path, autonomy_global="proactive")
        stack = _build_stack(config, tmp_path)

        scope = ActionScope(
            projects=["core"],
            destructive=True,
            affects_remote=False,
            estimated_impact="low",
        )
        plan = DispatchPlan(
            task="clean branches",
            steps=[DispatchStep(id="s1", action="clean", project="core")],
            scope=scope,
            estimated_duration=120,
            requires_approval=True,
        )

        result = stack["dispatch"].execute(plan, auto_approve=False)
        assert result.status == "cancelled"


class TestScheduledMode:
    """E2E tests for scheduled autonomy mode."""

    def test_scheduled_auto_executes_pre_approved(self, tmp_path: Path) -> None:
        """Scheduled mode auto-executes pre-approved actions."""
        config = _make_config(
            tmp_path,
            autonomy_global="scheduled",
            autonomy_pre_approved={"core": ["run tests"]},
        )
        stack = _build_stack(config, tmp_path)

        scope = ActionScope(projects=["core"], estimated_impact="low")
        plan = DispatchPlan(
            task="run tests",
            steps=[DispatchStep(id="s1", action="run tests", project="core")],
            scope=scope,
            estimated_duration=300,
            requires_approval=True,
        )

        result = stack["dispatch"].execute(plan, auto_approve=False)
        assert result.status == "success"

    def test_scheduled_blocks_non_approved(self, tmp_path: Path) -> None:
        """Scheduled mode blocks actions not in pre-approved list."""
        config = _make_config(
            tmp_path,
            autonomy_global="scheduled",
            autonomy_pre_approved={"core": ["run tests"]},
        )
        stack = _build_stack(config, tmp_path)

        scope = ActionScope(projects=["core"], estimated_impact="medium")
        plan = DispatchPlan(
            task="clean branches",
            steps=[DispatchStep(id="s1", action="clean branches", project="core")],
            scope=scope,
            estimated_duration=120,
            requires_approval=True,
        )

        result = stack["dispatch"].execute(plan, auto_approve=False)
        assert result.status == "cancelled"


class TestReleaseFlow:
    """E2E tests for coordinated release workflows."""

    def test_basic_release_workflow(self, tmp_path: Path) -> None:
        """Basic release without dependents."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        spec = ReleaseSpec(project="core", version="v0.1.0", update_dependents=False)
        result = stack["release"].execute_release(spec, auto_approve=True)

        assert result.status == "success"
        # Should have 3 steps: validate, merge, tag
        assert len(result.steps) == 3

    def test_release_with_dependents(self, tmp_path: Path) -> None:
        """Release updates downstream projects."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        spec = ReleaseSpec(project="core", version="v0.2.0", update_dependents=True)
        result = stack["release"].execute_release(spec, auto_approve=True)

        assert result.status == "success"
        # Should have: validate, merge, tag, update-prime, test-prime, update-edge, test-edge
        assert len(result.steps) >= 7

    def test_release_logs_to_memory(self, tmp_path: Path) -> None:
        """Successful release is logged to memory."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        spec = ReleaseSpec(project="prime", version="v1.0.0", update_dependents=False)
        result = stack["release"].execute_release(spec, auto_approve=True)

        assert result.status == "success"

        # Check memory
        recent = stack["memory"].get_recent(limit=5)
        assert len(recent) > 0
        assert recent[0].category == "release"
        assert "prime" in recent[0].content
        assert "v1.0.0" in recent[0].content


class TestModelRouterIntegration:
    """E2E tests for model router integration."""

    def test_router_selects_local_for_simple_tasks(self, tmp_path: Path) -> None:
        """Simple tasks route to local tier."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        endpoint = stack["router"].select_model("format", "low")
        assert endpoint is not None
        assert endpoint.tier == "local"

    def test_router_selects_cloud_fast_for_review(self, tmp_path: Path) -> None:
        """Review tasks route to cloud-fast."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        endpoint = stack["router"].select_model("review", "medium")
        assert endpoint is not None
        assert endpoint.tier == "cloud-fast"

    def test_router_falls_back_when_tier_unavailable(self, tmp_path: Path) -> None:
        """Router falls back when preferred tier is unavailable."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        # Clear local endpoints to simulate unavailability
        stack["router"].endpoints = {
            k: v for k, v in stack["router"].endpoints.items() if v.tier != "local"
        }

        # Format task prefers local, but should fall back
        endpoint = stack["router"].select_model("format", "low")
        assert endpoint is not None
        assert endpoint.tier in ("cloud-fast", "cloud-heavy")


class TestTaskParserIntegration:
    """E2E tests for task parser integration."""

    def test_parse_and_execute_merge(self, tmp_path: Path) -> None:
        """Parse merge task and execute."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        plan = stack["parser"].parse("merge core develop to main")
        result = stack["dispatch"].execute(plan, auto_approve=True)

        assert result.status == "success"
        assert len(result.steps) == 1
        assert "merge" in result.steps[0].output.lower()

    def test_parse_and_execute_multi_project_test(self, tmp_path: Path) -> None:
        """Parse multi-project test task and execute."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        plan = stack["parser"].parse("run tests across all projects")
        result = stack["dispatch"].execute(plan, auto_approve=True)

        assert result.status == "success"
        # Should run tests on all 3 projects
        assert len(result.steps) == 3
        projects = {step.project for step in plan.steps}
        assert projects == {"core", "prime", "edge"}


class TestDependencyGraphIntegration:
    """E2E tests for dependency graph integration."""

    def test_release_respects_dependency_order(self, tmp_path: Path) -> None:
        """Release plan respects dependency order."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        spec = ReleaseSpec(project="core", version="v0.3.0", update_dependents=True)
        plan = stack["release"].plan_release(spec)

        # Core steps should come before dependent updates
        core_steps = [s for s in plan.steps if s.project == "core"]
        prime_steps = [s for s in plan.steps if s.project == "prime"]
        edge_steps = [s for s in plan.steps if s.project == "edge"]

        assert len(core_steps) > 0
        assert len(prime_steps) > 0
        assert len(edge_steps) > 0

        # All core steps should have lower IDs (execute first)
        core_ids = [int(s.id.split("-")[1]) for s in core_steps]
        prime_ids = [int(s.id.split("-")[1]) for s in prime_steps]
        edge_ids = [int(s.id.split("-")[1]) for s in edge_steps]

        assert max(core_ids) < min(prime_ids)
        assert max(core_ids) < min(edge_ids)

    def test_affected_projects_includes_downstream(self, tmp_path: Path) -> None:
        """get_affected_by includes all downstream projects."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        affected = stack["graph"].get_affected_by("core")
        assert "core" in affected
        assert "prime" in affected
        assert "edge" in affected


class TestMemoryIntegration:
    """E2E tests for memory integration."""

    def test_memory_persists_across_operations(self, tmp_path: Path) -> None:
        """Memory persists across multiple operations."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        # Execute multiple releases
        spec1 = ReleaseSpec(project="core", version="v0.1.0", update_dependents=False)
        stack["release"].execute_release(spec1, auto_approve=True)

        spec2 = ReleaseSpec(project="prime", version="v1.0.0", update_dependents=False)
        stack["release"].execute_release(spec2, auto_approve=True)

        # Check both are in memory
        recent = stack["memory"].get_recent(limit=10)
        assert len(recent) >= 2

        contents = [entry.content for entry in recent]
        assert any("core" in c and "v0.1.0" in c for c in contents)
        assert any("prime" in c and "v1.0.0" in c for c in contents)

    def test_memory_project_history_filter(self, tmp_path: Path) -> None:
        """Memory can be filtered by project."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        # Execute releases for different projects
        stack["release"].execute_release(
            ReleaseSpec(project="core", version="v0.1.0"), auto_approve=True
        )
        stack["release"].execute_release(
            ReleaseSpec(project="prime", version="v1.0.0"), auto_approve=True
        )

        # Get core-specific history
        core_history = stack["memory"].get_project_history("core", limit=10)
        assert len(core_history) > 0
        assert all(entry.project == "core" for entry in core_history)


class TestFailureHandling:
    """E2E tests for failure handling and rollback."""

    def test_dispatch_stops_on_step_failure(self, tmp_path: Path) -> None:
        """Dispatch stops execution when a step fails."""
        config = _make_config(tmp_path)
        stack = _build_stack(config, tmp_path)

        # Clear all model endpoints to force LLM step failure
        stack["router"].endpoints.clear()

        scope = ActionScope(projects=["core"], estimated_impact="low")
        plan = DispatchPlan(
            task="multi-step with failure",
            steps=[
                DispatchStep(
                    id="s1", action="will fail", project="core", model_tier="cloud-fast"
                ),
                DispatchStep(id="s2", action="should not run", project="core"),
            ],
            scope=scope,
            estimated_duration=600,
            requires_approval=False,
        )

        result = stack["dispatch"].execute(plan, auto_approve=True)
        assert result.status == "failed"
        # Only first step should have been attempted
        assert len(result.steps) == 1
