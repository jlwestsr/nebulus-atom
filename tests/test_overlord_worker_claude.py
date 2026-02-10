"""Tests for the Claude Code worker module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


from nebulus_swarm.overlord.worker_claude import (
    ClaudeWorker,
    ClaudeWorkerConfig,
    ClaudeWorkerResult,
    load_worker_config,
)


# --- Config defaults and parsing ---


class TestClaudeWorkerConfig:
    """Tests for ClaudeWorkerConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = ClaudeWorkerConfig()
        assert cfg.enabled is False
        assert cfg.binary_path == "claude"
        assert cfg.default_model == "sonnet"
        assert cfg.model_overrides == {}
        assert cfg.timeout == 600

    def test_custom_values(self) -> None:
        cfg = ClaudeWorkerConfig(
            enabled=True,
            binary_path="/usr/local/bin/claude",
            default_model="opus",
            model_overrides={"architecture": "opus"},
            timeout=900,
        )
        assert cfg.enabled is True
        assert cfg.binary_path == "/usr/local/bin/claude"
        assert cfg.default_model == "opus"
        assert cfg.model_overrides == {"architecture": "opus"}
        assert cfg.timeout == 900


class TestClaudeWorkerResult:
    """Tests for ClaudeWorkerResult dataclass."""

    def test_defaults(self) -> None:
        result = ClaudeWorkerResult(success=True)
        assert result.success is True
        assert result.output == ""
        assert result.error is None
        assert result.duration == 0.0
        assert result.model_used == ""

    def test_full_result(self) -> None:
        result = ClaudeWorkerResult(
            success=False,
            output="partial output",
            error="something broke",
            duration=1.5,
            model_used="sonnet",
        )
        assert result.success is False
        assert result.error == "something broke"


class TestLoadWorkerConfig:
    """Tests for load_worker_config parser."""

    def test_empty_dict(self) -> None:
        assert load_worker_config({}) is None

    def test_no_claude_key(self) -> None:
        assert load_worker_config({"other": {}}) is None

    def test_claude_key_not_dict(self) -> None:
        assert load_worker_config({"claude": "invalid"}) is None

    def test_parses_full_config(self) -> None:
        raw = {
            "claude": {
                "enabled": True,
                "binary_path": "/usr/bin/claude",
                "default_model": "sonnet",
                "model_overrides": {"architecture": "opus", "planning": "opus"},
                "timeout": 300,
            }
        }
        cfg = load_worker_config(raw)
        assert cfg is not None
        assert cfg.enabled is True
        assert cfg.binary_path == "/usr/bin/claude"
        assert cfg.default_model == "sonnet"
        assert cfg.model_overrides == {"architecture": "opus", "planning": "opus"}
        assert cfg.timeout == 300

    def test_uses_defaults_for_missing_keys(self) -> None:
        raw = {"claude": {"enabled": True}}
        cfg = load_worker_config(raw)
        assert cfg is not None
        assert cfg.binary_path == "claude"
        assert cfg.default_model == "sonnet"
        assert cfg.timeout == 600


# --- Binary validation ---


class TestClaudeWorkerInit:
    """Tests for ClaudeWorker initialization and binary discovery."""

    @patch("shutil.which", return_value="/usr/local/bin/claude")
    def test_enabled_with_binary_found(self, mock_which: MagicMock) -> None:
        cfg = ClaudeWorkerConfig(enabled=True, binary_path="claude")
        worker = ClaudeWorker(cfg)
        assert worker.available is True
        mock_which.assert_called_once_with("claude")

    @patch("shutil.which", return_value=None)
    def test_enabled_binary_not_found(self, mock_which: MagicMock) -> None:
        cfg = ClaudeWorkerConfig(enabled=True, binary_path="claude")
        worker = ClaudeWorker(cfg)
        assert worker.available is False

    def test_disabled_skips_binary_check(self) -> None:
        cfg = ClaudeWorkerConfig(enabled=False)
        worker = ClaudeWorker(cfg)
        assert worker.available is False

    @patch("shutil.which", return_value=None)
    def test_execute_when_unavailable(self, _mock: MagicMock) -> None:
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        result = worker.execute("test", Path("/tmp"), "feature")
        assert result.success is False
        assert "not available" in result.error


# --- Model selection ---


class TestModelSelection:
    """Tests for _select_model priority chain."""

    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_explicit_override_wins(self, _mock: MagicMock) -> None:
        cfg = ClaudeWorkerConfig(
            enabled=True,
            default_model="sonnet",
            model_overrides={"architecture": "opus"},
        )
        worker = ClaudeWorker(cfg)
        assert worker._select_model("architecture", explicit="haiku") == "haiku"

    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_task_type_override(self, _mock: MagicMock) -> None:
        cfg = ClaudeWorkerConfig(
            enabled=True,
            default_model="sonnet",
            model_overrides={"architecture": "opus", "planning": "opus"},
        )
        worker = ClaudeWorker(cfg)
        assert worker._select_model("architecture") == "opus"
        assert worker._select_model("planning") == "opus"

    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_falls_back_to_default(self, _mock: MagicMock) -> None:
        cfg = ClaudeWorkerConfig(
            enabled=True,
            default_model="sonnet",
            model_overrides={"architecture": "opus"},
        )
        worker = ClaudeWorker(cfg)
        assert worker._select_model("feature") == "sonnet"
        assert worker._select_model("review") == "sonnet"


# --- Subprocess execution ---


class TestClaudeWorkerExecute:
    """Tests for execute() subprocess handling."""

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_successful_execution(
        self, mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Task completed successfully",
            stderr="",
        )
        cfg = ClaudeWorkerConfig(enabled=True, default_model="sonnet")
        worker = ClaudeWorker(cfg)
        result = worker.execute("fix the bug", tmp_path, "fix")

        assert result.success is True
        assert result.output == "Task completed successfully"
        assert result.model_used == "sonnet"
        assert result.duration > 0

        # Verify subprocess was called correctly
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "/usr/bin/claude"
        assert "-p" in cmd
        assert "fix the bug" in cmd
        assert "--model" in cmd
        assert "sonnet" in cmd
        assert "--print" in cmd

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_failed_execution(
        self, mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="partial output",
            stderr="Error: something went wrong",
        )
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        result = worker.execute("bad task", tmp_path, "feature")

        assert result.success is False
        assert result.error == "Error: something went wrong"
        assert result.output == "partial output"

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=10),
    )
    def test_timeout(
        self, _mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        cfg = ClaudeWorkerConfig(enabled=True, timeout=10)
        worker = ClaudeWorker(cfg)
        result = worker.execute("slow task", tmp_path, "feature")

        assert result.success is False
        assert "Timed out" in result.error

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run", side_effect=OSError("No such file"))
    def test_os_error(
        self, _mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        result = worker.execute("task", tmp_path, "feature")

        assert result.success is False
        assert "Failed to launch" in result.error

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_uses_project_path_as_cwd(
        self, mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        worker.execute("task", tmp_path, "feature")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == str(tmp_path)

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_nonexistent_path_uses_none_cwd(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        worker.execute("task", Path("/nonexistent/path"), "feature")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] is None

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_exit_code_nonzero_no_stderr(
        self, mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="")
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        result = worker.execute("task", tmp_path, "feature")

        assert result.success is False
        assert "Exit code 2" in result.error


# --- Dispatch integration ---


class TestDispatchIntegration:
    """Tests for ClaudeWorker integration with DispatchEngine."""

    def test_engine_no_worker_by_default(self, tmp_path: Path) -> None:
        from nebulus_swarm.overlord.autonomy import AutonomyEngine
        from nebulus_swarm.overlord.dispatch import DispatchEngine
        from nebulus_swarm.overlord.graph import DependencyGraph
        from nebulus_swarm.overlord.model_router import ModelRouter
        from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig

        d = tmp_path / "core"
        d.mkdir()
        config = OverlordConfig(
            projects={
                "core": ProjectConfig(name="core", path=d, remote="t/c", role="tooling")
            },
            autonomy_global="proactive",
            models={
                "local": {
                    "endpoint": "http://localhost:5000",
                    "model": "test",
                    "tier": "local",
                }
            },
        )
        engine = DispatchEngine(
            config, AutonomyEngine(config), DependencyGraph(config), ModelRouter(config)
        )
        assert engine.claude_worker is None

    def test_engine_with_worker_enabled(self, tmp_path: Path) -> None:
        from nebulus_swarm.overlord.autonomy import AutonomyEngine
        from nebulus_swarm.overlord.dispatch import DispatchEngine
        from nebulus_swarm.overlord.graph import DependencyGraph
        from nebulus_swarm.overlord.model_router import ModelRouter
        from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig

        d = tmp_path / "core"
        d.mkdir()
        config = OverlordConfig(
            projects={
                "core": ProjectConfig(name="core", path=d, remote="t/c", role="tooling")
            },
            autonomy_global="proactive",
            models={
                "local": {
                    "endpoint": "http://localhost:5000",
                    "model": "test",
                    "tier": "local",
                }
            },
            workers={
                "claude": {
                    "enabled": True,
                    "binary_path": "claude",
                    "default_model": "sonnet",
                }
            },
        )

        with patch("shutil.which", return_value="/usr/bin/claude"):
            engine = DispatchEngine(
                config,
                AutonomyEngine(config),
                DependencyGraph(config),
                ModelRouter(config),
            )
        # Worker should be initialized (binary "found" by mock)
        assert engine.claude_worker is not None
        assert engine.claude_worker.available is True

    def test_engine_worker_binary_missing_falls_back(self, tmp_path: Path) -> None:
        from nebulus_swarm.overlord.autonomy import AutonomyEngine
        from nebulus_swarm.overlord.dispatch import DispatchEngine
        from nebulus_swarm.overlord.graph import DependencyGraph
        from nebulus_swarm.overlord.model_router import ModelRouter
        from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig

        d = tmp_path / "core"
        d.mkdir()
        config = OverlordConfig(
            projects={
                "core": ProjectConfig(name="core", path=d, remote="t/c", role="tooling")
            },
            autonomy_global="proactive",
            models={
                "local": {
                    "endpoint": "http://localhost:5000",
                    "model": "test",
                    "tier": "local",
                }
            },
            workers={
                "claude": {
                    "enabled": True,
                    "binary_path": "nonexistent-binary",
                }
            },
        )

        engine = DispatchEngine(
            config, AutonomyEngine(config), DependencyGraph(config), ModelRouter(config)
        )
        # Worker should be None since binary not found
        assert engine.claude_worker is None
