"""Base worker abstraction for multi-backend LLM dispatch.

Defines the ABC and shared dataclasses that all worker backends
(Claude, Gemini, Local/TabbyAPI) implement.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Base configuration shared by all worker backends."""

    enabled: bool = False
    binary_path: str = ""
    default_model: str = ""
    model_overrides: dict[str, str] = field(default_factory=dict)
    timeout: int = 600


@dataclass
class WorkerResult:
    """Result of a worker execution."""

    success: bool
    output: str = ""
    error: Optional[str] = None
    duration: float = 0.0
    model_used: str = ""
    worker_type: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0


class BaseWorker(ABC):
    """Abstract base class for all LLM worker backends.

    Args:
        config: Worker configuration.
    """

    worker_type: str = "base"

    def __init__(self, config: WorkerConfig) -> None:
        self.config = config

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether the worker is ready to accept tasks."""
        ...

    @abstractmethod
    def execute(
        self,
        prompt: str,
        project_path: Path,
        task_type: str = "feature",
        model: Optional[str] = None,
    ) -> WorkerResult:
        """Execute a prompt and return the result.

        Args:
            prompt: The task prompt to send.
            project_path: Working directory for execution.
            task_type: Task category for model selection.
            model: Explicit model override (highest priority).

        Returns:
            WorkerResult with output and metadata.
        """
        ...

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
