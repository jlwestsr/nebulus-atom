"""Local/TabbyAPI worker — HTTP-based LLM dispatch via OpenAI-compatible endpoint.

Wraps an OpenAI-compatible HTTP endpoint (TabbyAPI, vLLM, etc.) for
task execution using synchronous httpx calls.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerConfig, WorkerResult

logger = logging.getLogger(__name__)


@dataclass
class LocalWorkerConfig(WorkerConfig):
    """Configuration for the local HTTP worker."""

    enabled: bool = False
    binary_path: str = ""
    default_model: str = "default"
    model_overrides: dict[str, str] = field(default_factory=dict)
    timeout: int = 600
    endpoint: str = "http://localhost:5000/v1"
    api_key: Optional[str] = None


class LocalWorker(BaseWorker):
    """Dispatches tasks to an OpenAI-compatible HTTP endpoint.

    Args:
        config: Worker configuration.
    """

    worker_type: str = "local"

    def __init__(self, config: LocalWorkerConfig) -> None:
        super().__init__(config)
        self._available = False
        self._endpoint = config.endpoint.rstrip("/")

        if config.enabled:
            self._available = self._check_health()

    @property
    def available(self) -> bool:
        """Whether the worker is enabled and the endpoint is reachable."""
        return self._available

    def execute(
        self,
        prompt: str,
        project_path: Path,
        task_type: str = "feature",
        model: Optional[str] = None,
    ) -> WorkerResult:
        """Execute a prompt via the OpenAI-compatible HTTP endpoint.

        Args:
            prompt: The task prompt to send.
            project_path: Working directory context (included in system message).
            task_type: Task category for model selection.
            model: Explicit model override (highest priority).

        Returns:
            WorkerResult with output and metadata.
        """
        if not self._available:
            return WorkerResult(
                success=False,
                error="Local worker is not available",
                worker_type=self.worker_type,
            )

        import httpx

        selected_model = self._select_model(task_type, model)
        config: LocalWorkerConfig = self.config  # type: ignore[assignment]

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        payload = {
            "model": selected_model,
            "messages": [
                {
                    "role": "system",
                    "content": f"Working directory: {project_path}",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 4096,
        }

        start = time.monotonic()
        try:
            response = httpx.post(
                f"{self._endpoint}/chat/completions",
                json=payload,
                headers=headers,
                timeout=config.timeout,
            )
            duration = time.monotonic() - start

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return WorkerResult(
                    success=True,
                    output=content.strip(),
                    duration=duration,
                    model_used=selected_model,
                    worker_type=self.worker_type,
                )
            else:
                return WorkerResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text[:500]}",
                    duration=duration,
                    model_used=selected_model,
                    worker_type=self.worker_type,
                )

        except httpx.TimeoutException:
            duration = time.monotonic() - start
            return WorkerResult(
                success=False,
                error=f"Timed out after {config.timeout}s",
                duration=duration,
                model_used=selected_model,
                worker_type=self.worker_type,
            )
        except httpx.HTTPError as e:
            duration = time.monotonic() - start
            return WorkerResult(
                success=False,
                error=f"HTTP error: {e}",
                duration=duration,
                model_used=selected_model,
                worker_type=self.worker_type,
            )

    def _check_health(self) -> bool:
        """Check if the endpoint is reachable via a GET to /models.

        Returns:
            True if the endpoint responds successfully.
        """
        import httpx

        config: LocalWorkerConfig = self.config  # type: ignore[assignment]
        headers: dict[str, str] = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        try:
            response = httpx.get(
                f"{self._endpoint}/models",
                headers=headers,
                timeout=5,
            )
            if response.status_code == 200:
                logger.info(f"Local worker initialized: {self._endpoint}")
                return True
            else:
                logger.warning(
                    f"Local endpoint returned {response.status_code}. Worker disabled."
                )
                return False
        except httpx.HTTPError:
            logger.warning(
                f"Local endpoint unreachable at '{self._endpoint}'. Worker disabled."
            )
            return False


def load_local_worker_config(raw_workers: dict) -> Optional[LocalWorkerConfig]:
    """Parse a local worker config from the workers YAML section.

    Args:
        raw_workers: The ``workers`` dict from overlord.yml.

    Returns:
        LocalWorkerConfig if ``local`` key exists, else None.
    """
    local_raw = raw_workers.get("local")
    if not local_raw or not isinstance(local_raw, dict):
        return None

    return LocalWorkerConfig(
        enabled=bool(local_raw.get("enabled", False)),
        default_model=str(local_raw.get("default_model", "default")),
        model_overrides={
            str(k): str(v) for k, v in local_raw.get("model_overrides", {}).items()
        },
        timeout=int(local_raw.get("timeout", 600)),
        endpoint=str(local_raw.get("endpoint", "http://localhost:5000/v1")),
        api_key=local_raw.get("api_key"),
    )
