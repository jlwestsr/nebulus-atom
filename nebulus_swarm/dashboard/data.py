"""Data client for Swarm Dashboard.

Hybrid data source: polls Overlord HTTP API for real-time data,
reads state.db directly for historical data and analytics.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from nebulus_swarm.overlord.state import OverlordState

logger = logging.getLogger(__name__)

# Cache TTL in seconds
API_CACHE_TTL = 5


@dataclass
class CachedResponse:
    """A cached API response with timestamp."""

    data: Any
    fetched_at: float = field(default_factory=time.time)

    @property
    def is_stale(self) -> bool:
        """Check if the cached data is older than the TTL."""
        return (time.time() - self.fetched_at) > API_CACHE_TTL


class SwarmDataClient:
    """Fetches swarm data from Overlord API and state database."""

    def __init__(
        self,
        overlord_url: str = "http://localhost:8080",
        state_db_path: str = "/var/lib/overlord/state.db",
    ):
        """Initialize data client.

        Args:
            overlord_url: Overlord HTTP base URL.
            state_db_path: Path to the Overlord state SQLite database.
        """
        self.overlord_url = overlord_url.rstrip("/")
        self._state: Optional[OverlordState] = None
        self._state_db_path = state_db_path

        # API response cache
        self._cache: Dict[str, CachedResponse] = {}

    @property
    def state(self) -> Optional[OverlordState]:
        """Lazily initialize the state DB connection."""
        if self._state is None:
            try:
                self._state = OverlordState(db_path=self._state_db_path)
            except Exception as e:
                logger.warning(f"Cannot open state DB: {e}")
        return self._state

    # ------------------------------------------------------------------
    # Real-time data (Overlord HTTP API)
    # ------------------------------------------------------------------

    def _fetch_api(self, path: str) -> Optional[dict]:
        """Fetch JSON from the Overlord API with caching.

        Args:
            path: API path (e.g., "/status").

        Returns:
            Parsed JSON response, or None on failure.
        """
        # Check cache
        cached = self._cache.get(path)
        if cached and not cached.is_stale:
            return cached.data

        url = f"{self.overlord_url}{path}"
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            self._cache[path] = CachedResponse(data=data)
            return data
        except requests.ConnectionError:
            logger.debug(f"Cannot reach Overlord at {url}")
            return None
        except Exception as e:
            logger.debug(f"API error for {path}: {e}")
            return None

    def get_status(self) -> Optional[dict]:
        """Get real-time Overlord status.

        Returns:
            Status dict with active_minions, config, pending_questions,
            or None if Overlord is unreachable.
        """
        return self._fetch_api("/status")

    def get_health(self) -> Optional[dict]:
        """Get Overlord health check.

        Returns:
            Health dict or None if unreachable.
        """
        return self._fetch_api("/health")

    def get_queue(self) -> Optional[dict]:
        """Get cached queue scan results.

        Returns:
            Dict with 'issues' list and 'paused' flag,
            or None if unreachable.
        """
        return self._fetch_api("/queue")

    def is_overlord_reachable(self) -> bool:
        """Check if the Overlord API is reachable."""
        return self.get_health() is not None

    # ------------------------------------------------------------------
    # Historical data (SQLite)
    # ------------------------------------------------------------------

    def get_work_history(
        self,
        repo: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        """Get work history from state database.

        Args:
            repo: Filter by repository.
            status: Filter by status.
            limit: Maximum records.

        Returns:
            List of work history records, empty list on error.
        """
        if not self.state:
            return []
        try:
            return self.state.get_work_history(repo=repo, status=status, limit=limit)
        except Exception as e:
            logger.warning(f"Failed to read work history: {e}")
            return []

    def get_distinct_repos(self) -> List[str]:
        """Get list of distinct repositories from work history.

        Returns:
            Sorted list of repo names, empty list on error.
        """
        if not self.state:
            return []
        try:
            return self.state.get_distinct_repos()
        except Exception as e:
            logger.warning(f"Failed to read repos: {e}")
            return []

    def get_metrics(self, days: Optional[int] = None) -> dict:
        """Compute aggregate metrics from work history.

        Args:
            days: Number of days to look back. None for all time.

        Returns:
            Dict with total, completed, failed, timeout counts,
            completion_rate, avg_duration, daily_stats.
        """
        if not self.state:
            return self._empty_metrics()

        try:
            # Get all history within the time range
            history = self.state.get_work_history(limit=10000)

            if days is not None:
                cutoff = time.time() - (days * 86400)
                history = [
                    h
                    for h in history
                    if h.get("completed_at")
                    and self._iso_to_timestamp(h["completed_at"]) >= cutoff
                ]

            if not history:
                return self._empty_metrics()

            total = len(history)
            completed = sum(1 for h in history if h["status"] == "completed")
            failed = sum(1 for h in history if h["status"] == "failed")
            timeout = sum(1 for h in history if h["status"] == "timeout")

            durations = [
                h["duration_seconds"]
                for h in history
                if h.get("duration_seconds") is not None
            ]

            avg_duration = sum(durations) / len(durations) if durations else 0
            sorted_durations = sorted(durations)
            median_duration = (
                sorted_durations[len(sorted_durations) // 2] if sorted_durations else 0
            )

            # Daily breakdown
            daily: Dict[str, Dict[str, int]] = {}
            for h in history:
                if h.get("completed_at"):
                    day = h["completed_at"][:10]  # YYYY-MM-DD
                    if day not in daily:
                        daily[day] = {
                            "completed": 0,
                            "failed": 0,
                            "timeout": 0,
                            "total_duration": 0,
                            "count": 0,
                        }
                    daily[day][h["status"]] = daily[day].get(h["status"], 0) + 1
                    if h.get("duration_seconds"):
                        daily[day]["total_duration"] += h["duration_seconds"]
                        daily[day]["count"] += 1

            # Compute daily averages
            daily_stats = []
            for day in sorted(daily.keys()):
                d = daily[day]
                count = d["count"]
                daily_stats.append(
                    {
                        "date": day,
                        "completed": d["completed"],
                        "failed": d["failed"],
                        "timeout": d.get("timeout", 0),
                        "avg_duration": (
                            d["total_duration"] / count if count > 0 else 0
                        ),
                    }
                )

            # Failure analysis
            error_types: Dict[str, Dict[str, Any]] = {}
            for h in history:
                if h["status"] != "completed" and h.get("error_message"):
                    # Extract error type from "type: message" format
                    err_msg = h["error_message"]
                    err_type = (
                        err_msg.split(":")[0].strip() if ":" in err_msg else "unknown"
                    )
                    if err_type not in error_types:
                        error_types[err_type] = {"count": 0, "last_message": ""}
                    error_types[err_type]["count"] += 1
                    error_types[err_type]["last_message"] = err_msg

            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "timeout": timeout,
                "completion_rate": completed / total if total > 0 else 0,
                "avg_duration": avg_duration,
                "median_duration": median_duration,
                "min_duration": min(durations) if durations else 0,
                "max_duration": max(durations) if durations else 0,
                "daily_stats": daily_stats,
                "error_types": error_types,
            }
        except Exception as e:
            logger.warning(f"Failed to compute metrics: {e}")
            return self._empty_metrics()

    @staticmethod
    def _empty_metrics() -> dict:
        """Return an empty metrics dict."""
        return {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "timeout": 0,
            "completion_rate": 0,
            "avg_duration": 0,
            "median_duration": 0,
            "min_duration": 0,
            "max_duration": 0,
            "daily_stats": [],
            "error_types": {},
        }

    @staticmethod
    def _iso_to_timestamp(iso_str: str) -> float:
        """Convert ISO datetime string to Unix timestamp."""
        from datetime import datetime

        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.timestamp()
        except (ValueError, TypeError):
            return 0.0
