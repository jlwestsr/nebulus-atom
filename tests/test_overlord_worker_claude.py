"""Tests for the Claude Code worker module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from nebulus_swarm.overlord.workers.claude import (
    ClaudeWorker,
    ClaudeWorkerConfig,
    ClaudeWorkerResult,
    load_worker_config,
)
from nebulus_swarm.overlord.workers.sdk_factory import LLMResponse


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
        assert cfg.api_key is None
        assert cfg.api_key_env == "ANTHROPIC_API_KEY"

    def test_custom_values(self) -> None:
        cfg = ClaudeWorkerConfig(
            enabled=True,
            binary_path="/usr/local/bin/claude",
            default_model="opus",
            model_overrides={"architecture": "opus"},
            timeout=900,
            api_key="sk-test",
            api_key_env="CUSTOM_KEY",
        )
        assert cfg.enabled is True
        assert cfg.binary_path == "/usr/local/bin/claude"
        assert cfg.default_model == "opus"
        assert cfg.model_overrides == {"architecture": "opus"}
        assert cfg.timeout == 900
        assert cfg.api_key == "sk-test"
        assert cfg.api_key_env == "CUSTOM_KEY"


class TestClaudeWorkerResult:
    """Tests for ClaudeWorkerResult dataclass."""

    def test_defaults(self) -> None:
        result = ClaudeWorkerResult(success=True)
        assert result.success is True
        assert result.output == ""
        assert result.error is None
        assert result.duration == 0.0
        assert result.model_used == ""
        assert result.tokens_input == 0
        assert result.tokens_output == 0
        assert result.tokens_total == 0

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
                "api_key": "sk-test",
                "api_key_env": "MY_KEY",
            }
        }
        cfg = load_worker_config(raw)
        assert cfg is not None
        assert cfg.enabled is True
        assert cfg.binary_path == "/usr/bin/claude"
        assert cfg.default_model == "sonnet"
        assert cfg.model_overrides == {"architecture": "opus", "planning": "opus"}
        assert cfg.timeout == 300
        assert cfg.api_key == "sk-test"
        assert cfg.api_key_env == "MY_KEY"

    def test_uses_defaults_for_missing_keys(self) -> None:
        raw = {"claude": {"enabled": True}}
        cfg = load_worker_config(raw)
        assert cfg is not None
        assert cfg.binary_path == "claude"
        assert cfg.default_model == "sonnet"
        assert cfg.timeout == 600
        assert cfg.api_key is None
        assert cfg.api_key_env == "ANTHROPIC_API_KEY"


# --- API key validation ---


class TestClaudeWorkerInit:
    """Tests for ClaudeWorker initialization and API key discovery."""

    def test_enabled_with_api_key_in_config(self) -> None:
        cfg = ClaudeWorkerConfig(enabled=True, api_key="sk-test")
        worker = ClaudeWorker(cfg)
        assert worker.available is True

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"})
    def test_enabled_with_env_key(self) -> None:
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        assert worker.available is True

    @patch.dict("os.environ", {}, clear=True)
    def test_enabled_no_key(self) -> None:
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        assert worker.available is False

    def test_disabled_skips_key_check(self) -> None:
        cfg = ClaudeWorkerConfig(enabled=False)
        worker = ClaudeWorker(cfg)
        assert worker.available is False

    @patch.dict("os.environ", {}, clear=True)
    def test_execute_when_unavailable(self) -> None:
        cfg = ClaudeWorkerConfig(enabled=True)
        worker = ClaudeWorker(cfg)
        result = worker.execute("test", Path("/tmp"), "feature")
        assert result.success is False
        assert "not available" in result.error


# --- Model selection ---


class TestModelSelection:
    """Tests for _select_model priority chain."""

    def test_explicit_override_wins(self) -> None:
        cfg = ClaudeWorkerConfig(
            enabled=True,
            api_key="sk-test",
            default_model="sonnet",
            model_overrides={"architecture": "opus"},
        )
        worker = ClaudeWorker(cfg)
        assert worker._select_model("architecture", explicit="haiku") == "haiku"

    def test_task_type_override(self) -> None:
        cfg = ClaudeWorkerConfig(
            enabled=True,
            api_key="sk-test",
            default_model="sonnet",
            model_overrides={"architecture": "opus", "planning": "opus"},
        )
        worker = ClaudeWorker(cfg)
        assert worker._select_model("architecture") == "opus"
        assert worker._select_model("planning") == "opus"

    def test_falls_back_to_default(self) -> None:
        cfg = ClaudeWorkerConfig(
            enabled=True,
            api_key="sk-test",
            default_model="sonnet",
            model_overrides={"architecture": "opus"},
        )
        worker = ClaudeWorker(cfg)
        assert worker._select_model("feature") == "sonnet"
        assert worker._select_model("review") == "sonnet"


# --- SDK execution ---


class TestClaudeWorkerExecute:
    """Tests for execute() SDK-based execution."""

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_anthropic")
    def test_successful_execution(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.return_value = LLMResponse(
            content="Task completed successfully",
            tokens_input=500,
            tokens_output=200,
            model="claude-sonnet-4-20250514",
            provider="anthropic",
        )
        cfg = ClaudeWorkerConfig(
            enabled=True, api_key="sk-test", default_model="sonnet"
        )
        worker = ClaudeWorker(cfg)
        result = worker.execute("fix the bug", tmp_path, "fix")

        assert result.success is True
        assert result.output == "Task completed successfully"
        assert result.model_used == "claude-sonnet-4-20250514"
        assert result.duration > 0
        assert result.tokens_input == 500
        assert result.tokens_output == 200
        assert result.tokens_total == 700

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_anthropic")
    def test_api_error(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.side_effect = RuntimeError("Anthropic API error: rate limit")
        cfg = ClaudeWorkerConfig(enabled=True, api_key="sk-test")
        worker = ClaudeWorker(cfg)
        result = worker.execute("bad task", tmp_path, "feature")

        assert result.success is False
        assert "Anthropic API error" in result.error

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_anthropic")
    def test_value_error(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.side_effect = ValueError("No API key")
        cfg = ClaudeWorkerConfig(enabled=True, api_key="sk-test")
        worker = ClaudeWorker(cfg)
        result = worker.execute("task", tmp_path, "feature")

        assert result.success is False
        assert "No API key" in result.error

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_anthropic")
    def test_passes_model_and_key(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.return_value = LLMResponse(
            content="ok",
            tokens_input=10,
            tokens_output=5,
            model="claude-sonnet-4-20250514",
            provider="anthropic",
        )
        cfg = ClaudeWorkerConfig(
            enabled=True, api_key="sk-my-key", default_model="sonnet"
        )
        worker = ClaudeWorker(cfg)
        worker.execute("task", tmp_path, "feature")

        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args[1]
        assert call_kwargs["model"] == "sonnet"
        assert call_kwargs["api_key"] == "sk-my-key"

    @patch("nebulus_swarm.overlord.workers.sdk_factory.call_anthropic")
    def test_worker_type_set(self, mock_call: MagicMock, tmp_path: Path) -> None:
        mock_call.return_value = LLMResponse(
            content="ok",
            tokens_input=1,
            tokens_output=1,
            model="m",
            provider="anthropic",
        )
        cfg = ClaudeWorkerConfig(enabled=True, api_key="sk-test")
        worker = ClaudeWorker(cfg)
        result = worker.execute("task", tmp_path)
        assert result.worker_type == "claude"


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
                    "api_key": "sk-test",
                }
            },
        )

        engine = DispatchEngine(
            config,
            AutonomyEngine(config),
            DependencyGraph(config),
            ModelRouter(config),
        )
        # Worker should be initialized (API key provided)
        assert engine.claude_worker is not None
        assert engine.claude_worker.available is True

    @patch.dict("os.environ", {}, clear=True)
    def test_engine_worker_no_key_falls_back(self, tmp_path: Path) -> None:
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
        # Worker should be None since no API key
        assert engine.claude_worker is None
