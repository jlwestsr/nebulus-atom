"""LLM connection pool for concurrent Minion access."""

import logging
import os
import threading
from dataclasses import dataclass

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 2
BACKOFF_BASE = 1.0
BACKOFF_MAX = 30.0


@dataclass
class PoolConfig:
    """Configuration for the LLM connection pool."""

    base_url: str
    model: str
    api_key: str = "not-needed"
    timeout: int = 600
    max_concurrency: int = DEFAULT_CONCURRENCY
    acquire_timeout: float = 60.0  # seconds to wait for a slot

    @classmethod
    def from_env(cls, **overrides) -> "PoolConfig":
        """Create config from environment variables."""
        return cls(
            base_url=overrides.get(
                "base_url",
                os.environ.get("ATOM_LLM_BASE_URL", "http://localhost:5000/v1"),
            ),
            model=overrides.get("model", os.environ.get("ATOM_LLM_MODEL", "default")),
            api_key=overrides.get(
                "api_key", os.environ.get("ATOM_LLM_API_KEY", "not-needed")
            ),
            timeout=int(
                overrides.get("timeout", os.environ.get("ATOM_LLM_TIMEOUT", "600"))
            ),
            max_concurrency=int(
                overrides.get(
                    "max_concurrency",
                    os.environ.get("ATOM_LLM_CONCURRENCY", str(DEFAULT_CONCURRENCY)),
                )
            ),
            acquire_timeout=float(overrides.get("acquire_timeout", "60.0")),
        )


@dataclass
class PoolStats:
    """Current pool statistics."""

    active: int = 0
    waiting: int = 0
    total_requests: int = 0
    total_errors: int = 0
    total_retries: int = 0


class LLMPool:
    """Thread-safe connection pool for OpenAI-compatible LLM backends."""

    def __init__(self, config: PoolConfig):
        self.config = config
        self._semaphore = threading.Semaphore(config.max_concurrency)
        self._lock = threading.Lock()
        self._stats = PoolStats()
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout,
        )
        self._shutdown = False

    @property
    def stats(self) -> PoolStats:
        """Get current pool statistics (snapshot)."""
        with self._lock:
            return PoolStats(
                active=self._stats.active,
                waiting=self._stats.waiting,
                total_requests=self._stats.total_requests,
                total_errors=self._stats.total_errors,
                total_retries=self._stats.total_retries,
            )

    def acquire(self) -> bool:
        """Acquire a slot from the pool. Returns True if acquired, False on timeout."""
        if self._shutdown:
            return False
        with self._lock:
            self._stats.waiting += 1
        try:
            acquired = self._semaphore.acquire(timeout=self.config.acquire_timeout)
            if acquired:
                with self._lock:
                    self._stats.active += 1
                    self._stats.total_requests += 1
            return acquired
        finally:
            with self._lock:
                self._stats.waiting -= 1

    def release(self) -> None:
        """Release a slot back to the pool."""
        with self._lock:
            self._stats.active = max(0, self._stats.active - 1)
        self._semaphore.release()

    def record_error(self) -> None:
        """Record an error (e.g. 429, 503)."""
        with self._lock:
            self._stats.total_errors += 1

    def record_retry(self) -> None:
        """Record a retry attempt."""
        with self._lock:
            self._stats.total_retries += 1

    def shutdown(self) -> None:
        """Mark pool as shut down — no new acquisitions."""
        self._shutdown = True

    @property
    def client(self) -> OpenAI:
        """Get the shared OpenAI client."""
        return self._client
