"""Tests for Overlord Task Parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.task_parser import TaskParser


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Build a test config."""
    projects = {}
    for name in ("core", "prime", "edge"):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name, path=d, remote=f"test/{name}", role="tooling"
        )

    return OverlordConfig(projects=projects)


def _make_parser(config: OverlordConfig) -> TaskParser:
    """Build a task parser."""
    graph = DependencyGraph(config)
    return TaskParser(graph)


class TestParseMerge:
    """Tests for merge task parsing."""

    def test_parse_merge_basic(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("merge core develop to main")
        assert plan.task == "merge core develop to main"
        assert len(plan.steps) == 1
        assert plan.steps[0].project == "core"
        assert "merge" in plan.steps[0].action.lower()

    def test_parse_merge_with_into(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("merge prime develop into main")
        assert plan.steps[0].project == "prime"

    def test_parse_merge_with_in(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("merge develop to main in edge")
        assert plan.steps[0].project == "edge"

    def test_merge_unknown_project_raises(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        with pytest.raises(ValueError, match="Unknown project"):
            parser.parse("merge unknown develop to main")


class TestParseTest:
    """Tests for test task parsing."""

    def test_parse_test_single_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("run tests in core")
        assert len(plan.steps) == 1
        assert plan.steps[0].project == "core"
        assert "test" in plan.steps[0].action.lower()

    def test_parse_test_all_projects(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("run tests across all projects")
        assert len(plan.steps) == 3
        projects = {step.project for step in plan.steps}
        assert projects == {"core", "prime", "edge"}

    def test_parse_test_without_run(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("tests in prime")
        assert len(plan.steps) == 1
        assert plan.steps[0].project == "prime"


class TestParseCleanBranches:
    """Tests for branch cleanup parsing."""

    def test_parse_clean_single_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("clean stale branches in core")
        assert len(plan.steps) == 1
        assert plan.steps[0].project == "core"
        assert "clean" in plan.steps[0].action.lower()

    def test_parse_clean_multiple_projects(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("clean branches in prime and edge")
        assert len(plan.steps) == 2
        projects = {step.project for step in plan.steps}
        assert projects == {"prime", "edge"}

    def test_clean_scope_is_destructive(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("clean stale branches in core")
        assert plan.scope.destructive is True


class TestParseMultiProject:
    """Tests for multi-project tasks."""

    def test_parse_update_dependency(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("update core in prime and edge")
        assert len(plan.steps) == 2
        projects = {step.project for step in plan.steps}
        assert projects == {"prime", "edge"}
        for step in plan.steps:
            assert "update core" in step.action.lower()


class TestParseGeneric:
    """Tests for generic fallback parsing."""

    def test_generic_falls_back_to_first_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("do something unusual")
        assert len(plan.steps) == 1
        # Should use first project (alphabetically: core)
        assert plan.steps[0].project in config.projects

    def test_generic_uses_llm_tier(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("complex task requiring AI")
        assert plan.steps[0].model_tier == "cloud-fast"

    def test_generic_requires_approval(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("unknown task")
        assert plan.requires_approval is True


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_config_raises(self, tmp_path: Path) -> None:
        config = OverlordConfig(projects={})
        graph = DependencyGraph(config)
        parser = TaskParser(graph)
        with pytest.raises(ValueError, match="No projects"):
            parser.parse("do something")

    def test_whitespace_handling(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan = parser.parse("  merge core develop to main  ")
        assert plan.steps[0].project == "core"

    def test_case_insensitive_parsing(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        parser = _make_parser(config)
        plan1 = parser.parse("MERGE core develop TO main")
        plan2 = parser.parse("merge core develop to main")
        assert plan1.steps[0].project == plan2.steps[0].project
