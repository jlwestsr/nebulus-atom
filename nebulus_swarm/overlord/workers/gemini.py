"""Gemini CLI worker — subprocess-based LLM dispatch via Gemini CLI.

Wraps the ``gemini -p`` CLI for task execution, following the same
subprocess pattern as the Claude worker.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerConfig, WorkerResult

logger = logging.getLogger(__name__)


@dataclass
class GeminiWorkerConfig(WorkerConfig):
    """Configuration for the Gemini CLI worker."""

    enabled: bool = False
    binary_path: str = "gemini"
    default_model: str = "gemini-2.5-pro"
    model_overrides: dict[str, str] = field(default_factory=dict)
    timeout: int = 600


class GeminiWorker(BaseWorker):
    """Dispatches tasks to Gemini CLI as a subprocess worker.

    Args:
        config: Worker configuration.
    """

    worker_type: str = "gemini"

    def __init__(self, config: GeminiWorkerConfig) -> None:
        super().__init__(config)
        self._binary: Optional[str] = None
        self._available = False

        if config.enabled:
            self._binary = shutil.which(config.binary_path)
            if self._binary:
                self._available = True
                logger.info(f"Gemini worker initialized: {self._binary}")
            else:
                logger.warning(
                    f"Gemini binary not found at '{config.binary_path}'. "
                    "Worker disabled."
                )

    @property
    def available(self) -> bool:
        """Whether the worker is enabled and the binary is accessible."""
        return self._available

    def execute(
        self,
        prompt: str,
        project_path: Path,
        task_type: str = "feature",
        model: Optional[str] = None,
    ) -> WorkerResult:
        """Execute a prompt via Gemini CLI.

        Args:
            prompt: The task prompt to send to Gemini.
            project_path: Working directory for the subprocess.
            task_type: Task category for model selection.
            model: Explicit model override (highest priority).

        Returns:
            WorkerResult with output and metadata.
        """
        if not self._available:
            return WorkerResult(
                success=False,
                error="Gemini worker is not available",
                worker_type=self.worker_type,
            )

        selected_model = self._select_model(task_type, model)
        cmd = self._build_command(prompt, selected_model)
        cwd = str(project_path) if project_path.exists() else None

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )
            duration = time.monotonic() - start

            if result.returncode == 0:
                return WorkerResult(
                    success=True,
                    output=result.stdout.strip(),
                    duration=duration,
                    model_used=selected_model,
                    worker_type=self.worker_type,
                )
            else:
                return WorkerResult(
                    success=False,
                    output=result.stdout.strip(),
                    error=result.stderr.strip() or f"Exit code {result.returncode}",
                    duration=duration,
                    model_used=selected_model,
                    worker_type=self.worker_type,
                )

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return WorkerResult(
                success=False,
                error=f"Timed out after {self.config.timeout}s",
                duration=duration,
                model_used=selected_model,
                worker_type=self.worker_type,
            )
        except OSError as e:
            duration = time.monotonic() - start
            return WorkerResult(
                success=False,
                error=f"Failed to launch Gemini: {e}",
                duration=duration,
                model_used=selected_model,
                worker_type=self.worker_type,
            )

    def _build_command(self, prompt: str, model: str) -> list[str]:
        """Build the Gemini CLI command list.

        Args:
            prompt: The task prompt.
            model: Selected model identifier.

        Returns:
            Command list for subprocess.run.
        """
        return [
            self._binary,  # type: ignore[list-item]
            "-p",
            prompt,
            "--model",
            model,
        ]


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
    )
