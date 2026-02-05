"""Platform health API client for hardware-aware dispatch.

Queries the platform (Edge/Prime) for thermal state, VRAM usage,
and system load. Supervisor uses this to adjust timeouts and throttle.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5


@dataclass
class HealthStatus:
    """Current platform health status."""

    thermal_level: int  # 0=normal, 1=warm, 2=hot, 3=critical
    vram_percent: float  # 0-100
    cpu_percent: float  # 0-100
    inference_latency_ms: float  # Last inference latency
    available: bool = True  # False if health check failed

    @property
    def is_throttled(self) -> bool:
        """Check if platform is in a throttled state."""
        return self.thermal_level >= 2

    @property
    def is_critical(self) -> bool:
        """Check if platform is in critical state."""
        return self.thermal_level >= 3

    @property
    def vram_pressure(self) -> bool:
        """Check if VRAM is under pressure (>90%)."""
        return self.vram_percent > 90


@dataclass
class HealthConfig:
    """Configuration for health client."""

    url: Optional[str] = None
    timeout: int = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls) -> "HealthConfig":
        """Load config from environment."""
        return cls(
            url=os.environ.get("ATOM_HEALTH_URL"),
            timeout=int(os.environ.get("ATOM_HEALTH_TIMEOUT", str(DEFAULT_TIMEOUT))),
        )

    @property
    def enabled(self) -> bool:
        """Check if health monitoring is configured."""
        return bool(self.url)


class HealthClient:
    """Client for querying platform health endpoint.

    When ATOM_HEALTH_URL is set, queries the platform for:
    - Thermal state (0-3)
    - VRAM usage percentage
    - CPU usage percentage
    - Inference latency

    When not configured or unavailable, returns healthy defaults.
    """

    # Default "healthy" status when health monitoring disabled/unavailable
    DEFAULT_STATUS = HealthStatus(
        thermal_level=0,
        vram_percent=50.0,
        cpu_percent=50.0,
        inference_latency_ms=100.0,
        available=False,
    )

    def __init__(self, config: Optional[HealthConfig] = None):
        """Initialize health client.

        Args:
            config: Health configuration. If None, loads from environment.
        """
        self.config = config or HealthConfig.from_env()

    @property
    def enabled(self) -> bool:
        """Check if health monitoring is enabled."""
        return self.config.enabled

    def get_status(self) -> HealthStatus:
        """Get current platform health status.

        Returns:
            HealthStatus with current values, or defaults if unavailable.
        """
        if not self.config.enabled or not self.config.url:
            return self.DEFAULT_STATUS

        try:
            response = requests.get(
                self.config.url,
                timeout=self.config.timeout,
            )
            if response.status_code == 200:
                data = response.json()
                return HealthStatus(
                    thermal_level=int(data.get("thermal_level", 0)),
                    vram_percent=float(data.get("vram_percent", 50.0)),
                    cpu_percent=float(data.get("cpu_percent", 50.0)),
                    inference_latency_ms=float(data.get("inference_latency_ms", 100.0)),
                    available=True,
                )
            else:
                logger.warning(f"Health endpoint returned {response.status_code}")
                return self.DEFAULT_STATUS
        except requests.exceptions.RequestException as e:
            logger.warning(f"Health check failed: {e}")
            return self.DEFAULT_STATUS
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Invalid health response: {e}")
            return self.DEFAULT_STATUS

    def calculate_timeout_multiplier(
        self, status: Optional[HealthStatus] = None
    ) -> float:
        """Calculate timeout multiplier based on thermal state.

        Args:
            status: Health status to use. If None, fetches current status.

        Returns:
            Multiplier for timeouts (1.0 = normal, 2.0 = doubled, etc.)
        """
        if status is None:
            status = self.get_status()

        if status.thermal_level >= 3:
            return 3.0  # Triple timeout at critical
        elif status.thermal_level >= 2:
            return 2.0  # Double timeout when hot
        elif status.thermal_level >= 1:
            return 1.5  # 50% longer when warm
        else:
            return 1.0  # Normal

    def should_pause_dispatch(self, status: Optional[HealthStatus] = None) -> bool:
        """Check if dispatch should be paused due to thermal state.

        Args:
            status: Health status to use. If None, fetches current status.

        Returns:
            True if dispatch should be paused.
        """
        if status is None:
            status = self.get_status()
        return status.is_critical

    def should_switch_model(self, status: Optional[HealthStatus] = None) -> bool:
        """Check if should switch to smaller model due to VRAM pressure.

        Args:
            status: Health status to use. If None, fetches current status.

        Returns:
            True if should consider switching to smaller model.
        """
        if status is None:
            status = self.get_status()
        return status.vram_pressure


# Cached singleton
_health_client: Optional[HealthClient] = None


def get_health_client() -> HealthClient:
    """Get cached health client instance."""
    global _health_client
    if _health_client is None:
        _health_client = HealthClient()
    return _health_client


def reset_health_client() -> None:
    """Reset cached health client (for testing)."""
    global _health_client
    _health_client = None
