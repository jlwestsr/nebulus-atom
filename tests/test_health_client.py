"""Tests for the platform health API client."""

import requests
from unittest.mock import MagicMock, patch

from nebulus_swarm.integrations.health_client import (
    HealthClient,
    HealthConfig,
    HealthStatus,
    get_health_client,
    reset_health_client,
)


class TestHealthConfig:
    def test_default_disabled(self):
        config = HealthConfig()
        assert config.enabled is False
        assert config.url is None

    def test_enabled_with_url(self):
        config = HealthConfig(url="http://localhost:8080/health")
        assert config.enabled is True

    def test_from_env_no_vars(self, monkeypatch):
        monkeypatch.delenv("ATOM_HEALTH_URL", raising=False)
        config = HealthConfig.from_env()
        assert config.enabled is False

    def test_from_env_with_vars(self, monkeypatch):
        monkeypatch.setenv("ATOM_HEALTH_URL", "http://edge:8080/health")
        monkeypatch.setenv("ATOM_HEALTH_TIMEOUT", "10")
        config = HealthConfig.from_env()
        assert config.url == "http://edge:8080/health"
        assert config.timeout == 10


class TestHealthStatus:
    def test_normal_state(self):
        status = HealthStatus(
            thermal_level=0,
            vram_percent=50.0,
            cpu_percent=30.0,
            inference_latency_ms=100.0,
        )
        assert status.is_throttled is False
        assert status.is_critical is False
        assert status.vram_pressure is False

    def test_throttled_state(self):
        status = HealthStatus(
            thermal_level=2,
            vram_percent=50.0,
            cpu_percent=30.0,
            inference_latency_ms=100.0,
        )
        assert status.is_throttled is True
        assert status.is_critical is False

    def test_critical_state(self):
        status = HealthStatus(
            thermal_level=3,
            vram_percent=50.0,
            cpu_percent=30.0,
            inference_latency_ms=100.0,
        )
        assert status.is_throttled is True
        assert status.is_critical is True

    def test_vram_pressure(self):
        status = HealthStatus(
            thermal_level=0,
            vram_percent=95.0,
            cpu_percent=30.0,
            inference_latency_ms=100.0,
        )
        assert status.vram_pressure is True


class TestHealthClientDisabled:
    def test_disabled_returns_defaults(self):
        config = HealthConfig(url=None)
        client = HealthClient(config)
        status = client.get_status()
        assert status.available is False
        assert status.thermal_level == 0

    def test_enabled_property(self):
        client = HealthClient(HealthConfig(url=None))
        assert client.enabled is False
        client = HealthClient(HealthConfig(url="http://localhost/health"))
        assert client.enabled is True


class TestHealthClientConnected:
    def test_successful_health_check(self):
        config = HealthConfig(url="http://localhost:8080/health")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "thermal_level": 1,
            "vram_percent": 75.0,
            "cpu_percent": 60.0,
            "inference_latency_ms": 150.0,
        }

        with patch("nebulus_swarm.integrations.health_client.requests.get") as mock_get:
            mock_get.return_value = mock_response
            client = HealthClient(config)
            status = client.get_status()

            assert status.available is True
            assert status.thermal_level == 1
            assert status.vram_percent == 75.0

    def test_connection_error_returns_defaults(self):
        config = HealthConfig(url="http://localhost:8080/health")

        with patch("nebulus_swarm.integrations.health_client.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException(
                "Connection refused"
            )
            client = HealthClient(config)
            status = client.get_status()

            assert status.available is False

    def test_http_error_returns_defaults(self):
        config = HealthConfig(url="http://localhost:8080/health")
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("nebulus_swarm.integrations.health_client.requests.get") as mock_get:
            mock_get.return_value = mock_response
            client = HealthClient(config)
            status = client.get_status()

            assert status.available is False


class TestTimeoutCalculation:
    def test_normal_timeout(self):
        client = HealthClient(HealthConfig())
        status = HealthStatus(
            thermal_level=0, vram_percent=50, cpu_percent=50, inference_latency_ms=100
        )
        assert client.calculate_timeout_multiplier(status) == 1.0

    def test_warm_timeout(self):
        client = HealthClient(HealthConfig())
        status = HealthStatus(
            thermal_level=1, vram_percent=50, cpu_percent=50, inference_latency_ms=100
        )
        assert client.calculate_timeout_multiplier(status) == 1.5

    def test_hot_timeout(self):
        client = HealthClient(HealthConfig())
        status = HealthStatus(
            thermal_level=2, vram_percent=50, cpu_percent=50, inference_latency_ms=100
        )
        assert client.calculate_timeout_multiplier(status) == 2.0

    def test_critical_timeout(self):
        client = HealthClient(HealthConfig())
        status = HealthStatus(
            thermal_level=3, vram_percent=50, cpu_percent=50, inference_latency_ms=100
        )
        assert client.calculate_timeout_multiplier(status) == 3.0


class TestDispatchDecisions:
    def test_should_pause_at_critical(self):
        client = HealthClient(HealthConfig())
        status = HealthStatus(
            thermal_level=3, vram_percent=50, cpu_percent=50, inference_latency_ms=100
        )
        assert client.should_pause_dispatch(status) is True

    def test_no_pause_below_critical(self):
        client = HealthClient(HealthConfig())
        status = HealthStatus(
            thermal_level=2, vram_percent=50, cpu_percent=50, inference_latency_ms=100
        )
        assert client.should_pause_dispatch(status) is False

    def test_should_switch_model_on_vram_pressure(self):
        client = HealthClient(HealthConfig())
        status = HealthStatus(
            thermal_level=0, vram_percent=95, cpu_percent=50, inference_latency_ms=100
        )
        assert client.should_switch_model(status) is True

    def test_no_switch_normal_vram(self):
        client = HealthClient(HealthConfig())
        status = HealthStatus(
            thermal_level=0, vram_percent=70, cpu_percent=50, inference_latency_ms=100
        )
        assert client.should_switch_model(status) is False


class TestClientCache:
    def test_singleton_pattern(self, monkeypatch):
        monkeypatch.delenv("ATOM_HEALTH_URL", raising=False)
        reset_health_client()

        client1 = get_health_client()
        client2 = get_health_client()
        assert client1 is client2

    def test_reset_clears_cache(self, monkeypatch):
        monkeypatch.delenv("ATOM_HEALTH_URL", raising=False)
        reset_health_client()

        client1 = get_health_client()
        reset_health_client()
        client2 = get_health_client()
        assert client1 is not client2
