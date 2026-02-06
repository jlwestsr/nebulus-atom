"""Tests for the Overlord autonomy engine."""

from __future__ import annotations

from pathlib import Path


from nebulus_swarm.overlord.action_scope import ActionScope
from nebulus_swarm.overlord.autonomy import AutonomyEngine, get_autonomy_summary
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig


def _make_config(tmp_path: Path, **autonomy_kwargs) -> OverlordConfig:
    """Build a test config with autonomy settings."""
    projects = {}
    for name in ("core", "prime", "edge"):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name, path=d, remote=f"test/{name}", role="tooling"
        )

    return OverlordConfig(projects=projects, **autonomy_kwargs)


class TestGetLevel:
    """Tests for AutonomyEngine.get_level."""

    def test_returns_global_when_no_override(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        assert engine.get_level("core") == "proactive"

    def test_returns_override_when_present(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            autonomy_global="proactive",
            autonomy_overrides={"core": "cautious"},
        )
        engine = AutonomyEngine(config)
        assert engine.get_level("core") == "cautious"
        assert engine.get_level("prime") == "proactive"

    def test_returns_global_when_no_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="scheduled")
        engine = AutonomyEngine(config)
        assert engine.get_level(None) == "scheduled"


class TestCanAutoExecute:
    """Tests for AutonomyEngine.can_auto_execute."""

    def test_cautious_never_auto_executes(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="cautious")
        engine = AutonomyEngine(config)
        scope = ActionScope(estimated_impact="low", affects_remote=False)
        assert not engine.can_auto_execute("any action", scope)

    def test_proactive_auto_executes_safe_local(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        scope = ActionScope(
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        assert engine.can_auto_execute("safe action", scope)

    def test_proactive_denies_remote(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        scope = ActionScope(affects_remote=True, estimated_impact="low")
        assert not engine.can_auto_execute("push", scope)

    def test_proactive_denies_destructive(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        scope = ActionScope(destructive=True, estimated_impact="low")
        assert not engine.can_auto_execute("force push", scope)

    def test_proactive_denies_high_impact(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        scope = ActionScope(estimated_impact="high")
        assert not engine.can_auto_execute("release", scope)

    def test_scheduled_auto_executes_pre_approved(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            autonomy_global="scheduled",
            autonomy_pre_approved={"core": ["run tests"]},
        )
        engine = AutonomyEngine(config)
        scope = ActionScope(projects=["core"])
        assert engine.can_auto_execute("run tests", scope)

    def test_scheduled_denies_non_approved(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            autonomy_global="scheduled",
            autonomy_pre_approved={"core": ["run tests"]},
        )
        engine = AutonomyEngine(config)
        scope = ActionScope(projects=["core"])
        assert not engine.can_auto_execute("push to remote", scope)

    def test_scheduled_denies_when_missing_from_one_project(
        self, tmp_path: Path
    ) -> None:
        config = _make_config(
            tmp_path,
            autonomy_global="scheduled",
            autonomy_pre_approved={
                "core": ["run tests"],
                "prime": ["clean branches"],
            },
        )
        engine = AutonomyEngine(config)
        scope = ActionScope(projects=["core", "prime"])
        # "run tests" is approved for core but not prime
        assert not engine.can_auto_execute("run tests", scope)


class TestShouldPropose:
    """Tests for AutonomyEngine.should_propose."""

    def test_cautious_never_proposes(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="cautious")
        engine = AutonomyEngine(config)
        scope = ActionScope(estimated_impact="low")
        assert not engine.should_propose("any action", scope)

    def test_proactive_proposes_low_impact(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        scope = ActionScope(estimated_impact="low")
        assert engine.should_propose("clean branches", scope)

    def test_proactive_proposes_medium_impact(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        scope = ActionScope(estimated_impact="medium")
        assert engine.should_propose("merge", scope)

    def test_proactive_does_not_propose_high_impact(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        scope = ActionScope(estimated_impact="high")
        assert not engine.should_propose("release", scope)

    def test_scheduled_proposes_non_approved(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            autonomy_global="scheduled",
            autonomy_pre_approved={"core": ["run tests"]},
        )
        engine = AutonomyEngine(config)
        scope = ActionScope(projects=["core"])
        assert engine.should_propose("push to remote", scope)

    def test_scheduled_does_not_propose_approved(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            autonomy_global="scheduled",
            autonomy_pre_approved={"core": ["run tests"]},
        )
        engine = AutonomyEngine(config)
        scope = ActionScope(projects=["core"])
        assert not engine.should_propose("run tests", scope)


class TestShouldEscalate:
    """Tests for AutonomyEngine.should_escalate."""

    def test_escalates_destructive_remote(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = AutonomyEngine(config)
        scope = ActionScope(destructive=True, affects_remote=True)
        assert engine.should_escalate(scope)

    def test_escalates_high_impact_multi_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = AutonomyEngine(config)
        scope = ActionScope(estimated_impact="high", projects=["core", "prime", "edge"])
        assert engine.should_escalate(scope)

    def test_does_not_escalate_high_impact_single_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = AutonomyEngine(config)
        scope = ActionScope(estimated_impact="high", projects=["core"])
        assert not engine.should_escalate(scope)

    def test_does_not_escalate_safe_operations(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        engine = AutonomyEngine(config)
        scope = ActionScope(
            destructive=False, affects_remote=False, estimated_impact="low"
        )
        assert not engine.should_escalate(scope)


class TestGetProjectConfig:
    """Tests for AutonomyEngine.get_project_config."""

    def test_returns_config_with_level_and_approved(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            autonomy_global="proactive",
            autonomy_overrides={"core": "cautious"},
            autonomy_pre_approved={"core": ["run tests", "clean branches"]},
        )
        engine = AutonomyEngine(config)
        proj_config = engine.get_project_config("core")

        assert proj_config.project == "core"
        assert proj_config.level == "cautious"
        assert proj_config.pre_approved_actions == ["run tests", "clean branches"]

    def test_returns_empty_approved_when_none(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="proactive")
        engine = AutonomyEngine(config)
        proj_config = engine.get_project_config("prime")

        assert proj_config.project == "prime"
        assert proj_config.level == "proactive"
        assert proj_config.pre_approved_actions == []


class TestGetAutonomySummary:
    """Tests for get_autonomy_summary."""

    def test_returns_global_and_projects(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            autonomy_global="proactive",
            autonomy_overrides={"core": "cautious", "edge": "scheduled"},
        )
        summary = get_autonomy_summary(config)

        assert summary["__global__"] == "proactive"
        assert summary["core"] == "cautious"
        assert summary["prime"] == "proactive"
        assert summary["edge"] == "scheduled"

    def test_all_projects_included(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, autonomy_global="cautious")
        summary = get_autonomy_summary(config)

        assert "__global__" in summary
        assert "core" in summary
        assert "prime" in summary
        assert "edge" in summary
