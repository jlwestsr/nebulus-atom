"""Tests for the Local/TabbyAPI HTTP worker module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from nebulus_swarm.overlord.workers.local import (
    LocalWorker,
    LocalWorkerConfig,
    load_local_worker_config,
)


# --- Config defaults and parsing ---


class TestLocalWorkerConfig:
    """Tests for LocalWorkerConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = LocalWorkerConfig()
        assert cfg.enabled is False
        assert cfg.default_model == "default"
        assert cfg.timeout == 600
        assert cfg.endpoint == "http://localhost:5000/v1"
        assert cfg.api_key is None

    def test_custom_values(self) -> None:
        cfg = LocalWorkerConfig(
            enabled=True,
            endpoint="http://gpu-box:8080/v1",
            api_key="sk-test",
            default_model="llama-3.1-8b",
            timeout=120,
        )
        assert cfg.enabled is True
        assert cfg.endpoint == "http://gpu-box:8080/v1"
        assert cfg.api_key == "sk-test"


class TestLoadLocalWorkerConfig:
    """Tests for load_local_worker_config parser."""

    def test_empty_dict(self) -> None:
        assert load_local_worker_config({}) is None

    def test_no_local_key(self) -> None:
        assert load_local_worker_config({"claude": {}}) is None

    def test_local_key_not_dict(self) -> None:
        assert load_local_worker_config({"local": "invalid"}) is None

    def test_parses_full_config(self) -> None:
        raw = {
            "local": {
                "enabled": True,
                "endpoint": "http://localhost:8080/v1",
                "api_key": "test-key",
                "default_model": "llama-3.1-8b",
                "model_overrides": {"review": "llama-3.1-70b"},
                "timeout": 120,
            }
        }
        cfg = load_local_worker_config(raw)
        assert cfg is not None
        assert cfg.enabled is True
        assert cfg.endpoint == "http://localhost:8080/v1"
        assert cfg.api_key == "test-key"
        assert cfg.default_model == "llama-3.1-8b"
        assert cfg.timeout == 120

    def test_uses_defaults_for_missing_keys(self) -> None:
        raw = {"local": {"enabled": True}}
        cfg = load_local_worker_config(raw)
        assert cfg is not None
        assert cfg.endpoint == "http://localhost:5000/v1"
        assert cfg.api_key is None
        assert cfg.default_model == "default"


# --- Health check / init ---


class TestLocalWorkerInit:
    """Tests for LocalWorker initialization and health check."""

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=True,
    )
    def test_enabled_with_healthy_endpoint(self, _mock: MagicMock) -> None:
        cfg = LocalWorkerConfig(enabled=True, endpoint="http://localhost:5000/v1")
        worker = LocalWorker(cfg)
        assert worker.available is True
        assert worker.worker_type == "local"

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=False,
    )
    def test_enabled_unhealthy_endpoint(self, _mock: MagicMock) -> None:
        cfg = LocalWorkerConfig(enabled=True)
        worker = LocalWorker(cfg)
        assert worker.available is False

    def test_disabled_skips_health_check(self) -> None:
        cfg = LocalWorkerConfig(enabled=False)
        worker = LocalWorker(cfg)
        assert worker.available is False

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=False,
    )
    def test_execute_when_unavailable(self, _mock: MagicMock) -> None:
        cfg = LocalWorkerConfig(enabled=True)
        worker = LocalWorker(cfg)
        result = worker.execute("test", Path("/tmp"))
        assert result.success is False
        assert "not available" in result.error


# --- HTTP execution ---


class TestLocalWorkerExecute:
    """Tests for execute() HTTP handling."""

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=True,
    )
    @patch("httpx.post")
    def test_successful_execution(
        self, mock_post: MagicMock, _mock_health: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Done!"}}]
        }
        mock_post.return_value = mock_response

        cfg = LocalWorkerConfig(enabled=True, default_model="llama")
        worker = LocalWorker(cfg)
        result = worker.execute("fix the bug", tmp_path, "fix")

        assert result.success is True
        assert result.output == "Done!"
        assert result.worker_type == "local"
        assert result.model_used == "llama"

        # Verify POST payload
        call_kwargs = mock_post.call_args
        assert "chat/completions" in call_kwargs[0][0]
        payload = call_kwargs[1]["json"]
        assert payload["model"] == "llama"
        assert len(payload["messages"]) == 2

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=True,
    )
    @patch("httpx.post")
    def test_http_error_status(
        self, mock_post: MagicMock, _mock_health: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        cfg = LocalWorkerConfig(enabled=True)
        worker = LocalWorker(cfg)
        result = worker.execute("task", tmp_path)

        assert result.success is False
        assert "HTTP 500" in result.error

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=True,
    )
    @patch("httpx.post")
    def test_timeout(
        self, mock_post: MagicMock, _mock_health: MagicMock, tmp_path: Path
    ) -> None:
        import httpx

        mock_post.side_effect = httpx.TimeoutException("timeout")

        cfg = LocalWorkerConfig(enabled=True, timeout=10)
        worker = LocalWorker(cfg)
        result = worker.execute("slow task", tmp_path)

        assert result.success is False
        assert "Timed out" in result.error

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=True,
    )
    @patch("httpx.post")
    def test_http_connection_error(
        self, mock_post: MagicMock, _mock_health: MagicMock, tmp_path: Path
    ) -> None:
        import httpx

        mock_post.side_effect = httpx.ConnectError("connection refused")

        cfg = LocalWorkerConfig(enabled=True)
        worker = LocalWorker(cfg)
        result = worker.execute("task", tmp_path)

        assert result.success is False
        assert "HTTP error" in result.error

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=True,
    )
    @patch("httpx.post")
    def test_includes_api_key(
        self, mock_post: MagicMock, _mock_health: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_post.return_value = mock_response

        cfg = LocalWorkerConfig(enabled=True, api_key="sk-test")
        worker = LocalWorker(cfg)
        worker.execute("task", tmp_path)

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test"

    @patch(
        "nebulus_swarm.overlord.workers.local.LocalWorker._check_health",
        return_value=True,
    )
    @patch("httpx.post")
    def test_no_api_key_no_auth_header(
        self, mock_post: MagicMock, _mock_health: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_post.return_value = mock_response

        cfg = LocalWorkerConfig(enabled=True)
        worker = LocalWorker(cfg)
        worker.execute("task", tmp_path)

        call_kwargs = mock_post.call_args[1]
        assert "Authorization" not in call_kwargs["headers"]


# --- Health check ---


class TestLocalWorkerHealthCheck:
    """Tests for _check_health."""

    @patch("httpx.get")
    def test_healthy_endpoint(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(status_code=200)
        cfg = LocalWorkerConfig(enabled=True)
        worker = LocalWorker(cfg)
        assert worker.available is True

    @patch("httpx.get")
    def test_unhealthy_endpoint(self, mock_get: MagicMock) -> None:
        mock_get.return_value = MagicMock(status_code=503)
        cfg = LocalWorkerConfig(enabled=True)
        worker = LocalWorker(cfg)
        assert worker.available is False

    @patch("httpx.get")
    def test_unreachable_endpoint(self, mock_get: MagicMock) -> None:
        import httpx

        mock_get.side_effect = httpx.ConnectError("refused")
        cfg = LocalWorkerConfig(enabled=True)
        worker = LocalWorker(cfg)
        assert worker.available is False
