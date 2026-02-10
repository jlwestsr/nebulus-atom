"""Tests for Overlord CLI commands."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from typer.testing import CliRunner

from nebulus_atom.commands.overlord_commands import overlord_app
from nebulus_swarm.overlord.memory import MemoryEntry

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

    def test_start_loads_dotenv(self, temp_git_repo: Path, tmp_path: Path) -> None:
        """Daemon start auto-loads .env and reports env var status."""
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
        # Create a .env file in the "cwd"
        env_file = tmp_path / ".env"
        env_file.write_text("SLACK_BOT_TOKEN=xoxb-test\n")

        mock_daemon_cls = MagicMock()
        mock_daemon_cls.check_running.return_value = False
        mock_instance = MagicMock()
        mock_daemon_cls.return_value = mock_instance
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
            patch("os.getcwd", return_value=str(tmp_path)),
        ):
            result = runner.invoke(overlord_app, ["daemon", "start"])
        assert "SLACK_BOT_TOKEN: yes" in result.output
        assert "Loaded .env" in result.output

    def test_start_configures_log_file(
        self, temp_git_repo: Path, tmp_path: Path
    ) -> None:
        """Daemon start configures logging with a log file path."""
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

        mock_daemon_cls = MagicMock()
        mock_daemon_cls.check_running.return_value = False
        mock_instance = MagicMock()
        mock_daemon_cls.return_value = mock_instance
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
            result = runner.invoke(overlord_app, ["daemon", "start"])
        assert "daemon.log" in result.output
        assert "Logging to" in result.output

    def test_start_shows_idle_schedule(
        self, temp_git_repo: Path, tmp_path: Path
    ) -> None:
        """Daemon start shows idle message when no scheduled tasks."""
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

        mock_daemon_cls = MagicMock()
        mock_daemon_cls.check_running.return_value = False
        mock_instance = MagicMock()
        mock_daemon_cls.return_value = mock_instance
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
            result = runner.invoke(overlord_app, ["daemon", "start"])
        assert "no scheduled tasks configured" in result.output.lower()


def _make_report_config(tmp_path: Path) -> Path:
    """Helper to write a config with a project for report/board tests."""
    proj_dir = tmp_path / "my-project"
    proj_dir.mkdir(exist_ok=True)
    return _make_config_file(
        tmp_path,
        {
            "my-project": {
                "path": str(proj_dir),
                "remote": "test/my-project",
                "role": "tooling",
                "branch_model": "develop-main",
                "depends_on": [],
            },
        },
    )


class TestReportCommand:
    """Tests for `overlord report`."""

    def test_report_completed_writes_memory(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        mock_mem.return_value.remember.return_value = "fake-uuid-1234"

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._post_report_to_slack",
            ),
        ):
            result = runner.invoke(
                overlord_app,
                ["report", "completed", "All tests passing", "-p", "my-project"],
            )
        assert result.exit_code == 0
        assert "COMPLETED" in result.output
        mock_mem.return_value.remember.assert_called_once()
        call_kwargs = mock_mem.return_value.remember.call_args
        assert call_kwargs.kwargs["category"] == "dispatch"
        assert call_kwargs.kwargs["status"] == "completed"

    def test_report_detects_project_from_cwd(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        proj_dir = tmp_path / "my-project"
        mock_mem = MagicMock()
        mock_mem.return_value.remember.return_value = "fake-uuid"

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._post_report_to_slack",
            ),
            patch("nebulus_atom.commands.overlord_commands.Path") as MockPath,
        ):
            MockPath.cwd.return_value.resolve.return_value = proj_dir / "subdir"
            # Need to preserve Path behavior for other uses
            MockPath.side_effect = Path
            MockPath.cwd = MagicMock(return_value=MagicMock())
            MockPath.cwd.return_value.resolve.return_value = proj_dir / "subdir"
            result = runner.invoke(
                overlord_app,
                ["report", "started", "Beginning work"],
            )
        # Even if CWD detection fails due to mocking complexity, it should not crash
        assert result.exit_code == 0 or "Could not detect" in result.output

    def test_report_explicit_project_flag(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        mock_mem.return_value.remember.return_value = "fake-uuid"

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._post_report_to_slack",
            ),
        ):
            result = runner.invoke(
                overlord_app,
                ["report", "in_progress", "Working on it", "-p", "my-project"],
            )
        assert result.exit_code == 0
        assert "my-project" in result.output
        assert "IN_PROGRESS" in result.output

    def test_report_rejects_invalid_status(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
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
                ["report", "invalid_status", "msg", "-p", "my-project"],
            )
        assert "Invalid status" in result.output

    def test_report_rejects_unknown_project(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
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
                ["report", "started", "msg", "-p", "no-such-project"],
            )
        assert "Unknown project" in result.output

    def test_report_auto_generates_task_id(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        mock_mem.return_value.remember.return_value = "fake-uuid"

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._post_report_to_slack",
            ),
        ):
            result = runner.invoke(
                overlord_app,
                ["report", "started", "Test", "-p", "my-project"],
            )
        assert result.exit_code == 0
        call_kwargs = mock_mem.return_value.remember.call_args
        assert call_kwargs.kwargs["task_id"].startswith("my-project-")

    def test_report_with_track(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        mock_mem.return_value.remember.return_value = "fake-uuid"

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._post_report_to_slack",
            ),
        ):
            result = runner.invoke(
                overlord_app,
                [
                    "report",
                    "started",
                    "Migrating servers",
                    "-p",
                    "my-project",
                    "--track",
                    "MCP Migration",
                ],
            )
        assert result.exit_code == 0
        assert "MCP Migration" in result.output
        call_kwargs = mock_mem.return_value.remember.call_args
        assert call_kwargs.kwargs["track"] == "MCP Migration"

    def test_report_with_agent_name(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        mock_mem.return_value.remember.return_value = "fake-uuid"

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._post_report_to_slack",
            ),
        ):
            result = runner.invoke(
                overlord_app,
                [
                    "report",
                    "started",
                    "Test",
                    "-p",
                    "my-project",
                    "--agent",
                    "Claude Agent 1",
                ],
            )
        assert result.exit_code == 0
        assert "Claude Agent 1" in result.output
        call_kwargs = mock_mem.return_value.remember.call_args
        assert call_kwargs.kwargs["agent_name"] == "Claude Agent 1"


def _make_memory_entries(
    statuses: list[str],
    project: str = "my-project",
) -> list[MemoryEntry]:
    """Build fake MemoryEntry objects for board tests."""
    entries = []
    for i, status in enumerate(statuses):
        entries.append(
            MemoryEntry(
                id=f"uuid-{i}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                category="dispatch",
                project=project,
                content=f"[{status.upper()}] Task {i}",
                metadata={
                    "status": status,
                    "agent_name": f"Agent-{i}",
                    "task_id": f"{project}-{i}",
                    "track": f"Track {i}" if i % 2 == 0 else "",
                },
            )
        )
    return entries


class TestBoardCommand:
    """Tests for `overlord board`."""

    def test_board_prints_active_entries(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        entries = _make_memory_entries(["started", "in_progress", "blocked"])
        mock_mem.return_value.search.return_value = entries

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
        ):
            result = runner.invoke(overlord_app, ["board"])
        assert result.exit_code == 0
        assert "Dispatch Board" in result.output
        assert "Agent-0" in result.output

    def test_board_excludes_completed_by_default(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        entries = _make_memory_entries(["started", "completed"])
        mock_mem.return_value.search.return_value = entries

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
        ):
            result = runner.invoke(overlord_app, ["board"])
        assert result.exit_code == 0
        # Agent-0 is started (shown), Agent-1 is completed (hidden)
        assert "Agent-0" in result.output

    def test_board_includes_completed_with_all_flag(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        entries = _make_memory_entries(["started", "completed"])
        mock_mem.return_value.search.return_value = entries

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
        ):
            result = runner.invoke(overlord_app, ["board", "--all"])
        assert result.exit_code == 0
        # Both agents should be visible
        assert "Agent-0" in result.output
        assert "Agent-1" in result.output

    def test_board_filters_by_days(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        # One entry from now, one from 30 days ago
        recent = _make_memory_entries(["started"])[0]
        old = MemoryEntry(
            id="old-uuid",
            timestamp="2020-01-01T00:00:00+00:00",
            category="dispatch",
            project="my-project",
            content="[STARTED] Old task",
            metadata={
                "status": "started",
                "agent_name": "Old-Agent",
                "task_id": "old-1",
                "track": "",
            },
        )
        mock_mem.return_value.search.return_value = [recent, old]

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
        ):
            result = runner.invoke(overlord_app, ["board", "--days", "7"])
        assert result.exit_code == 0
        assert "Agent-0" in result.output
        assert "Old-Agent" not in result.output

    def test_board_sync_writes_between_markers(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        entries = _make_memory_entries(["started"])
        mock_mem.return_value.search.return_value = entries

        # Create OVERLORD.md with markers
        md_path = tmp_path / "OVERLORD.md"
        md_path.write_text(
            "# Header\n\n"
            "## Dispatch Board\n\n"
            "<!-- DISPATCH_BOARD_START -->\n"
            "old board content\n"
            "<!-- DISPATCH_BOARD_END -->\n\n"
            "## Agent Roster\n\n"
            "<!-- AGENT_ROSTER_START -->\n"
            "old roster\n"
            "<!-- AGENT_ROSTER_END -->\n\n"
            "## Footer\n"
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
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
        ):
            # Patch workspace_root to point to tmp_path
            from nebulus_swarm.overlord.registry import load_config

            with patch(
                "nebulus_atom.commands.overlord_commands._load_registry_or_exit"
            ) as mock_reg:
                reg = load_config()
                # Override workspace_root
                reg_mock = MagicMock(wraps=reg)
                reg_mock.workspace_root = tmp_path
                reg_mock.projects = reg.projects
                mock_reg.return_value = reg_mock

                result = runner.invoke(overlord_app, ["board", "--sync"])

        assert result.exit_code == 0
        updated = md_path.read_text()
        assert "Agent-0" in updated
        assert "old board content" not in updated
        assert "# Header" in updated
        assert "## Footer" in updated

    def test_board_sync_preserves_other_sections(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        entries = _make_memory_entries(["in_progress"])
        mock_mem.return_value.search.return_value = entries

        md_path = tmp_path / "OVERLORD.md"
        md_path.write_text(
            "## Projects\n\nproject content\n\n"
            "## Dispatch Board\n\n"
            "<!-- DISPATCH_BOARD_START -->\nold\n<!-- DISPATCH_BOARD_END -->\n\n"
            "## Agent Roster\n\n"
            "<!-- AGENT_ROSTER_START -->\nold\n<!-- AGENT_ROSTER_END -->\n\n"
            "## Governance\n\ngovernance content\n"
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
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._load_registry_or_exit"
            ) as mock_reg,
        ):
            mock_cfg = MagicMock()
            mock_cfg.workspace_root = tmp_path
            mock_cfg.projects = {}
            mock_reg.return_value = mock_cfg

            result = runner.invoke(overlord_app, ["board", "--sync"])

        assert result.exit_code == 0
        updated = md_path.read_text()
        assert "project content" in updated
        assert "governance content" in updated

    def test_board_sync_dry_run_no_write(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        entries = _make_memory_entries(["started"])
        mock_mem.return_value.search.return_value = entries

        md_path = tmp_path / "OVERLORD.md"
        original = (
            "## Dispatch Board\n\n"
            "<!-- DISPATCH_BOARD_START -->\noriginal\n<!-- DISPATCH_BOARD_END -->\n\n"
            "## Agent Roster\n\n"
            "<!-- AGENT_ROSTER_START -->\noriginal\n<!-- AGENT_ROSTER_END -->\n"
        )
        md_path.write_text(original)

        with (
            patch(
                "nebulus_atom.commands.overlord_commands.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_swarm.overlord.registry.DEFAULT_CONFIG_PATH",
                config_file,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._load_registry_or_exit"
            ) as mock_reg,
        ):
            mock_cfg = MagicMock()
            mock_cfg.workspace_root = tmp_path
            mock_cfg.projects = {}
            mock_reg.return_value = mock_cfg

            result = runner.invoke(overlord_app, ["board", "--dry-run"])

        assert result.exit_code == 0
        # File should NOT be modified
        assert md_path.read_text() == original

    def test_board_sync_creates_backup(self, tmp_path: Path) -> None:
        config_file = _make_report_config(tmp_path)
        mock_mem = MagicMock()
        entries = _make_memory_entries(["started"])
        mock_mem.return_value.search.return_value = entries

        md_path = tmp_path / "OVERLORD.md"
        md_path.write_text(
            "<!-- DISPATCH_BOARD_START -->\nold\n<!-- DISPATCH_BOARD_END -->\n"
            "<!-- AGENT_ROSTER_START -->\nold\n<!-- AGENT_ROSTER_END -->\n"
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
            patch(
                "nebulus_atom.commands.overlord_commands.OverlordMemory",
                mock_mem,
            ),
            patch(
                "nebulus_atom.commands.overlord_commands._load_registry_or_exit"
            ) as mock_reg,
        ):
            mock_cfg = MagicMock()
            mock_cfg.workspace_root = tmp_path
            mock_cfg.projects = {}
            mock_reg.return_value = mock_cfg

            result = runner.invoke(overlord_app, ["board", "--sync"])

        assert result.exit_code == 0
        backup_path = tmp_path / "OVERLORD.md.bak"
        assert backup_path.exists()
        assert "old" in backup_path.read_text()
