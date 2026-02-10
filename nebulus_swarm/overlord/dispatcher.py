"""Core dispatch loop — Analyze → Brief → Provision → Execute → Review.

Orchestrates the full lifecycle of dispatching a task from the work queue
through worker execution and optional review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from nebulus_swarm.overlord.mirrors import MirrorManager
from nebulus_swarm.overlord.mission_brief import (
    build_review_prompt,
    build_worker_prompt,
    generate_mission_brief,
)
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.work_queue import (
    DispatchResultRecord,
    Task,
    WorkQueue,
)
from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerResult

logger = logging.getLogger(__name__)

# Tier mapping: task complexity/type → preferred worker tier
TIER_MAP: dict[str, str] = {
    "format": "local",
    "lint": "local",
    "boilerplate": "local",
    "review": "cloud-fast",
    "architecture": "cloud-heavy",
    "planning": "cloud-heavy",
}

# Worker tier preferences
TIER_TO_WORKER: dict[str, str] = {
    "local": "local",
    "cloud-fast": "claude",
    "cloud-heavy": "claude",
}

# Fallback order when preferred worker is unavailable
FALLBACK_ORDER: list[str] = ["claude", "gemini", "local"]

# Model override for cloud-heavy tier (use Opus)
CLOUD_HEAVY_MODEL = "opus"


@dataclass
class DispatchContext:
    """Everything needed to execute a task."""

    task: Task
    project_config: ProjectConfig
    worker: BaseWorker
    worktree_path: Optional[Path] = None
    brief_path: Optional[Path] = None
    model: Optional[str] = None
    dry_run: bool = False


class Dispatcher:
    """Orchestrates the Analyze → Brief → Provision → Execute → Review loop.

    Args:
        queue: Work queue for task state management.
        config: Overlord configuration with project registry.
        mirrors: Mirror manager for worktree provisioning.
        workers: Dict mapping worker name to BaseWorker instance.
    """

    def __init__(
        self,
        queue: WorkQueue,
        config: OverlordConfig,
        mirrors: MirrorManager,
        workers: dict[str, BaseWorker],
    ) -> None:
        self.queue = queue
        self.config = config
        self.mirrors = mirrors
        self.workers = workers

    def dispatch_task(
        self,
        task_id: str,
        *,
        dry_run: bool = False,
        worker_name: Optional[str] = None,
        skip_review: bool = False,
    ) -> DispatchResultRecord:
        """Full lifecycle for one task.

        Steps:
        1. Load task, validate status is active
        2. Lock task, transition active → dispatched
        3. Analyze: select_worker
        4. Brief: generate_mission_brief
        5. Provision: create worktree
        6. Execute (skip if dry_run)
        7. Review (skip if dry_run or skip_review)
        8. Record result, transition to completed/failed, unlock

        Args:
            task_id: UUID of the task to dispatch.
            dry_run: If True, generate brief and provision but skip execution.
            worker_name: Explicit worker override.
            skip_review: If True, skip the review step.

        Returns:
            DispatchResultRecord with execution details.

        Raises:
            ValueError: If the task is not found or not in active status.
            RuntimeError: If no eligible workers are available.
        """
        # 1. Load and validate
        task = self.queue.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        if task.status != "active":
            raise ValueError(
                f"Task {task_id[:8]} is '{task.status}', expected 'active'"
            )

        project_config = self.config.projects.get(task.project)
        if not project_config:
            raise ValueError(f"Unknown project: {task.project}")

        # 2. Lock and transition
        worker_obj, selected_name = self.select_worker(task, worker_name)
        self.queue.lock_task(task_id, selected_name)

        try:
            self.queue.transition(
                task_id,
                "dispatched",
                changed_by="dispatcher",
                reason=f"Dispatched to worker={selected_name}",
            )

            # 3. Build context
            model = (
                CLOUD_HEAVY_MODEL if self._infer_tier(task) == "cloud-heavy" else None
            )
            ctx = DispatchContext(
                task=task,
                project_config=project_config,
                worker=worker_obj,
                model=model,
                dry_run=dry_run,
            )

            # 4. Provision worktree
            ctx.worktree_path = self.mirrors.provision_worktree(
                task.project,
                task_id,
            )

            # 5. Generate brief
            ctx.brief_path = generate_mission_brief(ctx)

            # 6. Execute
            exec_result: Optional[WorkerResult] = None
            if not dry_run:
                exec_result = self.execute_worker(ctx)

                if not exec_result.success:
                    return self._fail_task(
                        task_id,
                        selected_name,
                        ctx,
                        exec_result,
                        reason=f"Worker execution failed: {exec_result.error}",
                    )

                # 7. Review — always transition through in_review for state machine
                self.queue.transition(
                    task_id,
                    "in_review",
                    changed_by="dispatcher",
                    reason="Execution complete, starting review"
                    if not skip_review
                    else "Execution complete, review skipped",
                )

                if not skip_review:
                    review_result = self.run_review(ctx, exec_result)

                    if not review_result.success:
                        return self._fail_task(
                            task_id,
                            selected_name,
                            ctx,
                            exec_result,
                            reason=f"Review failed: {review_result.error}",
                            review_status="failed",
                        )

            # 8. Record success
            review_status = "skipped" if (dry_run or skip_review) else "passed"
            result = DispatchResultRecord(
                task_id=task_id,
                worker_id=selected_name,
                model_id=exec_result.model_used if exec_result else "",
                branch_name=f"atom/{task_id[:8]}",
                mission_brief_path=str(ctx.brief_path) if ctx.brief_path else "",
                review_status=review_status,
                output_log=exec_result.output if exec_result else "dry-run",
            )
            self.queue.record_dispatch_result(result)

            if not dry_run:
                self.queue.transition(
                    task_id,
                    "completed",
                    changed_by="dispatcher",
                    reason="Dispatch completed successfully",
                )

            return result

        except Exception as e:
            logger.error("Dispatch failed for %s: %s", task_id[:8], e)
            # Attempt to transition to failed
            try:
                current = self.queue.get_task(task_id)
                if current and current.status in ("dispatched", "in_review"):
                    self.queue.transition(
                        task_id,
                        "failed",
                        changed_by="dispatcher",
                        reason=str(e),
                    )
            except Exception:
                logger.exception("Failed to transition task %s to failed", task_id[:8])
            raise
        finally:
            try:
                self.queue.unlock_task(task_id)
            except Exception:
                logger.exception("Failed to unlock task %s", task_id[:8])

    def select_worker(
        self,
        task: Task,
        explicit_name: Optional[str] = None,
    ) -> tuple[BaseWorker, str]:
        """Select the best available worker for a task.

        Args:
            task: The task to dispatch.
            explicit_name: Explicit worker name override.

        Returns:
            Tuple of (worker instance, worker name).

        Raises:
            RuntimeError: If no eligible workers are available.
        """
        if explicit_name:
            worker = self.workers.get(explicit_name)
            if worker and worker.available:
                return worker, explicit_name
            raise RuntimeError(f"Requested worker '{explicit_name}' is not available")

        # Infer tier from task
        tier = self._infer_tier(task)
        preferred = TIER_TO_WORKER.get(tier)

        # Try preferred worker
        if preferred and preferred in self.workers:
            worker = self.workers[preferred]
            if worker.available:
                return worker, preferred

        # Fallback chain
        for name in FALLBACK_ORDER:
            if name in self.workers and self.workers[name].available:
                return self.workers[name], name

        raise RuntimeError("No eligible workers available")

    def select_reviewer(
        self,
        executor_name: str,
    ) -> tuple[BaseWorker, str]:
        """Select a reviewer worker, preferring a different backend than the executor.

        Args:
            executor_name: Name of the worker that executed the task.

        Returns:
            Tuple of (worker instance, worker name).

        Raises:
            RuntimeError: If no review workers are available.
        """
        # Prefer a different worker for review
        for name in FALLBACK_ORDER:
            if name != executor_name and name in self.workers:
                worker = self.workers[name]
                if worker.available:
                    return worker, name

        # Fall back to same worker if nothing else is available
        if executor_name in self.workers:
            worker = self.workers[executor_name]
            if worker.available:
                return worker, executor_name

        raise RuntimeError("No review workers available")

    def generate_brief(self, ctx: DispatchContext) -> Path:
        """Write MISSION_BRIEF.md to worktree.

        Args:
            ctx: Dispatch context with task and worktree_path set.

        Returns:
            Path to the generated brief file.
        """
        return generate_mission_brief(ctx)

    def execute_worker(self, ctx: DispatchContext) -> WorkerResult:
        """Invoke the worker with the mission brief as prompt.

        Args:
            ctx: Dispatch context with worker, brief_path, and worktree_path set.

        Returns:
            WorkerResult from the execution.
        """
        if not ctx.brief_path or not ctx.worktree_path:
            raise ValueError("brief_path and worktree_path must be set")

        prompt = build_worker_prompt(ctx.brief_path)
        return ctx.worker.execute(
            prompt=prompt,
            project_path=ctx.worktree_path,
            task_type=ctx.task.complexity,
            model=ctx.model,
        )

    def run_review(
        self,
        ctx: DispatchContext,
        exec_result: WorkerResult,
    ) -> WorkerResult:
        """Invoke a reviewer worker on the execution results.

        Args:
            ctx: Dispatch context.
            exec_result: Result from the execution worker.

        Returns:
            WorkerResult from the review.
        """
        if not ctx.brief_path or not ctx.worktree_path:
            raise ValueError("brief_path and worktree_path must be set")

        reviewer, _ = self.select_reviewer(ctx.worker.worker_type)
        prompt = build_review_prompt(ctx.brief_path, exec_result.output)
        return reviewer.execute(
            prompt=prompt,
            project_path=ctx.worktree_path,
            task_type="review",
        )

    def _infer_tier(self, task: Task) -> str:
        """Infer the target model tier from task attributes.

        Args:
            task: The task to classify.

        Returns:
            One of: "local", "cloud-fast", "cloud-heavy".
        """
        # Check explicit task type keywords in title/description
        text = f"{task.title} {task.description or ''}".lower()
        for keyword, tier in TIER_MAP.items():
            if keyword in text:
                return tier

        # Fall back on complexity
        if task.complexity in ("low",):
            return "local"
        if task.complexity in ("high",):
            return "cloud-heavy"
        return "cloud-fast"

    def _fail_task(
        self,
        task_id: str,
        worker_id: str,
        ctx: DispatchContext,
        exec_result: Optional[WorkerResult],
        reason: str,
        review_status: str = "",
    ) -> DispatchResultRecord:
        """Record failure and transition task to failed state.

        Args:
            task_id: Task UUID.
            worker_id: Worker that was used.
            ctx: Dispatch context.
            exec_result: Execution result (may be None).
            reason: Failure reason.
            review_status: Review status if applicable.

        Returns:
            DispatchResultRecord for the failed dispatch.
        """
        result = DispatchResultRecord(
            task_id=task_id,
            worker_id=worker_id,
            model_id=exec_result.model_used if exec_result else "",
            branch_name=f"atom/{task_id[:8]}",
            mission_brief_path=str(ctx.brief_path) if ctx.brief_path else "",
            review_status=review_status,
            output_log=exec_result.output if exec_result else "",
        )
        self.queue.record_dispatch_result(result)
        self.queue.transition(
            task_id,
            "failed",
            changed_by="dispatcher",
            reason=reason,
        )
        return result
