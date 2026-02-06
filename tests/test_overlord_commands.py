"""Tests for Overlord CLI commands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestAutonomyCommand:
    """Tests for `overlord autonomy`."""

    def test_autonomy_shows_settings(self, tmp_path: Path) -> None:
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
            result = runner.invoke(overlord_app, ["autonomy"])
        assert "Autonomy Settings" in result.output
        assert "(global)" in result.output
        assert "cautious" in result.output

    def test_autonomy_list_approved_empty(self, tmp_path: Path) -> None:
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
            result = runner.invoke(overlord_app, ["autonomy", "--list-approved"])
        assert "No pre-approved actions" in result.output

    def test_autonomy_list_approved_shows_actions(self, tmp_path: Path) -> None:
        # Create config with pre-approved actions
        core_dir = tmp_path / "core"
        core_dir.mkdir()
        config = {
            "projects": {
                "core": {
                    "path": str(core_dir),
                    "remote": "test/core",
                    "role": "shared-library",
                    "branch_model": "develop-main",
                    "depends_on": [],
                }
            },
            "autonomy": {
                "global": "scheduled",
                "overrides": {},
                "pre_approved": {
                    "core": ["run tests", "clean branches"],
                },
            },
        }
        config_file = tmp_path / "overlord.yml"
        config_file.write_text(yaml.dump(config, default_flow_style=False))

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
            result = runner.invoke(overlord_app, ["autonomy", "--list-approved"])
        assert "Pre-Approved Actions" in result.output
        assert "run tests" in result.output
        assert "clean branches" in result.output

    def test_autonomy_set_global_shows_instructions(self, tmp_path: Path) -> None:
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
            result = runner.invoke(overlord_app, ["autonomy", "--global", "proactive"])
        assert "edit" in result.output.lower()
        assert "proactive" in result.output

    def test_autonomy_set_project_shows_instructions(self, tmp_path: Path) -> None:
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
            result = runner.invoke(
                overlord_app,
                ["autonomy", "--project", "nebulus-core", "--level", "proactive"],
            )
        assert "edit" in result.output.lower()
        assert "nebulus-core" in result.output
        assert "proactive" in result.output


class TestDaemonCommand:
    """Tests for `overlord daemon` lifecycle commands."""

    def test_status_when_running(self) -> None:
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon"
        ) as MockDaemon:
            MockDaemon.read_pid.return_value = 12345
            MockDaemon.check_running.return_value = True
            result = runner.invoke(overlord_app, ["daemon", "status"])
        assert "running" in result.output.lower()
        assert "12345" in result.output

    def test_status_when_stopped(self) -> None:
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon"
        ) as MockDaemon:
            MockDaemon.read_pid.return_value = None
            MockDaemon.check_running.return_value = False
            result = runner.invoke(overlord_app, ["daemon", "status"])
        assert "not running" in result.output.lower()

    def test_status_stale_pid_file(self) -> None:
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon"
        ) as MockDaemon:
            MockDaemon.read_pid.return_value = 99999
            MockDaemon.check_running.return_value = False
            result = runner.invoke(overlord_app, ["daemon", "status"])
        assert "stale" in result.output.lower()
        assert "99999" in result.output

    def test_stop_sends_sigterm(self) -> None:
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon"
        ) as MockDaemon:
            MockDaemon.check_running.return_value = True
            MockDaemon.read_pid.return_value = 12345
            MockDaemon.stop_daemon.return_value = True
            result = runner.invoke(overlord_app, ["daemon", "stop"])
        assert "stopped" in result.output.lower()
        MockDaemon.stop_daemon.assert_called_once()

    def test_stop_when_not_running(self) -> None:
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon"
        ) as MockDaemon:
            MockDaemon.check_running.return_value = False
            result = runner.invoke(overlord_app, ["daemon", "stop"])
        assert "not running" in result.output.lower()

    def test_stop_timeout_fails(self) -> None:
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon"
        ) as MockDaemon:
            MockDaemon.check_running.return_value = True
            MockDaemon.read_pid.return_value = 12345
            MockDaemon.stop_daemon.return_value = False
            result = runner.invoke(overlord_app, ["daemon", "stop"])
        assert "failed" in result.output.lower()
        assert result.exit_code == 1

    def test_start_refuses_if_already_running(self) -> None:
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon"
        ) as MockDaemon:
            MockDaemon.check_running.return_value = True
            MockDaemon.read_pid.return_value = 12345
            result = runner.invoke(overlord_app, ["daemon", "start"])
        assert "already running" in result.output.lower()
        assert "12345" in result.output

    def test_restart_stops_then_starts(
        self, temp_git_repo: Path, tmp_path: Path
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

        # Mock OverlordDaemon at the import location
        mock_daemon_cls = MagicMock()
        # First call: check_running for restart's stop phase → True
        # Second call: check_running for start phase → False
        mock_daemon_cls.check_running.side_effect = [True, False]
        mock_daemon_cls.read_pid.return_value = 12345
        mock_daemon_cls.stop_daemon.return_value = True
        # Mock the instance returned by the constructor
        mock_instance = MagicMock()
        mock_daemon_cls.return_value = mock_instance
        # Make asyncio.run with mock work by making run() return immediately
        mock_instance.run = MagicMock(return_value=None)

        with (
            patch(
                "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon",
                mock_daemon_cls,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
        ):
            result = runner.invoke(overlord_app, ["daemon", "restart"])
        # Should have stopped the old daemon
        mock_daemon_cls.stop_daemon.assert_called_once()
        # Should have started a new one
        assert "stopped" in result.output.lower()
        assert "starting" in result.output.lower()

    def test_unknown_daemon_action(self) -> None:
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.OverlordDaemon"
        ) as MockDaemon:
            MockDaemon.check_running.return_value = False
            result = runner.invoke(overlord_app, ["daemon", "bogus"])
        assert "unknown" in result.output.lower()
        assert "bogus" in result.output
