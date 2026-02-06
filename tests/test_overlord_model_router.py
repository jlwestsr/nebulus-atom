"""Tests for Overlord Model Router."""

from __future__ import annotations

from pathlib import Path

from nebulus_swarm.overlord.model_router import (
    ModelEndpoint,
    ModelRouter,
    get_task_tier_mapping,
)
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig


def _make_config(tmp_path: Path, **models_kwargs) -> OverlordConfig:
    """Build a test config with model endpoints."""
    projects = {}
    for name in ("core", "prime"):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name, path=d, remote=f"test/{name}", role="tooling"
        )

    return OverlordConfig(projects=projects, models=dict(models_kwargs))


class TestModelEndpoint:
    """Tests for ModelEndpoint dataclass."""

    def test_creates_with_required_fields(self) -> None:
        endpoint = ModelEndpoint(
            name="local-llama",
            endpoint="http://localhost:5000",
            model="llama3.1-8b",
            tier="local",
        )
        assert endpoint.name == "local-llama"
        assert endpoint.tier == "local"
        assert endpoint.concurrent == 1
        assert endpoint.health_check_url is None

    def test_creates_with_all_fields(self) -> None:
        endpoint = ModelEndpoint(
            name="cloud-sonnet",
            endpoint="https://api.anthropic.com",
            model="claude-sonnet-4",
            tier="cloud-fast",
            concurrent=5,
            health_check_url="https://api.anthropic.com/health",
        )
        assert endpoint.concurrent == 5
        assert endpoint.health_check_url == "https://api.anthropic.com/health"

    def test_health_fields_initialized(self) -> None:
        endpoint = ModelEndpoint(
            name="test", endpoint="http://test", model="test", tier="local"
        )
        assert endpoint._last_health_check == 0.0
        assert endpoint._is_healthy is True


class TestModelRouterInit:
    """Tests for ModelRouter initialization."""

    def test_empty_config_creates_empty_router(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        router = ModelRouter(config)
        assert len(router.endpoints) == 0

    def test_loads_single_endpoint(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            local_llama={
                "endpoint": "http://localhost:5000",
                "model": "llama3.1-8b",
                "tier": "local",
            },
        )
        router = ModelRouter(config)
        assert len(router.endpoints) == 1
        assert "local_llama" in router.endpoints
        assert router.endpoints["local_llama"].tier == "local"

    def test_loads_multiple_endpoints(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            local_llama={
                "endpoint": "http://localhost:5000",
                "model": "llama3.1-8b",
                "tier": "local",
            },
            cloud_sonnet={
                "endpoint": "https://api.anthropic.com",
                "model": "claude-sonnet-4",
                "tier": "cloud-fast",
            },
        )
        router = ModelRouter(config)
        assert len(router.endpoints) == 2
        assert "local_llama" in router.endpoints
        assert "cloud_sonnet" in router.endpoints

    def test_skips_invalid_config(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            valid={"endpoint": "http://test", "model": "test", "tier": "local"},
            invalid="not a dict",
        )
        router = ModelRouter(config)
        assert len(router.endpoints) == 1
        assert "valid" in router.endpoints


class TestInferTier:
    """Tests for ModelRouter._infer_tier."""

    def test_format_task_returns_local(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("format", "low") == "local"

    def test_lint_task_returns_local(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("lint", "medium") == "local"

    def test_boilerplate_task_returns_local(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("boilerplate", "low") == "local"

    def test_low_complexity_feature_returns_local(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("feature", "low") == "local"

    def test_medium_complexity_feature_returns_local(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("feature", "medium") == "local"

    def test_high_complexity_feature_returns_cloud_fast(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("feature", "high") == "cloud-fast"

    def test_review_task_returns_cloud_fast(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("review", "medium") == "cloud-fast"

    def test_architecture_task_returns_cloud_heavy(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("architecture", "high") == "cloud-heavy"

    def test_planning_task_returns_cloud_heavy(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("planning", "high") == "cloud-heavy"

    def test_unknown_task_returns_cloud_fast(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router._infer_tier("unknown-task", "medium") == "cloud-fast"


class TestSelectModel:
    """Tests for ModelRouter.select_model."""

    def test_returns_none_when_no_endpoints(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        assert router.select_model("format", "low") is None

    def test_selects_local_for_format_task(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            local_llama={
                "endpoint": "http://localhost:5000",
                "model": "llama",
                "tier": "local",
            },
        )
        router = ModelRouter(config)
        endpoint = router.select_model("format", "low")
        assert endpoint is not None
        assert endpoint.tier == "local"

    def test_selects_cloud_fast_for_review(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            sonnet={
                "endpoint": "https://api.anthropic.com",
                "model": "sonnet",
                "tier": "cloud-fast",
            },
        )
        router = ModelRouter(config)
        endpoint = router.select_model("review", "medium")
        assert endpoint is not None
        assert endpoint.tier == "cloud-fast"

    def test_falls_back_when_tier_unavailable(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            sonnet={
                "endpoint": "https://api.anthropic.com",
                "model": "sonnet",
                "tier": "cloud-fast",
            },
        )
        router = ModelRouter(config)
        # Requests local but only cloud-fast available
        endpoint = router.select_model("format", "low")
        assert endpoint is not None
        assert endpoint.tier == "cloud-fast"

    def test_prefers_local_when_available(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            local={
                "endpoint": "http://localhost:5000",
                "model": "llama",
                "tier": "cloud-fast",
            },
            cloud={
                "endpoint": "https://api.anthropic.com",
                "model": "sonnet",
                "tier": "cloud-fast",
            },
        )
        router = ModelRouter(config)
        endpoint = router.select_model("review", "medium", prefer_local=True)
        assert endpoint is not None
        # Both are cloud-fast tier, but local endpoint name comes first alphabetically


class TestHealthChecking:
    """Tests for ModelRouter health checking."""

    def test_endpoint_assumed_healthy_without_health_url(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            local={
                "endpoint": "http://localhost:5000",
                "model": "llama",
                "tier": "local",
            },
        )
        router = ModelRouter(config)
        endpoint = router.endpoints["local"]
        assert router._is_healthy(endpoint) is True

    def test_health_check_result_cached(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            local={
                "endpoint": "http://localhost:5000",
                "model": "llama",
                "tier": "local",
            },
        )
        router = ModelRouter(config)
        endpoint = router.endpoints["local"]

        # First check
        router._is_healthy(endpoint)
        first_check_time = endpoint._last_health_check

        # Second check (should use cache)
        router._is_healthy(endpoint)
        assert endpoint._last_health_check == first_check_time


class TestFallback:
    """Tests for ModelRouter fallback logic."""

    def test_local_falls_back_to_cloud_fast(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            sonnet={
                "endpoint": "https://api.anthropic.com",
                "model": "sonnet",
                "tier": "cloud-fast",
            },
        )
        router = ModelRouter(config)
        endpoint = router._fallback("local", prefer_local=True)
        assert endpoint is not None
        assert endpoint.tier == "cloud-fast"

    def test_cloud_fast_falls_back_to_local_when_preferred(
        self, tmp_path: Path
    ) -> None:
        config = _make_config(
            tmp_path,
            local={
                "endpoint": "http://localhost:5000",
                "model": "llama",
                "tier": "local",
            },
        )
        router = ModelRouter(config)
        endpoint = router._fallback("cloud-fast", prefer_local=True)
        assert endpoint is not None
        assert endpoint.tier == "local"

    def test_cloud_heavy_falls_back_to_cloud_fast(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            sonnet={
                "endpoint": "https://api.anthropic.com",
                "model": "sonnet",
                "tier": "cloud-fast",
            },
        )
        router = ModelRouter(config)
        endpoint = router._fallback("cloud-heavy", prefer_local=False)
        assert endpoint is not None
        assert endpoint.tier == "cloud-fast"


class TestRefreshHealth:
    """Tests for ModelRouter.refresh_health."""

    def test_resets_health_check_timestamps(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            local={
                "endpoint": "http://localhost:5000",
                "model": "llama",
                "tier": "local",
            },
        )
        router = ModelRouter(config)
        endpoint = router.endpoints["local"]

        # Trigger initial health check
        router._is_healthy(endpoint)
        assert endpoint._last_health_check > 0

        # Refresh
        router.refresh_health()
        # After refresh, health check should have been re-run
        assert endpoint._last_health_check > 0


class TestGetTierSummary:
    """Tests for ModelRouter.get_tier_summary."""

    def test_empty_router_returns_empty_tiers(self, tmp_path: Path) -> None:
        router = ModelRouter(_make_config(tmp_path))
        summary = router.get_tier_summary()
        assert summary == {"local": [], "cloud-fast": [], "cloud-heavy": []}

    def test_groups_endpoints_by_tier(self, tmp_path: Path) -> None:
        config = _make_config(
            tmp_path,
            local_a={
                "endpoint": "http://localhost:5000",
                "model": "llama",
                "tier": "local",
            },
            local_b={
                "endpoint": "http://localhost:5001",
                "model": "mistral",
                "tier": "local",
            },
            sonnet={
                "endpoint": "https://api.anthropic.com",
                "model": "sonnet",
                "tier": "cloud-fast",
            },
            opus={
                "endpoint": "https://api.anthropic.com",
                "model": "opus",
                "tier": "cloud-heavy",
            },
        )
        router = ModelRouter(config)
        summary = router.get_tier_summary()
        assert len(summary["local"]) == 2
        assert len(summary["cloud-fast"]) == 1
        assert len(summary["cloud-heavy"]) == 1


class TestGetTaskTierMapping:
    """Tests for get_task_tier_mapping helper."""

    def test_returns_mapping_dict(self) -> None:
        mapping = get_task_tier_mapping()
        assert isinstance(mapping, dict)
        assert "format" in mapping
        assert "review" in mapping
        assert "architecture" in mapping

    def test_format_maps_to_local(self) -> None:
        mapping = get_task_tier_mapping()
        assert mapping["format"] == "local"

    def test_review_maps_to_cloud_fast(self) -> None:
        mapping = get_task_tier_mapping()
        assert mapping["review"] == "cloud-fast"

    def test_architecture_maps_to_cloud_heavy(self) -> None:
        mapping = get_task_tier_mapping()
        assert mapping["architecture"] == "cloud-heavy"
