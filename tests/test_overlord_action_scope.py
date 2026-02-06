"""Tests for the Overlord action scope model and blast radius evaluation."""

from __future__ import annotations

from pathlib import Path

from nebulus_swarm.overlord.action_scope import (
    SCOPE_LOCAL_MERGE,
    SCOPE_PUSH,
    SCOPE_READ_ONLY,
    SCOPE_RELEASE,
    ActionScope,
    evaluate_scope,
    scope_for_merge,
    scope_for_push,
    scope_for_release,
)
from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Minimal config for scope tests."""
    projects = {}
    for name in ("core", "prime", "edge"):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name, path=d, remote=f"test/{name}", role="tooling"
        )
    projects["prime"].depends_on = ["core"]
    projects["edge"].depends_on = ["core"]
    return OverlordConfig(projects=projects)


class TestPreBuiltScopes:
    """Tests for the pre-built scope constants."""

    def test_read_only_is_safe(self) -> None:
        assert not SCOPE_READ_ONLY.destructive
        assert SCOPE_READ_ONLY.reversible
        assert not SCOPE_READ_ONLY.affects_remote
        assert SCOPE_READ_ONLY.estimated_impact == "low"

    def test_local_merge_is_reversible(self) -> None:
        assert not SCOPE_LOCAL_MERGE.destructive
        assert SCOPE_LOCAL_MERGE.reversible
        assert not SCOPE_LOCAL_MERGE.affects_remote

    def test_push_affects_remote(self) -> None:
        assert SCOPE_PUSH.affects_remote
        assert not SCOPE_PUSH.reversible

    def test_release_is_high_impact(self) -> None:
        assert SCOPE_RELEASE.estimated_impact == "high"
        assert SCOPE_RELEASE.affects_remote


class TestEvaluateScope:
    """Tests for evaluate_scope."""

    def test_destructive_remote_always_denied(self) -> None:
        scope = ActionScope(
            destructive=True,
            affects_remote=True,
            estimated_impact="low",
        )
        verdict = evaluate_scope(scope, "scheduled", OverlordConfig())
        assert not verdict.approved
        assert verdict.escalation_required

    def test_cautious_denies_medium_impact(self) -> None:
        scope = ActionScope(estimated_impact="medium")
        verdict = evaluate_scope(scope, "cautious", OverlordConfig())
        assert not verdict.approved

    def test_cautious_approves_low_local(self) -> None:
        scope = ActionScope(estimated_impact="low", affects_remote=False)
        verdict = evaluate_scope(scope, "cautious", OverlordConfig())
        assert verdict.approved

    def test_cautious_denies_low_remote(self) -> None:
        scope = ActionScope(estimated_impact="low", affects_remote=True)
        verdict = evaluate_scope(scope, "cautious", OverlordConfig())
        assert not verdict.approved

    def test_proactive_approves_low(self) -> None:
        scope = ActionScope(estimated_impact="low")
        verdict = evaluate_scope(scope, "proactive", OverlordConfig())
        assert verdict.approved

    def test_proactive_denies_medium(self) -> None:
        scope = ActionScope(estimated_impact="medium")
        verdict = evaluate_scope(scope, "proactive", OverlordConfig())
        assert not verdict.approved

    def test_proactive_escalates_high(self) -> None:
        scope = ActionScope(estimated_impact="high")
        verdict = evaluate_scope(scope, "proactive", OverlordConfig())
        assert not verdict.approved
        assert verdict.escalation_required

    def test_scheduled_approves_low(self) -> None:
        scope = ActionScope(estimated_impact="low")
        verdict = evaluate_scope(scope, "scheduled", OverlordConfig())
        assert verdict.approved

    def test_scheduled_approves_medium_local(self) -> None:
        scope = ActionScope(estimated_impact="medium", affects_remote=False)
        verdict = evaluate_scope(scope, "scheduled", OverlordConfig())
        assert verdict.approved

    def test_scheduled_denies_medium_remote(self) -> None:
        scope = ActionScope(estimated_impact="medium", affects_remote=True)
        verdict = evaluate_scope(scope, "scheduled", OverlordConfig())
        assert not verdict.approved
        assert verdict.escalation_required

    def test_scheduled_denies_high(self) -> None:
        scope = ActionScope(estimated_impact="high")
        verdict = evaluate_scope(scope, "scheduled", OverlordConfig())
        assert not verdict.approved
        assert verdict.escalation_required

    def test_unknown_autonomy_denies(self) -> None:
        scope = ActionScope(estimated_impact="low")
        verdict = evaluate_scope(scope, "yolo", OverlordConfig())
        assert not verdict.approved
        assert verdict.escalation_required


class TestScopeBuilders:
    """Tests for scope_for_merge, scope_for_push, scope_for_release."""

    def test_scope_for_merge(self) -> None:
        scope = scope_for_merge("my-proj", "feat/x", "develop")
        assert scope.projects == ["my-proj"]
        assert "feat/x" in scope.branches
        assert "develop" in scope.branches
        assert not scope.affects_remote
        assert scope.reversible

    def test_scope_for_push_single(self) -> None:
        scope = scope_for_push(["my-proj"])
        assert scope.affects_remote
        assert scope.estimated_impact == "medium"

    def test_scope_for_push_multiple(self) -> None:
        scope = scope_for_push(["a", "b", "c"])
        assert scope.estimated_impact == "high"

    def test_scope_for_release_includes_downstream(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        graph = DependencyGraph(config)
        scope = scope_for_release("core", graph)
        assert "core" in scope.projects
        assert "prime" in scope.projects
        assert "edge" in scope.projects
        assert scope.estimated_impact == "high"
        assert scope.affects_remote
