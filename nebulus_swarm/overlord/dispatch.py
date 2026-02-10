"""Overlord Dispatch Engine — coordinates task execution across projects."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nebulus_swarm.overlord.action_scope import ActionScope
    from nebulus_swarm.overlord.autonomy import AutonomyEngine
    from nebulus_swarm.overlord.graph import DependencyGraph
    from nebulus_swarm.overlord.memory import OverlordMemory
    from nebulus_swarm.overlord.model_router import ModelRouter
    from nebulus_swarm.overlord.registry import OverlordConfig
    from nebulus_swarm.overlord.worker_claude import ClaudeWorker

logger = logging.getLogger(__name__)

# Maps action phrases to shell commands for direct execution.
# Checked in order; first match wins. More specific patterns first.
ACTION_COMMANDS: list[tuple[str, str]] = [
    ("run tests", "pytest -v"),
    ("run test", "pytest -v"),
    ("lint", "ruff check ."),
    ("format code", "ruff format ."),
    ("type check", "mypy ."),
    ("typecheck", "mypy ."),
]


@dataclass
class DispatchStep:
    """A single atomic step in a dispatch plan."""

    id: str
    action: str
    project: str
    dependencies: list[str] = field(default_factory=list)
    model_tier: Optional[str] = None
    timeout: int = 300


@dataclass
class StepResult:
    """Result of executing a single step."""

    step_id: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    duration: float = 0.0


@dataclass
class DispatchPlan:
    """A multi-step execution plan."""

    task: str
    steps: list[DispatchStep]
    scope: ActionScope
    estimated_duration: int
    requires_approval: bool


@dataclass
class DispatchResult:
    """Result of executing a dispatch plan."""

    status: str  # "success", "failed", "cancelled"
    steps: list[StepResult] = field(default_factory=list)
    reason: str = ""


class DispatchEngine:
    """Coordinates task execution across multiple projects."""

    def __init__(
        self,
        config: OverlordConfig,
        autonomy: AutonomyEngine,
        graph: DependencyGraph,
        model_router: ModelRouter,
        memory: Optional[OverlordMemory] = None,
    ):
        """Initialize the dispatch engine.

        Args:
            config: Overlord configuration.
            autonomy: Autonomy engine for approval decisions.
            graph: Dependency graph for project ordering.
            model_router: Model router for LLM task assignment.
            memory: Optional memory store for dispatch event logging.
        """
        self.config = config
        self.autonomy = autonomy
        self.graph = graph
        self.router = model_router
        self.memory = memory

        # Initialize Claude worker if configured
        self.claude_worker: Optional[ClaudeWorker] = None
        self._init_claude_worker()

    def _init_claude_worker(self) -> None:
        """Initialize Claude Code worker from config if present."""
        from nebulus_swarm.overlord.worker_claude import (
            ClaudeWorker,
            load_worker_config,
        )

        worker_cfg = load_worker_config(self.config.workers)
        if worker_cfg and worker_cfg.enabled:
            self.claude_worker = ClaudeWorker(worker_cfg)
            if not self.claude_worker.available:
                logger.warning("Claude worker enabled but binary not found — disabled")
                self.claude_worker = None

    def execute(self, plan: DispatchPlan, auto_approve: bool = False) -> DispatchResult:
        """Execute a dispatch plan.

        Args:
            plan: The dispatch plan to execute.
            auto_approve: If True, skip approval check (for testing).

        Returns:
            DispatchResult with execution status and step results.
        """
        # Check autonomy — can we auto-execute or need approval?
        if plan.requires_approval and not auto_approve:
            logger.info(
                f"Plan requires approval: {plan.task} "
                f"(affects {len(plan.scope.projects)} projects)"
            )
            if not self._can_auto_approve(plan):
                return DispatchResult(
                    status="cancelled",
                    reason="Requires user approval (autonomy level blocks auto-execution)",
                )

        logger.info(f"Executing plan: {plan.task} ({len(plan.steps)} steps)")

        # Build execution order
        ordered_steps = self._topological_order(plan.steps)

        # Execute steps in order
        results: list[StepResult] = []
        for step in ordered_steps:
            logger.info(f"Executing step: {step.id} ({step.action})")
            result = self._execute_step(step)
            results.append(result)

            if not result.success:
                logger.error(
                    f"Step {step.id} failed: {result.error}. Stopping execution."
                )
                return DispatchResult(
                    status="failed", steps=results, reason=result.error or "Step failed"
                )

        logger.info(f"Plan completed successfully: {plan.task}")
        return DispatchResult(status="success", steps=results)

    def _can_auto_approve(self, plan: DispatchPlan) -> bool:
        """Check if plan can be auto-approved based on autonomy settings.

        Args:
            plan: The dispatch plan.

        Returns:
            True if plan can auto-execute without user approval.
        """
        # Get first project's autonomy level (if multi-project, we escalate anyway)
        project = plan.scope.projects[0] if plan.scope.projects else None

        # Check if action can auto-execute
        return self.autonomy.can_auto_execute(plan.task, plan.scope, project)

    def _topological_order(self, steps: list[DispatchStep]) -> list[DispatchStep]:
        """Order steps based on dependencies (topological sort).

        Args:
            steps: List of steps with dependencies.

        Returns:
            List of steps in execution order.
        """
        # Build dependency graph
        step_map = {step.id: step for step in steps}
        in_degree = {step.id: 0 for step in steps}
        dependents: dict[str, list[str]] = {step.id: [] for step in steps}

        for step in steps:
            for dep_id in step.dependencies:
                if dep_id in step_map:
                    in_degree[step.id] += 1
                    dependents[dep_id].append(step.id)

        # Kahn's algorithm
        queue = [step_id for step_id, degree in in_degree.items() if degree == 0]
        ordered: list[DispatchStep] = []

        while queue:
            current_id = queue.pop(0)
            ordered.append(step_map[current_id])

            for dependent_id in dependents[current_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        if len(ordered) != len(steps):
            logger.error("Circular dependency detected in dispatch plan")
            # Return original order as fallback
            return steps

        return ordered

    def _execute_step(self, step: DispatchStep) -> StepResult:
        """Execute a single step.

        Args:
            step: The step to execute.

        Returns:
            StepResult with execution outcome.
        """
        import time

        start_time = time.time()

        try:
            if step.model_tier:
                # LLM-powered step — dispatch to worker
                result = self._dispatch_to_worker(step)
            else:
                # Direct execution (git command, script, etc.)
                result = self._execute_direct(step)

            duration = time.time() - start_time
            return StepResult(
                step_id=step.id,
                success=result["success"],
                output=result.get("output", ""),
                error=result.get("error"),
                duration=duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"Step {step.id} raised exception")
            return StepResult(
                step_id=step.id,
                success=False,
                error=str(e),
                duration=duration,
            )

    def _dispatch_to_worker(self, step: DispatchStep) -> dict[str, object]:
        """Dispatch a step to an LLM worker.

        Tries Claude Code worker first if available, falls back to
        ModelRouter simulation.

        Args:
            step: The step requiring LLM processing.

        Returns:
            Dict with success, output, and optional error.
        """
        task_type = self._infer_task_type(step.action)

        # Try Claude Code worker first
        if self.claude_worker and self.claude_worker.available:
            project_cfg = self.config.projects.get(step.project)
            project_path = project_cfg.path if project_cfg else Path.cwd()

            logger.info(
                f"Dispatching to Claude worker: {step.action} in {step.project}"
            )
            result = self.claude_worker.execute(
                prompt=step.action,
                project_path=project_path,
                task_type=task_type,
            )

            if self.memory:
                self.memory.remember(
                    content=f"Claude worker: {step.action} -> "
                    f"{'success' if result.success else 'failed'}",
                    category="dispatch",
                    project=step.project,
                )

            if result.success:
                return {"success": True, "output": result.output}
            else:
                return {
                    "success": False,
                    "output": result.output,
                    "error": result.error,
                }

        # Fall back to ModelRouter path
        endpoint = self.router.select_model(
            task_type=task_type,
            complexity="medium",
        )

        if not endpoint:
            return {
                "success": False,
                "error": "No healthy model endpoint available",
            }

        logger.info(f"Dispatching to {endpoint.name} ({endpoint.tier}): {step.action}")

        return {
            "success": True,
            "output": f"[Simulated] Dispatched to {endpoint.name}: {step.action}",
        }

    def _execute_direct(self, step: DispatchStep) -> dict[str, object]:
        """Execute a step directly (non-LLM, e.g., git commands).

        Args:
            step: The step to execute.

        Returns:
            Dict with success, output, and optional error.
        """
        logger.info(f"Direct execution: {step.action} in {step.project}")

        command = self._action_to_command(step.action)
        if not command:
            return {
                "success": True,
                "output": f"[Simulated] Executed: {step.action} in {step.project}",
            }

        project_cfg = self.config.projects.get(step.project)
        project_path = project_cfg.path if project_cfg else None
        cwd = str(project_path) if project_path and project_path.exists() else None

        # Guard: skip real execution when project path lacks expected structure
        if not self._can_execute_in(command, project_path):
            return {
                "success": True,
                "output": f"[Simulated] Executed: {step.action} in {step.project}",
            }

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=step.timeout,
            )

            if self.memory:
                self.memory.remember(
                    content=f"Direct exec: {command} -> exit {result.returncode}",
                    category="dispatch",
                    project=step.project,
                )

            if result.returncode == 0:
                return {"success": True, "output": result.stdout.strip()}
            else:
                return {
                    "success": False,
                    "output": result.stdout.strip(),
                    "error": result.stderr.strip() or f"Exit code {result.returncode}",
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Command timed out after {step.timeout}s",
            }
        except OSError as e:
            return {"success": False, "error": f"Failed to execute: {e}"}

    @staticmethod
    def _action_to_command(action: str) -> Optional[str]:
        """Map an action description to a shell command.

        Args:
            action: Human-readable action description.

        Returns:
            Shell command string, or None if no mapping found.
        """
        action_lower = action.lower().strip()

        # Phrase matches from ACTION_COMMANDS (ordered, first match wins)
        for phrase, cmd in ACTION_COMMANDS:
            if phrase in action_lower:
                return cmd

        # Git merge pattern: "merge X to Y" or "merge X into Y"
        for sep in (" to ", " into "):
            if action_lower.startswith("merge ") and sep in action_lower:
                parts = action_lower.removeprefix("merge ").split(sep, 1)
                if len(parts) == 2:
                    source = parts[0].strip()
                    target = parts[1].strip()
                    return f"git checkout {target} && git merge --no-ff {source}"

        # Git checkout pattern
        if action_lower.startswith("checkout "):
            branch = action_lower.removeprefix("checkout ").strip()
            return f"git checkout {branch}"

        return None

    def _infer_task_type(self, action: str) -> str:
        """Infer task type from action description.

        Args:
            action: Action description string.

        Returns:
            Task type for model routing.
        """
        action_lower = action.lower()

        if any(kw in action_lower for kw in ["format", "lint", "style"]):
            return "format"
        if any(kw in action_lower for kw in ["review", "check", "validate"]):
            return "review"
        if any(kw in action_lower for kw in ["feature", "implement", "add"]):
            return "feature"
        if any(kw in action_lower for kw in ["architecture", "design", "plan"]):
            return "architecture"

        return "feature"  # Default

    @staticmethod
    def _can_execute_in(command: str, project_path: Optional[Path]) -> bool:
        """Check if a command can meaningfully run in the project path.

        Args:
            command: Shell command to execute.
            project_path: Project directory.

        Returns:
            True if the project has the expected structure for the command.
        """
        if not project_path or not project_path.exists():
            return False

        if command.startswith("git "):
            return (project_path / ".git").exists()

        if command.startswith(("pytest", "ruff", "mypy")):
            return (project_path / "pyproject.toml").exists() or (
                project_path / "setup.py"
            ).exists()

        return True


def build_simple_plan(
    task: str,
    project: str,
    scope: ActionScope,
    requires_approval: bool = True,
) -> DispatchPlan:
    """Build a simple single-step dispatch plan.

    Args:
        task: Task description.
        project: Target project.
        scope: Action scope.
        requires_approval: Whether plan needs approval.

    Returns:
        DispatchPlan with a single step.
    """
    step = DispatchStep(
        id="step-1",
        action=task,
        project=project,
        dependencies=[],
        model_tier=None,
        timeout=300,
    )

    return DispatchPlan(
        task=task,
        steps=[step],
        scope=scope,
        estimated_duration=step.timeout,
        requires_approval=requires_approval,
    )
