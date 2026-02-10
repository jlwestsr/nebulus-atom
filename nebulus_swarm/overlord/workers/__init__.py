"""Worker backends for Overlord multi-backend LLM dispatch.

Exports all worker classes and a convenience loader for initializing
all configured workers from overlord.yml.
"""

from __future__ import annotations

from typing import Optional

from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerConfig, WorkerResult
from nebulus_swarm.overlord.workers.claude import (
    ClaudeWorker,
    ClaudeWorkerConfig,
    load_worker_config as load_claude_worker_config,
)
from nebulus_swarm.overlord.workers.gemini import (
    GeminiWorker,
    GeminiWorkerConfig,
    load_gemini_worker_config,
)
from nebulus_swarm.overlord.workers.local import (
    LocalWorker,
    LocalWorkerConfig,
    load_local_worker_config,
)

ALL_WORKERS: dict[str, type[BaseWorker]] = {
    "claude": ClaudeWorker,
    "gemini": GeminiWorker,
    "local": LocalWorker,
}

__all__ = [
    "ALL_WORKERS",
    "BaseWorker",
    "ClaudeWorker",
    "ClaudeWorkerConfig",
    "GeminiWorker",
    "GeminiWorkerConfig",
    "LocalWorker",
    "LocalWorkerConfig",
    "WorkerConfig",
    "WorkerResult",
    "load_all_workers",
    "load_claude_worker_config",
    "load_gemini_worker_config",
    "load_local_worker_config",
]


def load_all_workers(raw_workers: dict) -> dict[str, BaseWorker]:
    """Initialize all configured workers from the workers YAML section.

    Args:
        raw_workers: The ``workers`` dict from overlord.yml.

    Returns:
        Dict mapping worker type name to initialized worker instance.
        Only includes workers that are enabled and available.
    """
    workers: dict[str, BaseWorker] = {}

    loaders: list[tuple[str, type[BaseWorker], Optional[WorkerConfig]]] = [
        ("claude", ClaudeWorker, load_claude_worker_config(raw_workers)),
        ("gemini", GeminiWorker, load_gemini_worker_config(raw_workers)),
        ("local", LocalWorker, load_local_worker_config(raw_workers)),
    ]

    for name, worker_cls, config in loaders:
        if config and config.enabled:
            worker = worker_cls(config)
            if worker.available:
                workers[name] = worker

    return workers
