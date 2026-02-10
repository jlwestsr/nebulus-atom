"""Backward-compatibility shim — re-exports from workers.claude.

All new code should import from ``nebulus_swarm.overlord.workers.claude``
directly. This module exists to preserve existing imports in dispatch.py,
slack_commands.py, overlord_commands.py, and tests.
"""

from nebulus_swarm.overlord.workers.claude import (  # noqa: F401
    ClaudeWorker,
    ClaudeWorkerConfig,
    ClaudeWorkerResult,
    load_worker_config,
)

__all__ = [
    "ClaudeWorker",
    "ClaudeWorkerConfig",
    "ClaudeWorkerResult",
    "load_worker_config",
]
