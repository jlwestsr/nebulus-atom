"""Tests for Overlord Proactive Detection Patterns."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from nebulus_swarm.overlord.autonomy import AutonomyEngine
from nebulus_swarm.overlord.detectors import (
    AheadOfMainDetector,
    DetectionEngine,
    DetectionResult,
    FailingTestDetector,
    StaleBranchDetector,
)
from nebulus_swarm.overlord.graph import DependencyGraph
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
        autonomy_global="cautious",
        models={
            "local": {
                "endpoint": "http://localhost:5000",
                "model": "test",
                "tier": "local",
            }
        },
    )


def _make_status(
    name: str = "core",
    branch: str = "develop",
    clean: bool = True,
    ahead: int = 0,
    stale_branches: list | None = None,
    has_tests: bool = True,
    issues: list | None = None,
) -> MagicMock:
    """Build a mock ProjectStatus."""
    mock = MagicMock()
    mock.name = name
    mock.git = MagicMock(
        branch=branch,
        clean=clean,
        ahead=ahead,
        behind=0,
        stale_branches=stale_branches or [],
        last_commit="test commit",
        last_commit_date="2026-02-06",
        tags=[],
    )
    mock.tests = MagicMock(
        has_tests=has_tests, test_command="pytest" if has_tests else None
    )
    mock.issues = issues or []
    mock.config = MagicMock(role="tooling")
    return mock


# --- Stale Branch Detector Tests ---


class TestStaleBranchDetector:
    """Tests for stale branch detection."""

    def test_no_stale_branches(self) -> None:
        detector = StaleBranchDetector()
        status = _make_status(stale_branches=[])
        results = detector.detect(status)
        assert results == []

    def test_single_stale_branch(self) -> None:
        detector = StaleBranchDetector(threshold_days=7)
        status = _make_status(stale_branches=["old-feature"])
        results = detector.detect(status)
        assert len(results) == 1
        assert results[0].detector == "stale-branch"
        assert results[0].severity == "low"
        assert "old-feature" in results[0].description

    def test_multiple_stale_branches(self) -> None:
        detector = StaleBranchDetector()
        status = _make_status(stale_branches=["old-1", "old-2", "old-3"])
        results = detector.detect(status)
        assert len(results) == 3

    def test_proposed_action_includes_project(self) -> None:
        detector = StaleBranchDetector()
        status = _make_status(name="prime", stale_branches=["dead"])
        results = detector.detect(status)
        assert "prime" in results[0].proposed_action

    def test_custom_threshold(self) -> None:
        detector = StaleBranchDetector(threshold_days=14)
        status = _make_status(stale_branches=["stale"])
        results = detector.detect(status)
        assert ">14 days" in results[0].description


# --- Ahead of Main Detector Tests ---


class TestAheadOfMainDetector:
    """Tests for ahead-of-main detection."""

    def test_not_ahead(self) -> None:
        detector = AheadOfMainDetector()
        status = _make_status(ahead=0)
        results = detector.detect(status)
        assert results == []

    def test_slightly_ahead(self) -> None:
        detector = AheadOfMainDetector()
        status = _make_status(ahead=3)
        results = detector.detect(status)
        assert len(results) == 1
        assert results[0].severity == "low"
        assert "3 commits ahead" in results[0].description

    def test_significantly_ahead(self) -> None:
        detector = AheadOfMainDetector()
        status = _make_status(ahead=10)
        results = detector.detect(status)
        assert len(results) == 1
        assert results[0].severity == "medium"

    def test_proposed_merge_action(self) -> None:
        detector = AheadOfMainDetector()
        status = _make_status(name="core", ahead=2)
        results = detector.detect(status)
        assert "merge" in results[0].proposed_action.lower()
        assert "core" in results[0].proposed_action


# --- Failing Test Detector Tests ---


class TestFailingTestDetector:
    """Tests for failing test detection."""

    def test_no_tests_detected(self) -> None:
        detector = FailingTestDetector()
        status = _make_status(has_tests=False)
        results = detector.detect(status)
        assert len(results) == 1
        assert results[0].severity == "medium"
        assert "No test" in results[0].description

    def test_tests_passing(self) -> None:
        detector = FailingTestDetector()
        status = _make_status(has_tests=True, issues=[])
        results = detector.detect(status)
        assert results == []

    def test_test_failure_in_issues(self) -> None:
        detector = FailingTestDetector()
        status = _make_status(has_tests=True, issues=["Test failures detected"])
        results = detector.detect(status)
        assert len(results) == 1
        assert results[0].severity == "high"

    def test_non_test_issues_ignored(self) -> None:
        detector = FailingTestDetector()
        status = _make_status(has_tests=True, issues=["Dirty working tree"])
        results = detector.detect(status)
        assert results == []


# --- Detection Engine Tests ---


class TestDetectionEngine:
    """Tests for the detection engine orchestrator."""

    def test_creates_with_all_detectors(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)
        assert len(engine.detectors) == 3

    def test_run_all_ecosystem(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)

        statuses = [
            _make_status(name="core", stale_branches=["old"]),
            _make_status(name="prime", ahead=5),
        ]
        with patch(
            "nebulus_swarm.overlord.detectors.scan_ecosystem",
            return_value=statuses,
        ):
            results = engine.run_all()
            assert len(results) >= 2  # At least stale + ahead

    def test_run_all_single_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)

        status = _make_status(name="core", ahead=3)
        with patch(
            "nebulus_swarm.overlord.detectors.scan_project",
            return_value=status,
        ):
            results = engine.run_all(project="core")
            assert any(r.detector == "ahead-of-main" for r in results)

    def test_run_all_unknown_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)
        results = engine.run_all(project="nonexistent")
        assert results == []

    def test_format_summary_empty(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)
        assert "No issues" in engine.format_summary([])

    def test_format_summary_with_results(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)
        results = [
            DetectionResult(
                detector="stale-branch",
                project="core",
                severity="low",
                description="Branch old is stale",
                proposed_action="clean branches",
            )
        ]
        summary = engine.format_summary(results)
        assert "1 findings" in summary
        assert "core" in summary


# --- Autonomy Filtering Tests ---


class TestAutonomyFiltering:
    """Tests for detection result filtering by autonomy level."""

    def test_cautious_surfaces_all(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.autonomy_global = "cautious"
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)

        results = [
            DetectionResult("d1", "core", "low", "desc", "action"),
            DetectionResult("d2", "core", "high", "desc", "action"),
        ]
        filtered = engine.filter_by_autonomy(results)
        assert len(filtered) == 2

    def test_proactive_filters_by_severity(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.autonomy_global = "proactive"
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)

        results = [
            DetectionResult("d1", "core", "low", "desc", "action"),
            DetectionResult("d2", "core", "medium", "desc", "action"),
            DetectionResult("d3", "core", "high", "desc", "action"),
        ]
        filtered = engine.filter_by_autonomy(results)
        assert len(filtered) == 2  # low + medium only

    def test_scheduled_passes_all(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.autonomy_global = "scheduled"
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)

        results = [
            DetectionResult("d1", "core", "high", "desc", "action"),
        ]
        filtered = engine.filter_by_autonomy(results)
        assert len(filtered) == 1


# --- Edge Cases ---


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_ecosystem(self, tmp_path: Path) -> None:
        config = OverlordConfig(
            models={
                "local": {
                    "endpoint": "http://localhost:5000",
                    "model": "test",
                    "tier": "local",
                }
            }
        )
        graph = DependencyGraph(config)
        autonomy = AutonomyEngine(config)
        engine = DetectionEngine(config, graph, autonomy)
        with patch(
            "nebulus_swarm.overlord.detectors.scan_ecosystem",
            return_value=[],
        ):
            results = engine.run_all()
            assert results == []

    def test_detection_result_dataclass(self) -> None:
        result = DetectionResult(
            detector="test",
            project="core",
            severity="low",
            description="test desc",
            proposed_action="do something",
        )
        assert result.detector == "test"
        assert result.project == "core"
        assert result.severity == "low"
