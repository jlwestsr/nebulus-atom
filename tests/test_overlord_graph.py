"""Tests for the Overlord dependency graph traversal."""

from __future__ import annotations

from pathlib import Path

from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig

import pytest


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Build a realistic config: core -> prime, edge, atom, forge; gantry -> core+prime."""
    projects = {}
    for name in (
        "nebulus-core",
        "nebulus-prime",
        "nebulus-edge",
        "nebulus-atom",
        "nebulus-forge",
        "nebulus-gantry",
    ):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name,
            path=d,
            remote=f"jlwestsr/{name}",
            role="tooling",
        )

    projects["nebulus-prime"].depends_on = ["nebulus-core"]
    projects["nebulus-edge"].depends_on = ["nebulus-core"]
    projects["nebulus-atom"].depends_on = ["nebulus-core"]
    projects["nebulus-forge"].depends_on = ["nebulus-core"]
    projects["nebulus-gantry"].depends_on = ["nebulus-core", "nebulus-prime"]

    return OverlordConfig(projects=projects)


class TestGetUpstream:
    """Tests for DependencyGraph.get_upstream."""

    def test_core_has_no_upstream(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        assert graph.get_upstream("nebulus-core") == []

    def test_prime_depends_on_core(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        assert graph.get_upstream("nebulus-prime") == ["nebulus-core"]

    def test_gantry_depends_on_core_and_prime(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        upstream = graph.get_upstream("nebulus-gantry")
        assert "nebulus-core" in upstream
        assert "nebulus-prime" in upstream

    def test_unknown_project_raises(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        with pytest.raises(KeyError, match="Unknown project"):
            graph.get_upstream("nonexistent")


class TestGetDownstream:
    """Tests for DependencyGraph.get_downstream."""

    def test_core_has_all_dependents(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        downstream = graph.get_downstream("nebulus-core")
        assert "nebulus-prime" in downstream
        assert "nebulus-edge" in downstream
        assert "nebulus-atom" in downstream
        assert "nebulus-forge" in downstream
        assert "nebulus-gantry" in downstream

    def test_prime_has_gantry_downstream(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        downstream = graph.get_downstream("nebulus-prime")
        assert "nebulus-gantry" in downstream

    def test_leaf_has_no_downstream(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        assert graph.get_downstream("nebulus-edge") == []


class TestGetAffectedBy:
    """Tests for DependencyGraph.get_affected_by."""

    def test_change_core_affects_everything(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        affected = graph.get_affected_by("nebulus-core")
        assert affected[0] == "nebulus-core"
        assert "nebulus-prime" in affected
        assert "nebulus-edge" in affected
        assert "nebulus-gantry" in affected

    def test_change_leaf_only_affects_itself(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        affected = graph.get_affected_by("nebulus-edge")
        assert affected == ["nebulus-edge"]

    def test_change_prime_affects_prime_and_gantry(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        affected = graph.get_affected_by("nebulus-prime")
        assert affected[0] == "nebulus-prime"
        assert "nebulus-gantry" in affected
        assert len(affected) == 2


class TestReleaseOrder:
    """Tests for DependencyGraph.get_release_order."""

    def test_core_comes_first(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        order = graph.get_release_order()
        assert order[0] == "nebulus-core"

    def test_gantry_comes_after_prime(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        order = graph.get_release_order()
        assert order.index("nebulus-prime") < order.index("nebulus-gantry")

    def test_all_projects_present(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        order = graph.get_release_order()
        assert len(order) == 6


class TestSubgraph:
    """Tests for DependencyGraph.get_subgraph."""

    def test_subgraph_filters_edges(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        sub = graph.get_subgraph(["nebulus-core", "nebulus-prime"])
        assert sub["nebulus-core"] == []
        assert sub["nebulus-prime"] == ["nebulus-core"]

    def test_subgraph_excludes_out_of_scope_deps(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        sub = graph.get_subgraph(["nebulus-prime", "nebulus-gantry"])
        # gantry depends on core and prime, but core is not in subset
        assert sub["nebulus-gantry"] == ["nebulus-prime"]

    def test_subgraph_empty_input(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        assert graph.get_subgraph([]) == {}


class TestRenderAscii:
    """Tests for DependencyGraph.render_ascii."""

    def test_render_contains_root_marker(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        ascii_out = graph.render_ascii()
        assert "(root)" in ascii_out

    def test_render_contains_all_projects(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        ascii_out = graph.render_ascii()
        for name in _make_config(tmp_path).projects:
            assert name in ascii_out

    def test_render_shows_dependency_arrows(self, tmp_path: Path) -> None:
        graph = DependencyGraph(_make_config(tmp_path))
        ascii_out = graph.render_ascii()
        assert "<-" in ascii_out
        assert "->" in ascii_out


class TestEmptyConfig:
    """Tests with an empty registry."""

    def test_empty_release_order(self) -> None:
        graph = DependencyGraph(OverlordConfig())
        assert graph.get_release_order() == []

    def test_empty_render_ascii(self) -> None:
        graph = DependencyGraph(OverlordConfig())
        assert graph.render_ascii() == ""
