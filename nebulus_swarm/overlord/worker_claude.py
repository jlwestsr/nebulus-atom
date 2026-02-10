"""Claude Code worker — subprocess-based LLM dispatch via Claude CLI.

Enables Overlord to delegate code tasks to Claude Code running as a
subprocess with full tool access (file editing, git, etc.). Opt-in
via ``~/.atom/overlord.yml`` workers section.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClaudeWorkerConfig:
    """Configuration for the Claude Code worker."""

    enabled: bool = False
    binary_path: str = "claude"
    default_model: str = "sonnet"
    model_overrides: dict[str, str] = field(default_factory=dict)
    timeout: int = 600


@dataclass
class ClaudeWorkerResult:
    """Result of a Claude Code worker execution."""

    success: bool
    output: str = ""
    error: Optional[str] = None
    duration: float = 0.0
    model_used: str = ""


class ClaudeWorker:
    """Dispatches tasks to Claude Code CLI as a subprocess worker.

    Args:
        config: Worker configuration.
    """

    def __init__(self, config: ClaudeWorkerConfig) -> None:
        self.config = config
        self._binary: Optional[str] = None
        self._available = False

        if config.enabled:
            self._binary = shutil.which(config.binary_path)
            if self._binary:
                self._available = True
                logger.info(f"Claude worker initialized: {self._binary}")
            else:
                logger.warning(
                    f"Claude binary not found at '{config.binary_path}'. "
                    "Worker disabled — falling back to ModelRouter."
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
    ) -> ClaudeWorkerResult:
        """Execute a prompt via Claude Code CLI.

        Args:
            prompt: The task prompt to send to Claude.
            project_path: Working directory for the subprocess.
            task_type: Task category for model selection.
            model: Explicit model override (highest priority).

        Returns:
            ClaudeWorkerResult with output and metadata.
        """
        if not self._available:
            return ClaudeWorkerResult(
                success=False,
                error="Claude worker is not available",
            )

        selected_model = self._select_model(task_type, model)

        cmd = [
            self._binary,  # type: ignore[list-item]
            "-p",
            prompt,
            "--model",
            selected_model,
            "--print",
        ]

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
                return ClaudeWorkerResult(
                    success=True,
                    output=result.stdout.strip(),
                    duration=duration,
                    model_used=selected_model,
                )
            else:
                return ClaudeWorkerResult(
                    success=False,
                    output=result.stdout.strip(),
                    error=result.stderr.strip() or f"Exit code {result.returncode}",
                    duration=duration,
                    model_used=selected_model,
                )

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return ClaudeWorkerResult(
                success=False,
                error=f"Timed out after {self.config.timeout}s",
                duration=duration,
                model_used=selected_model,
            )
        except OSError as e:
            duration = time.monotonic() - start
            return ClaudeWorkerResult(
                success=False,
                error=f"Failed to launch Claude: {e}",
                duration=duration,
                model_used=selected_model,
            )

    def _select_model(self, task_type: str, explicit: Optional[str] = None) -> str:
        """Select model with priority: explicit > override > default.

        Args:
            task_type: Task category for override lookup.
            explicit: Explicit model override from caller.

        Returns:
            Model identifier string.
        """
        if explicit:
            return explicit
        return self.config.model_overrides.get(task_type, self.config.default_model)


def load_worker_config(raw_workers: dict) -> Optional[ClaudeWorkerConfig]:
    """Parse a Claude worker config from the workers YAML section.

    Args:
        raw_workers: The ``workers`` dict from overlord.yml.

    Returns:
        ClaudeWorkerConfig if ``claude`` key exists, else None.
    """
    claude_raw = raw_workers.get("claude")
    if not claude_raw or not isinstance(claude_raw, dict):
        return None

    return ClaudeWorkerConfig(
        enabled=bool(claude_raw.get("enabled", False)),
        binary_path=str(claude_raw.get("binary_path", "claude")),
        default_model=str(claude_raw.get("default_model", "sonnet")),
        model_overrides={
            str(k): str(v) for k, v in claude_raw.get("model_overrides", {}).items()
        },
        timeout=int(claude_raw.get("timeout", 600)),
    )
