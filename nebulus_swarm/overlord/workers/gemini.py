"""Gemini worker — native SDK-based LLM dispatch via Google API.

Uses the Google Generative AI Python SDK for direct API calls with
token tracking, replacing the previous subprocess-based CLI execution.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerConfig, WorkerResult

logger = logging.getLogger(__name__)


@dataclass
class GeminiWorkerConfig(WorkerConfig):
    """Configuration for the Gemini worker."""

    enabled: bool = False
    binary_path: str = "gemini"
    default_model: str = "gemini-2.5-pro"
    model_overrides: dict[str, str] = field(default_factory=dict)
    timeout: int = 600
    api_key: Optional[str] = None
    api_key_env: str = "GOOGLE_API_KEY"


class GeminiWorker(BaseWorker):
    """Dispatches tasks to Google Generative AI API via native SDK.

    Args:
        config: Worker configuration.
    """

    worker_type: str = "gemini"

    def __init__(self, config: GeminiWorkerConfig) -> None:
        super().__init__(config)
        self._available = False
        self._api_key: Optional[str] = None

        if config.enabled:
            self._api_key = config.api_key or os.environ.get(config.api_key_env)
            if self._api_key:
                self._available = True
                logger.info("Gemini worker initialized via SDK")
            else:
                logger.warning(
                    f"No API key found (checked config.api_key and "
                    f"${config.api_key_env}). Worker disabled."
                )

    @property
    def available(self) -> bool:
        """Whether the worker is enabled and an API key is available."""
        return self._available

    def execute(
        self,
        prompt: str,
        project_path: Path,
        task_type: str = "feature",
        model: Optional[str] = None,
    ) -> WorkerResult:
        """Execute a prompt via the Google Generative AI SDK.

        Args:
            prompt: The task prompt to send to Gemini.
            project_path: Working directory context.
            task_type: Task category for model selection.
            model: Explicit model override (highest priority).

        Returns:
            WorkerResult with output, token counts, and metadata.
        """
        if not self._available:
            return WorkerResult(
                success=False,
                error="Gemini worker is not available",
                worker_type=self.worker_type,
            )

        from nebulus_swarm.overlord.workers.sdk_factory import call_google

        selected_model = self._select_model(task_type, model)

        start = time.monotonic()
        try:
            response = call_google(
                prompt=prompt,
                model=selected_model,
                api_key=self._api_key,
                timeout=self.config.timeout,
            )
            duration = time.monotonic() - start

            tokens_total = response.tokens_input + response.tokens_output
            return WorkerResult(
                success=True,
                output=response.content.strip(),
                duration=duration,
                model_used=response.model,
                worker_type=self.worker_type,
                tokens_input=response.tokens_input,
                tokens_output=response.tokens_output,
                tokens_total=tokens_total,
            )

        except ValueError as e:
            duration = time.monotonic() - start
            return WorkerResult(
                success=False,
                error=str(e),
                duration=duration,
                model_used=selected_model,
                worker_type=self.worker_type,
            )
        except RuntimeError as e:
            duration = time.monotonic() - start
            return WorkerResult(
                success=False,
                error=str(e),
                duration=duration,
                model_used=selected_model,
                worker_type=self.worker_type,
            )


def load_gemini_worker_config(raw_workers: dict) -> Optional[GeminiWorkerConfig]:
    """Parse a Gemini worker config from the workers YAML section.

    Args:
        raw_workers: The ``workers`` dict from overlord.yml.

    Returns:
        GeminiWorkerConfig if ``gemini`` key exists, else None.
    """
    gemini_raw = raw_workers.get("gemini")
    if not gemini_raw or not isinstance(gemini_raw, dict):
        return None

    return GeminiWorkerConfig(
        enabled=bool(gemini_raw.get("enabled", False)),
        binary_path=str(gemini_raw.get("binary_path", "gemini")),
        default_model=str(gemini_raw.get("default_model", "gemini-2.5-pro")),
        model_overrides={
            str(k): str(v) for k, v in gemini_raw.get("model_overrides", {}).items()
        },
        timeout=int(gemini_raw.get("timeout", 600)),
        api_key=gemini_raw.get("api_key"),
        api_key_env=str(gemini_raw.get("api_key_env", "GOOGLE_API_KEY")),
    )
