"""Tests for the Gemini worker module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from nebulus_swarm.overlord.workers.gemini import (
    GeminiWorker,
    GeminiWorkerConfig,
    load_gemini_worker_config,
)
from nebulus_swarm.overlord.workers.sdk_factory import LLMResponse


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
        assert cfg.api_key is None
        assert cfg.api_key_env == "GOOGLE_API_KEY"

    def test_custom_values(self) -> None:
        cfg = GeminiWorkerConfig(
            enabled=True,
            binary_path="/usr/local/bin/gemini",
            default_model="gemini-2.5-flash",
            model_overrides={"review": "gemini-2.5-pro"},
            timeout=300,
            api_key="goog-key",
            api_key_env="MY_GOOGLE_KEY",
        )
        assert cfg.enabled is True
        assert cfg.default_model == "gemini-2.5-flash"
        assert cfg.api_key == "goog-key"
        assert cfg.api_key_env == "MY_GOOGLE_KEY"


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
                "api_key": "goog-key",
                "api_key_env": "MY_KEY",
            }
        }
        cfg = load_gemini_worker_config(raw)
        assert cfg is not None
        assert cfg.enabled is True
        assert cfg.binary_path == "/usr/bin/gemini"
        assert cfg.timeout == 300
        assert cfg.api_key == "goog-key"
        assert cfg.api_key_env == "MY_KEY"

    def test_uses_defaults_for_missing_keys(self) -> None:
        raw = {"gemini": {"enabled": True}}
        cfg = load_gemini_worker_config(raw)
        assert cfg is not None
        assert cfg.binary_path == "gemini"
        assert cfg.default_model == "gemini-2.5-pro"
        assert cfg.api_key is None
        assert cfg.api_key_env == "GOOGLE_API_KEY"


# --- API key validation ---


class TestGeminiWorkerInit:
    """Tests for GeminiWorker initialization and API key discovery."""

    def test_enabled_with_api_key_in_config(self) -> None:
        cfg = GeminiWorkerConfig(enabled=True, api_key="goog-key")
        worker = GeminiWorker(cfg)
        assert worker.available is True
        assert worker.worker_type == "gemini"

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "env-key"})
    def test_enabled_with_env_key(self) -> None:
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        assert worker.available is True

    @patch.dict("os.environ", {}, clear=True)
    def test_enabled_no_key(self) -> None:
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        assert worker.available is False

    def test_disabled_skips_key_check(self) -> None:
        cfg = GeminiWorkerConfig(enabled=False)
        worker = GeminiWorker(cfg)
        assert worker.available is False

    @patch.dict("os.environ", {}, clear=True)
    def test_execute_when_unavailable(self) -> None:
        cfg = GeminiWorkerConfig(enabled=True)
        worker = GeminiWorker(cfg)
        result = worker.execute("test", Path("/tmp"), "feature")
        assert result.success is False
        assert "not available" in result.error


# --- Model selection ---


class TestGeminiModelSelection:
    """Tests for model selection in GeminiWorker."""

    def test_explicit_override_wins(self) -> None:
        cfg = GeminiWorkerConfig(
            enabled=True,
            api_key="goog-key",
            model_overrides={"architecture": "gemini-2.5-pro"},
        )
        worker = GeminiWorker(cfg)
        assert (
            worker._select_model("architecture", explicit="gemini-2.5-flash")
            == "gemini-2.5-flash"
        )

    def test_task_type_override(self) -> None:
        cfg = GeminiWorkerConfig(
            enabled=True,
            api_key="goog-key",
            model_overrides={"architecture": "gemini-2.5-pro"},
        )
        worker = GeminiWorker(cfg)
        assert worker._select_model("architecture") == "gemini-2.5-pro"

    def test_falls_back_to_default(self) -> None:
        cfg = GeminiWorkerConfig(enabled=True, api_key="goog-key")
        worker = GeminiWorker(cfg)
        assert worker._select_model("feature") == "gemini-2.5-pro"


# --- SDK execution ---


class TestGeminiWorkerExecute:
    """Tests for execute() SDK-based execution."""

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_google")
    def test_successful_execution(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.return_value = LLMResponse(
            content="Task completed",
            tokens_input=300,
            tokens_output=150,
            model="gemini-2.5-pro",
            provider="google",
        )
        cfg = GeminiWorkerConfig(enabled=True, api_key="goog-key")
        worker = GeminiWorker(cfg)
        result = worker.execute("describe the code", tmp_path, "review")

        assert result.success is True
        assert result.output == "Task completed"
        assert result.worker_type == "gemini"
        assert result.duration > 0
        assert result.tokens_input == 300
        assert result.tokens_output == 150
        assert result.tokens_total == 450

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_google")
    def test_api_error(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.side_effect = RuntimeError("Google API error: quota exceeded")
        cfg = GeminiWorkerConfig(enabled=True, api_key="goog-key")
        worker = GeminiWorker(cfg)
        result = worker.execute("bad task", tmp_path)

        assert result.success is False
        assert "Google API error" in result.error

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_google")
    def test_value_error(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.side_effect = ValueError("No API key")
        cfg = GeminiWorkerConfig(enabled=True, api_key="goog-key")
        worker = GeminiWorker(cfg)
        result = worker.execute("task", tmp_path)

        assert result.success is False
        assert "No API key" in result.error

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_google")
    def test_passes_model_and_key(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.return_value = LLMResponse(
            content="ok",
            tokens_input=10,
            tokens_output=5,
            model="gemini-2.5-pro",
            provider="google",
        )
        cfg = GeminiWorkerConfig(
            enabled=True, api_key="goog-key", default_model="gemini-2.5-pro"
        )
        worker = GeminiWorker(cfg)
        worker.execute("task", tmp_path)

        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args[1]
        assert call_kwargs["model"] == "gemini-2.5-pro"
        assert call_kwargs["api_key"] == "goog-key"

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_google")
    def test_worker_type_set(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.return_value = LLMResponse(
            content="ok",
            tokens_input=1,
            tokens_output=1,
            model="m",
            provider="google",
        )
        cfg = GeminiWorkerConfig(enabled=True, api_key="goog-key")
        worker = GeminiWorker(cfg)
        result = worker.execute("task", tmp_path)
        assert result.worker_type == "gemini"
