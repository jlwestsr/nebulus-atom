"""Tests for Overlord CLI commands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from nebulus_atom.commands.overlord_commands import overlord_app

runner = CliRunner()


def _make_config_file(tmp_path: Path, projects: dict) -> Path:
    """Helper to write an overlord.yml and return its path."""
    config = {
        "projects": projects,
        "autonomy": {"global": "cautious", "overrides": {}},
    }
    config_file = tmp_path / "overlord.yml"
    config_file.write_text(yaml.dump(config, default_flow_style=False))
    return config_file


class TestStatusCommand:
    """Tests for `overlord status`."""

    def test_status_shows_project_names(
        self,
        temp_git_repo: Path,
        tmp_path: Path,
    ) -> None:
        config_file = _make_config_file(
            tmp_path,
            {
                "my-project": {
                    "path": str(temp_git_repo),
                    "remote": "test/my-project",
                    "role": "tooling",
                    "branch_model": "develop-main",
                    "depends_on": [],
                },
            },
        )
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["status"])
        assert "my-project" in result.output

    def test_status_single_project(
        self,
        temp_git_repo: Path,
        tmp_path: Path,
    ) -> None:
        config_file = _make_config_file(
            tmp_path,
            {
                "proj-a": {
                    "path": str(temp_git_repo),
                    "remote": "test/a",
                    "role": "tooling",
                    "branch_model": "develop-main",
                    "depends_on": [],
                },
            },
        )
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["status", "proj-a"])
        assert "proj-a" in result.output

    def test_status_unknown_project(self, tmp_path: Path) -> None:
        config_file = _make_config_file(
            tmp_path,
            {
                "known": {
                    "path": str(tmp_path),
                    "remote": "test/known",
                    "role": "tooling",
                    "branch_model": "develop-main",
                    "depends_on": [],
                },
            },
        )
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["status", "unknown"])
        assert "Unknown project" in result.output


class TestScanCommand:
    """Tests for `overlord scan`."""

    def test_scan_shows_detail(
        self,
        temp_git_repo: Path,
        tmp_path: Path,
    ) -> None:
        config_file = _make_config_file(
            tmp_path,
            {
                "my-project": {
                    "path": str(temp_git_repo),
                    "remote": "test/my-project",
                    "role": "tooling",
                    "branch_model": "develop-main",
                    "depends_on": [],
                },
            },
        )
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["scan"])
        assert "my-project" in result.output
        assert "Branch:" in result.output


class TestDiscoverCommand:
    """Tests for `overlord discover`."""

    def test_discover_finds_git_repos(self, tmp_path: Path) -> None:
        # Create a fake workspace with a git repo
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        repo = workspace / "test-repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)

        # Ensure config doesn't exist so discover writes it
        fake_config = tmp_path / "overlord.yml"

        with patch(
            "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
            fake_config,
        ):
            result = runner.invoke(
                overlord_app, ["discover", "--workspace", str(workspace)]
            )
        assert "Discovered 1 projects" in result.output
        assert fake_config.exists()

        # Verify valid YAML was written
        content = yaml.safe_load(fake_config.read_text())
        assert "test-repo" in content["projects"]

    def test_discover_prints_to_stdout_when_config_exists(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        repo = workspace / "test-repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)

        # Pre-create config file
        fake_config = tmp_path / "overlord.yml"
        fake_config.write_text("existing: true\n")

        with patch(
            "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
            fake_config,
        ):
            result = runner.invoke(
                overlord_app, ["discover", "--workspace", str(workspace)]
            )
        assert "already exists" in result.output
        # Original config should not be overwritten
        assert "existing: true" in fake_config.read_text()

    def test_discover_invalid_workspace(self, tmp_path: Path) -> None:
        result = runner.invoke(
            overlord_app, ["discover", "--workspace", str(tmp_path / "nope")]
        )
        assert "not found" in result.output


class TestConfigCommand:
    """Tests for `overlord config`."""

    def test_config_shows_tree(
        self,
        temp_git_repo: Path,
        tmp_path: Path,
    ) -> None:
        config_file = _make_config_file(
            tmp_path,
            {
                "my-project": {
                    "path": str(temp_git_repo),
                    "remote": "test/my-project",
                    "role": "tooling",
                    "branch_model": "develop-main",
                    "depends_on": [],
                },
            },
        )
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["config"])
        assert "my-project" in result.output
        assert "cautious" in result.output
        assert "Config is valid" in result.output


def _make_dep_config_file(tmp_path: Path) -> Path:
    """Helper to write a config with dependencies for graph/scope tests."""
    core_dir = tmp_path / "core"
    prime_dir = tmp_path / "prime"
    edge_dir = tmp_path / "edge"
    for d in (core_dir, prime_dir, edge_dir):
        d.mkdir(exist_ok=True)

    return _make_config_file(
        tmp_path,
        {
            "nebulus-core": {
                "path": str(core_dir),
                "remote": "test/core",
                "role": "shared-library",
                "branch_model": "develop-main",
                "depends_on": [],
            },
            "nebulus-prime": {
                "path": str(prime_dir),
                "remote": "test/prime",
                "role": "platform-deployment",
                "branch_model": "develop-main",
                "depends_on": ["nebulus-core"],
            },
            "nebulus-edge": {
                "path": str(edge_dir),
                "remote": "test/edge",
                "role": "platform-deployment",
                "branch_model": "develop-main",
                "depends_on": ["nebulus-core"],
            },
        },
    )


class TestGraphCommand:
    """Tests for `overlord graph`."""

    def test_graph_shows_full_tree(self, tmp_path: Path) -> None:
        config_file = _make_dep_config_file(tmp_path)
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["graph"])
        assert "Dependency Graph" in result.output
        assert "nebulus-core" in result.output

    def test_graph_single_project_impact(self, tmp_path: Path) -> None:
        config_file = _make_dep_config_file(tmp_path)
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["graph", "nebulus-core"])
        assert "Impact Analysis" in result.output
        assert "Upstream" in result.output
        assert "Downstream" in result.output
        assert "nebulus-prime" in result.output

    def test_graph_unknown_project(self, tmp_path: Path) -> None:
        config_file = _make_dep_config_file(tmp_path)
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["graph", "nope"])
        assert "Unknown project" in result.output


class TestMemoryCommand:
    """Tests for `overlord memory`."""

    def test_memory_recent_empty(self, tmp_path: Path) -> None:
        with patch(
            "nebulus_atom.commands.overlord_commands.OverlordMemory",
        ) as MockMem:
            MockMem.return_value.get_recent.return_value = []
            result = runner.invoke(overlord_app, ["memory", "recent"])
        assert "No memories found" in result.output

    def test_memory_search_requires_query(self) -> None:
        result = runner.invoke(overlord_app, ["memory", "search"])
        assert "requires a query" in result.output

    def test_memory_forget_requires_id(self) -> None:
        result = runner.invoke(overlord_app, ["memory", "forget"])
        assert "requires an entry ID" in result.output

    def test_memory_unknown_action(self) -> None:
        result = runner.invoke(overlord_app, ["memory", "bogus"])
        assert "Unknown action" in result.output


class TestScopeCommand:
    """Tests for `overlord scope`."""

    def test_scope_merge(self, tmp_path: Path) -> None:
        config_file = _make_dep_config_file(tmp_path)
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["scope", "merge", "nebulus-core"])
        assert "Blast Radius" in result.output
        assert "nebulus-core" in result.output

    def test_scope_release_shows_downstream(self, tmp_path: Path) -> None:
        config_file = _make_dep_config_file(tmp_path)
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["scope", "release", "nebulus-core"])
        assert "Blast Radius" in result.output
        assert "nebulus-prime" in result.output
        assert "nebulus-edge" in result.output

    def test_scope_unknown_project(self, tmp_path: Path) -> None:
        config_file = _make_dep_config_file(tmp_path)
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["scope", "push", "nope"])
        assert "Unknown project" in result.output

    def test_scope_unknown_action(self, tmp_path: Path) -> None:
        config_file = _make_dep_config_file(tmp_path)
        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["scope", "yolo", "nebulus-core"])
        assert "Unknown action" in result.output
