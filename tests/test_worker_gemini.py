"""Tests for the Gemini CLI worker module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from nebulus_swarm.overlord.workers.gemini import (
    GeminiWorker,
    GeminiWorkerConfig,
    load_gemini_worker_config,
)


# --- Config defaults and parsing ---


class TestGeminiWorkerConfig:
    """Tests for GeminiWorkerConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = GeminiWorkerConfig()
        assert cfg.enabled is False
        assert cfg.binary_path == "gemini"
        assert cfg.default_model == "gemini-2.5-pro"
        assert cfg.model_overrides == {}
        assert cfg.timeout == 600

    def test_custom_values(self) -> None:
        cfg = GeminiWorkerConfig(
            enabled=True,
            binary_path="/usr/local/bin/gemini",
            default_model="gemini-2.0-flash",
            model_overrides={"review": "gemini-2.5-pro"},
            timeout=300,
        )
        assert cfg.enabled is True
        assert cfg.default_model == "gemini-2.0-flash"


class TestLoadGeminiWorkerConfig:
    """Tests for load_gemini_worker_config parser."""

    def test_empty_dict(self) -> None:
        assert load_gemini_worker_config({}) is None

    def test_no_gemini_key(self) -> None:
        assert load_gemini_worker_config({"claude": {}}) is None

    def test_gemini_key_not_dict(self) -> None:
        assert load_gemini_worker_config({"gemini": "invalid"}) is None

    def test_parses_full_config(self) -> None:
        raw = {
            "gemini": {
                "enabled": True,
                "binary_path": "/usr/bin/gemini",
                "default_model": "gemini-2.5-pro",
                "model_overrides": {"architecture": "gemini-2.5-pro"},
                "timeout": 300,
            }
        }
        cfg = load_gemini_worker_config(raw)
        assert cfg is not None
        assert cfg.enabled is True
        assert cfg.binary_path == "/usr/bin/gemini"
        assert cfg.timeout == 300

    def test_uses_defaults_for_missing_keys(self) -> None:
        raw = {"gemini": {"enabled": True}}
        cfg = load_gemini_worker_config(raw)
        assert cfg is not None
        assert cfg.binary_path == "gemini"
        assert cfg.default_model == "gemini-2.5-pro"


# --- Binary validation ---


class TestGeminiWorkerInit:
    """Tests for GeminiWorker initialization and binary discovery."""

    @patch("shutil.which", return_value="/usr/local/bin/gemini")
    def test_enabled_with_binary_found(self, mock_which: MagicMock) -> None:
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        assert worker.available is True
        assert worker.worker_type == "gemini"
        mock_which.assert_called_once_with("gemini")

    @patch("shutil.which", return_value=None)
    def test_enabled_binary_not_found(self, mock_which: MagicMock) -> None:
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        assert worker.available is False

    def test_disabled_skips_binary_check(self) -> None:
        cfg = GeminiWorkerConfig(enabled=False)
        worker = GeminiWorker(cfg)
        assert worker.available is False

    @patch("shutil.which", return_value=None)
    def test_execute_when_unavailable(self, _mock: MagicMock) -> None:
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        result = worker.execute("test", Path("/tmp"), "feature")
        assert result.success is False
        assert "not available" in result.error


# --- Model selection ---


class TestGeminiModelSelection:
    """Tests for model selection in GeminiWorker."""

    @patch("shutil.which", return_value="/usr/bin/gemini")
    def test_explicit_override_wins(self, _mock: MagicMock) -> None:
        cfg = GeminiWorkerConfig(
            enabled=True,
            model_overrides={"architecture": "gemini-2.5-pro"},
        )
        worker = GeminiWorker(cfg)
        assert (
            worker._select_model("architecture", explicit="gemini-2.0-flash")
            == "gemini-2.0-flash"
        )

    @patch("shutil.which", return_value="/usr/bin/gemini")
    def test_task_type_override(self, _mock: MagicMock) -> None:
        cfg = GeminiWorkerConfig(
            enabled=True,
            model_overrides={"architecture": "gemini-2.5-pro"},
        )
        worker = GeminiWorker(cfg)
        assert worker._select_model("architecture") == "gemini-2.5-pro"

    @patch("shutil.which", return_value="/usr/bin/gemini")
    def test_falls_back_to_default(self, _mock: MagicMock) -> None:
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        assert worker._select_model("feature") == "gemini-2.5-pro"


# --- Subprocess execution ---


class TestGeminiWorkerExecute:
    """Tests for execute() subprocess handling."""

    @patch("shutil.which", return_value="/usr/bin/gemini")
    @patch("subprocess.run")
    def test_successful_execution(
        self, mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Task completed",
            stderr="",
        )
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        result = worker.execute("describe the code", tmp_path, "review")

        assert result.success is True
        assert result.output == "Task completed"
        assert result.worker_type == "gemini"
        assert result.duration > 0

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/gemini"
        assert "-p" in cmd
        assert "describe the code" in cmd

    @patch("shutil.which", return_value="/usr/bin/gemini")
    @patch("subprocess.run")
    def test_failed_execution(
        self, mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="partial",
            stderr="Error occurred",
        )
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        result = worker.execute("bad task", tmp_path)

        assert result.success is False
        assert result.error == "Error occurred"

    @patch("shutil.which", return_value="/usr/bin/gemini")
    @patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="gemini", timeout=10),
    )
    def test_timeout(
        self, _mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        cfg = GeminiWorkerConfig(enabled=True, timeout=10)
        worker = GeminiWorker(cfg)
        result = worker.execute("slow task", tmp_path)

        assert result.success is False
        assert "Timed out" in result.error

    @patch("shutil.which", return_value="/usr/bin/gemini")
    @patch("subprocess.run", side_effect=OSError("No such file"))
    def test_os_error(
        self, _mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        result = worker.execute("task", tmp_path)

        assert result.success is False
        assert "Failed to launch" in result.error

    @patch("shutil.which", return_value="/usr/bin/gemini")
    @patch("subprocess.run")
    def test_uses_project_path_as_cwd(
        self, mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        worker.execute("task", tmp_path)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == str(tmp_path)

    @patch("shutil.which", return_value="/usr/bin/gemini")
    @patch("subprocess.run")
    def test_nonexistent_path_uses_none_cwd(
        self, mock_run: MagicMock, _mock_which: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        worker.execute("task", Path("/nonexistent/path"))

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] is None

    @patch("shutil.which", return_value="/usr/bin/gemini")
    @patch("subprocess.run")
    def test_command_includes_model_flag(
        self, mock_run: MagicMock, _mock_which: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        cfg = GeminiWorkerConfig(enabled=True, default_model="gemini-2.5-pro")
        worker = GeminiWorker(cfg)
        worker.execute("task", tmp_path)

        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        assert "gemini-2.5-pro" in cmd
