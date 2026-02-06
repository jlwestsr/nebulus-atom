"""Overlord Model Router — three-tier routing with health checking."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nebulus_swarm.overlord.registry import OverlordConfig

logger = logging.getLogger(__name__)


@dataclass
class ModelEndpoint:
    """Configuration for a single LLM endpoint."""

    name: str
    endpoint: str
    model: str
    tier: str  # "local", "cloud-fast", "cloud-heavy"
    concurrent: int = 1
    health_check_url: Optional[str] = None
    _last_health_check: float = field(default=0.0, init=False, repr=False)
    _is_healthy: bool = field(default=True, init=False, repr=False)


class ModelRouter:
    """Routes tasks to appropriate LLM tier with health checking and fallback."""

    def __init__(self, config: OverlordConfig):
        """Initialize the router.

        Args:
            config: Overlord configuration containing models section.
        """
        self.config = config
        self.endpoints: dict[str, ModelEndpoint] = {}
        self._load_endpoints()

    def _load_endpoints(self) -> None:
        """Parse models config into ModelEndpoint instances."""
        for name, data in self.config.models.items():
            if not isinstance(data, dict):
                logger.warning(f"Skipping invalid model config: {name}")
                continue

            self.endpoints[name] = ModelEndpoint(
                name=name,
                endpoint=str(data.get("endpoint", "")),
                model=str(data.get("model", "")),
                tier=str(data.get("tier", "cloud-fast")),
                concurrent=int(data.get("concurrent", 1)),
                health_check_url=data.get("health_check_url"),
            )

    def select_model(
        self, task_type: str, complexity: str = "medium", prefer_local: bool = True
    ) -> Optional[ModelEndpoint]:
        """Select best available model for a task.

        Args:
            task_type: Task category (format, feature, review, architecture, etc.)
            complexity: Complexity level (low, medium, high).
            prefer_local: Whether to prefer local endpoints when available.

        Returns:
            ModelEndpoint if available, None if no models configured.
        """
        if not self.endpoints:
            logger.warning("No models configured")
            return None

        # Infer target tier
        target_tier = self._infer_tier(task_type, complexity)

        logger.info(
            f"Selecting model: task_type={task_type}, complexity={complexity}, "
            f"target_tier={target_tier}"
        )

        # Try target tier
        endpoint = self._get_healthy_endpoint(target_tier, prefer_local)
        if endpoint:
            logger.info(f"Selected {endpoint.name} ({endpoint.tier})")
            return endpoint

        # Fallback
        endpoint = self._fallback(target_tier, prefer_local)
        if endpoint:
            logger.warning(
                f"Tier '{target_tier}' unavailable, falling back to "
                f"{endpoint.name} ({endpoint.tier})"
            )
            return endpoint

        logger.error("No healthy endpoints available")
        return None

    def _infer_tier(self, task_type: str, complexity: str) -> str:
        """Infer target tier from task type and complexity.

        Args:
            task_type: Task category.
            complexity: Complexity level.

        Returns:
            One of: "local", "cloud-fast", "cloud-heavy"
        """
        # Simple/mechanical tasks → local
        if task_type in ("format", "lint", "boilerplate"):
            return "local"

        # Feature implementation
        if task_type == "feature":
            if complexity in ("low", "medium"):
                return "local"
            return "cloud-fast"

        # Code review → cloud-fast
        if task_type == "review":
            return "cloud-fast"

        # Architecture/planning → cloud-heavy
        if task_type in ("architecture", "planning"):
            return "cloud-heavy"

        # Default to cloud-fast
        return "cloud-fast"

    def _get_healthy_endpoint(
        self, tier: str, prefer_local: bool
    ) -> Optional[ModelEndpoint]:
        """Get a healthy endpoint from the target tier.

        Args:
            tier: Target tier.
            prefer_local: Whether to prefer local endpoints.

        Returns:
            Healthy endpoint or None.
        """
        candidates = [ep for ep in self.endpoints.values() if ep.tier == tier]

        if not candidates:
            return None

        # Sort: local first if preferred, then by name for stability
        candidates.sort(
            key=lambda ep: (not prefer_local or ep.endpoint != "local", ep.name)
        )

        for endpoint in candidates:
            if self._is_healthy(endpoint):
                return endpoint

        return None

    def _is_healthy(self, endpoint: ModelEndpoint) -> bool:
        """Check if endpoint is healthy (with caching).

        Args:
            endpoint: Endpoint to check.

        Returns:
            True if healthy.
        """
        now = time.time()
        cache_ttl = 60.0  # Cache health checks for 60 seconds

        # Use cached result if recent
        if now - endpoint._last_health_check < cache_ttl:
            return endpoint._is_healthy

        # Local endpoints assumed healthy
        if not endpoint.health_check_url:
            endpoint._is_healthy = True
            endpoint._last_health_check = now
            return True

        # TODO: Implement HTTP health check
        # For now, assume healthy
        endpoint._is_healthy = True
        endpoint._last_health_check = now
        return True

    def _fallback(
        self, preferred_tier: str, prefer_local: bool
    ) -> Optional[ModelEndpoint]:
        """Find fallback endpoint when preferred tier unavailable.

        Fallback order:
        - local → cloud-fast → cloud-heavy
        - cloud-fast → local → cloud-heavy
        - cloud-heavy → cloud-fast → local

        Args:
            preferred_tier: The tier that was unavailable.
            prefer_local: Whether to prefer local endpoints.

        Returns:
            Fallback endpoint or None.
        """
        fallback_order = {
            "local": ["cloud-fast", "cloud-heavy"],
            "cloud-fast": (
                ["local", "cloud-heavy"] if prefer_local else ["cloud-heavy", "local"]
            ),
            "cloud-heavy": ["cloud-fast", "local"],
        }

        for tier in fallback_order.get(preferred_tier, []):
            endpoint = self._get_healthy_endpoint(tier, prefer_local)
            if endpoint:
                return endpoint

        return None

    def refresh_health(self) -> None:
        """Force refresh health checks for all endpoints."""
        for endpoint in self.endpoints.values():
            endpoint._last_health_check = 0.0
            self._is_healthy(endpoint)

    def get_tier_summary(self) -> dict[str, list[str]]:
        """Get summary of endpoints by tier.

        Returns:
            Dict mapping tier -> list of endpoint names.
        """
        summary: dict[str, list[str]] = {
            "local": [],
            "cloud-fast": [],
            "cloud-heavy": [],
        }

        for endpoint in self.endpoints.values():
            if endpoint.tier in summary:
                summary[endpoint.tier].append(endpoint.name)

        return summary


def get_task_tier_mapping() -> dict[str, str]:
    """Get default task type → tier mapping.

    Returns:
        Dict mapping task types to their default tier.
    """
    return {
        "format": "local",
        "lint": "local",
        "boilerplate": "local",
        "feature": "local/cloud-fast",  # Depends on complexity
        "review": "cloud-fast",
        "architecture": "cloud-heavy",
        "planning": "cloud-heavy",
    }
