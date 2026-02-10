"""Tests for the dispatcher module — dispatch loop orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nebulus_swarm.overlord.dispatcher import (
    DispatchContext,
    Dispatcher,
)
from nebulus_swarm.overlord.mission_brief import BRIEF_FILENAME
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.work_queue import (
    Task,
    WorkQueue,
)
from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerConfig, WorkerResult


# --- Fixtures ---


class FakeWorker(BaseWorker):
    """Fake worker for testing."""

    worker_type: str = "fake"

    def __init__(
        self,
        name: str = "fake",
        is_available: bool = True,
        result: WorkerResult | None = None,
    ) -> None:
        super().__init__(WorkerConfig(enabled=True))
        self.worker_type = name
        self._available = is_available
        self._result = result or WorkerResult(
            success=True,
            output="done",
            model_used="test-model",
            worker_type=name,
        )
        self.execute_calls: list[dict] = []

    @property
    def available(self) -> bool:
        return self._available

    def execute(
        self,
        prompt: str,
        project_path: Path,
        task_type: str = "feature",
        model: str | None = None,
    ) -> WorkerResult:
        self.execute_calls.append(
            {
                "prompt": prompt,
                "project_path": project_path,
                "task_type": task_type,
                "model": model,
            }
        )
        return self._result


@pytest.fixture
def config(tmp_path: Path) -> OverlordConfig:
    return OverlordConfig(
        workspace_root=tmp_path,
        projects={
            "nebulus-core": ProjectConfig(
                name="nebulus-core",
                path=tmp_path / "nebulus-core",
                remote="jlwestsr/nebulus-core",
                role="shared-library",
                depends_on=["nebulus-prime"],
            ),
        },
    )


@pytest.fixture
def queue(tmp_path: Path) -> WorkQueue:
    return WorkQueue(db_path=tmp_path / "test_queue.db")


@pytest.fixture
def mirrors() -> MagicMock:
    mgr = MagicMock()
    mgr.provision_worktree.return_value = Path("/tmp/fake-worktree")
    mgr.cleanup_worktree.return_value = True
    return mgr


@pytest.fixture
def claude_worker() -> FakeWorker:
    return FakeWorker(name="claude")


@pytest.fixture
def gemini_worker() -> FakeWorker:
    return FakeWorker(name="gemini")


@pytest.fixture
def local_worker() -> FakeWorker:
    return FakeWorker(name="local")


@pytest.fixture
def workers(
    claude_worker: FakeWorker,
    gemini_worker: FakeWorker,
    local_worker: FakeWorker,
) -> dict[str, BaseWorker]:
    return {"claude": claude_worker, "gemini": gemini_worker, "local": local_worker}


@pytest.fixture
def dispatcher(
    queue: WorkQueue,
    config: OverlordConfig,
    mirrors: MagicMock,
    workers: dict[str, BaseWorker],
) -> Dispatcher:
    return Dispatcher(queue, config, mirrors, workers)


def _create_active_task(queue: WorkQueue, **kwargs) -> str:
    """Helper to add and triage a task to active."""
    defaults = {"title": "Test task", "project": "nebulus-core"}
    defaults.update(kwargs)
    task_id = queue.add_task(**defaults)
    queue.transition(task_id, "active", changed_by="test")
    return task_id


# --- TestSelectWorker ---


class TestSelectWorker:
    """Tests for worker selection logic."""

    def test_tier_mapping_local(self, dispatcher: Dispatcher, queue: WorkQueue) -> None:
        """Low complexity task maps to local tier."""
        task_id = _create_active_task(queue, complexity="low")
        task = queue.get_task(task_id)
        worker, name = dispatcher.select_worker(task)
        assert name == "local"

    def test_tier_mapping_cloud_heavy(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
    ) -> None:
        """Architecture keyword in title maps to cloud-heavy tier."""
        task_id = _create_active_task(
            queue,
            title="architecture redesign",
            complexity="high",
        )
        task = queue.get_task(task_id)
        worker, name = dispatcher.select_worker(task)
        # cloud-heavy maps to claude
        assert name == "claude"

    def test_fallback_chain(self, queue: WorkQueue, config: OverlordConfig) -> None:
        """Falls through FALLBACK_ORDER when preferred is unavailable."""
        unavailable_claude = FakeWorker(name="claude", is_available=False)
        available_gemini = FakeWorker(name="gemini")
        workers = {"claude": unavailable_claude, "gemini": available_gemini}
        d = Dispatcher(queue, config, MagicMock(), workers)

        task_id = _create_active_task(queue)
        task = queue.get_task(task_id)
        worker, name = d.select_worker(task)
        assert name == "gemini"

    def test_no_workers_raises(self, queue: WorkQueue, config: OverlordConfig) -> None:
        """RuntimeError raised when no workers are available."""
        d = Dispatcher(queue, config, MagicMock(), {})
        task_id = _create_active_task(queue)
        task = queue.get_task(task_id)
        with pytest.raises(RuntimeError, match="No eligible workers"):
            d.select_worker(task)

    def test_explicit_override(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
    ) -> None:
        """Explicit worker_name overrides tier selection."""
        task_id = _create_active_task(queue, complexity="low")
        task = queue.get_task(task_id)
        worker, name = dispatcher.select_worker(task, explicit_name="gemini")
        assert name == "gemini"


# --- TestGenerateBrief ---


class TestGenerateBrief:
    """Tests for mission brief generation."""

    def test_brief_file_written(
        self,
        config: OverlordConfig,
        tmp_path: Path,
    ) -> None:
        """Brief file is written to the worktree."""
        task = Task(id="abc12345", title="Add widget", project="nebulus-core")
        pc = config.projects["nebulus-core"]
        wt = tmp_path / "worktree"
        wt.mkdir()

        ctx = DispatchContext(
            task=task,
            project_config=pc,
            worker=FakeWorker(),
            worktree_path=wt,
        )

        from nebulus_swarm.overlord.mission_brief import generate_mission_brief

        path = generate_mission_brief(ctx)

        assert path.exists()
        assert path.name == BRIEF_FILENAME

    def test_brief_contains_objective_and_constraints(
        self,
        config: OverlordConfig,
        tmp_path: Path,
    ) -> None:
        """Brief contains key sections."""
        task = Task(
            id="abc12345",
            title="Add widget",
            project="nebulus-core",
            description="Implement the widget component",
        )
        pc = config.projects["nebulus-core"]
        wt = tmp_path / "worktree"
        wt.mkdir()

        ctx = DispatchContext(
            task=task,
            project_config=pc,
            worker=FakeWorker(),
            worktree_path=wt,
        )

        from nebulus_swarm.overlord.mission_brief import generate_mission_brief

        generate_mission_brief(ctx)
        content = (wt / BRIEF_FILENAME).read_text()

        assert "Implement the widget component" in content
        assert "## Constraints" in content
        assert "## Verification" in content
        assert "nebulus-core" in content

    def test_brief_contains_project_dependencies(
        self,
        config: OverlordConfig,
        tmp_path: Path,
    ) -> None:
        """Brief includes project dependency information."""
        task = Task(id="abc12345", title="Test", project="nebulus-core")
        pc = config.projects["nebulus-core"]
        wt = tmp_path / "worktree"
        wt.mkdir()

        ctx = DispatchContext(
            task=task,
            project_config=pc,
            worker=FakeWorker(),
            worktree_path=wt,
        )

        from nebulus_swarm.overlord.mission_brief import generate_mission_brief

        generate_mission_brief(ctx)
        content = (wt / BRIEF_FILENAME).read_text()

        assert "nebulus-prime" in content

    def test_dry_run_creates_brief(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """Dry-run still generates the mission brief."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id, dry_run=True)

        assert (wt / BRIEF_FILENAME).exists()


# --- TestDispatchLifecycle ---


class TestDispatchLifecycle:
    """Tests for the full dispatch lifecycle."""

    def test_happy_path(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """Full dispatch: active → dispatched → in_review → completed."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        result = dispatcher.dispatch_task(task_id)

        task = queue.get_task(task_id)
        assert task.status == "completed"
        assert result.review_status == "passed"

    def test_dry_run_stops_before_execute(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
        claude_worker: FakeWorker,
    ) -> None:
        """Dry-run generates brief but doesn't execute worker."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        result = dispatcher.dispatch_task(task_id, dry_run=True)

        assert len(claude_worker.execute_calls) == 0
        assert result.output_log == "dry-run"
        # Task stays dispatched (not completed) on dry-run
        task = queue.get_task(task_id)
        assert task.status == "dispatched"

    def test_failure_transitions_to_failed(
        self,
        queue: WorkQueue,
        config: OverlordConfig,
        mirrors: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Worker failure transitions task to failed."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        fail_worker = FakeWorker(
            name="claude",
            result=WorkerResult(success=False, error="crash", worker_type="claude"),
        )
        d = Dispatcher(queue, config, mirrors, {"claude": fail_worker})

        task_id = _create_active_task(queue)
        d.dispatch_task(task_id, skip_review=True)

        task = queue.get_task(task_id)
        assert task.status == "failed"

    def test_lock_and_unlock(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """Task is locked during dispatch and unlocked after."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        task = queue.get_task(task_id)
        assert task.locked_by is None

    def test_review_step_called(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
        gemini_worker: FakeWorker,
    ) -> None:
        """Review step invokes a (different) worker."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        # Gemini should have been called for review (different from claude executor)
        assert len(gemini_worker.execute_calls) > 0

    def test_skip_review(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
        gemini_worker: FakeWorker,
    ) -> None:
        """skip_review=True skips the review step."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        result = dispatcher.dispatch_task(task_id, skip_review=True)

        assert result.review_status == "skipped"
        assert len(gemini_worker.execute_calls) == 0

    def test_worker_error_recorded(
        self,
        queue: WorkQueue,
        config: OverlordConfig,
        mirrors: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Worker error is recorded in dispatch result."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        fail_worker = FakeWorker(
            name="claude",
            result=WorkerResult(
                success=False,
                error="timeout",
                output="partial output",
                worker_type="claude",
            ),
        )
        d = Dispatcher(queue, config, mirrors, {"claude": fail_worker})

        task_id = _create_active_task(queue)
        d.dispatch_task(task_id, skip_review=True)

        results = queue.get_dispatch_results(task_id)
        assert len(results) >= 1

    def test_dispatch_result_recorded(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """DispatchResultRecord is recorded in the queue."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        results = queue.get_dispatch_results(task_id)
        assert len(results) == 1
        assert results[0].task_id == task_id
        assert results[0].branch_name == f"atom/{task_id[:8]}"

    def test_task_log_entries(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """Dispatch creates audit log entries for each transition."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        log = queue.get_task_log(task_id)
        statuses = [(e.old_status, e.new_status) for e in log]
        # backlog→active (from fixture), active→dispatched, dispatched→in_review, in_review→completed
        assert ("active", "dispatched") in statuses
        assert ("dispatched", "in_review") in statuses
        assert ("in_review", "completed") in statuses

    def test_retry_count_preserved(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """Retry count doesn't change on successful dispatch."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        task = queue.get_task(task_id)
        assert task.retry_count == 0


# --- TestProvision ---


class TestProvision:
    """Tests for worktree provisioning in the dispatch loop."""

    def test_worktree_created(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        mirrors: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Provision is called with correct project and task_id."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id, dry_run=True)

        mirrors.provision_worktree.assert_called_once_with("nebulus-core", task_id)

    def test_mirror_not_found_error(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        mirrors: MagicMock,
    ) -> None:
        """RuntimeError from provision propagates and fails the task."""
        mirrors.provision_worktree.side_effect = RuntimeError("Mirror not initialized")

        task_id = _create_active_task(queue)
        with pytest.raises(RuntimeError, match="Mirror not initialized"):
            dispatcher.dispatch_task(task_id)

        task = queue.get_task(task_id)
        assert task.status == "failed"

    def test_cleanup_after_failure(
        self,
        queue: WorkQueue,
        config: OverlordConfig,
        mirrors: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Task is unlocked even after provision failure."""
        mirrors.provision_worktree.side_effect = RuntimeError("fail")

        d = Dispatcher(queue, config, mirrors, {"claude": FakeWorker(name="claude")})
        task_id = _create_active_task(queue)

        with pytest.raises(RuntimeError):
            d.dispatch_task(task_id)

        task = queue.get_task(task_id)
        assert task.locked_by is None

    def test_worktree_path_in_context(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        mirrors: MagicMock,
        tmp_path: Path,
        claude_worker: FakeWorker,
    ) -> None:
        """Worker receives the worktree path as project_path."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id, skip_review=True)

        assert len(claude_worker.execute_calls) == 1
        assert claude_worker.execute_calls[0]["project_path"] == wt


# --- TestReview ---


class TestReview:
    """Tests for the review step."""

    def test_review_invoked_with_different_worker(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
        claude_worker: FakeWorker,
        gemini_worker: FakeWorker,
    ) -> None:
        """Review uses a different worker than executor when possible."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        # Claude executes, Gemini reviews
        assert len(claude_worker.execute_calls) == 1
        assert len(gemini_worker.execute_calls) == 1

    def test_review_failure_keeps_task_failed(
        self,
        queue: WorkQueue,
        config: OverlordConfig,
        mirrors: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Review failure transitions task to failed."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        exec_worker = FakeWorker(name="claude")
        review_worker = FakeWorker(
            name="gemini",
            result=WorkerResult(
                success=False,
                error="review issues",
                worker_type="gemini",
            ),
        )
        d = Dispatcher(
            queue,
            config,
            mirrors,
            {"claude": exec_worker, "gemini": review_worker},
        )

        task_id = _create_active_task(queue)
        result = d.dispatch_task(task_id)

        task = queue.get_task(task_id)
        assert task.status == "failed"
        assert result.review_status == "failed"

    def test_review_pass_completes_task(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """Successful review transitions task to completed."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        task = queue.get_task(task_id)
        assert task.status == "completed"

    def test_review_prompt_contains_exec_output(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
        gemini_worker: FakeWorker,
    ) -> None:
        """Review prompt includes the execution output."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        review_prompt = gemini_worker.execute_calls[0]["prompt"]
        # The execution worker returns "done" as output
        assert "done" in review_prompt


# --- TestErrorHandling ---


class TestErrorHandling:
    """Tests for error handling."""

    def test_task_not_found(self, dispatcher: Dispatcher) -> None:
        """ValueError raised for nonexistent task."""
        with pytest.raises(ValueError, match="Task not found"):
            dispatcher.dispatch_task("nonexistent-id")

    def test_task_not_active(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
    ) -> None:
        """ValueError raised when task is not in active status."""
        task_id = queue.add_task(title="Test", project="nebulus-core")
        # task is in backlog, not active
        with pytest.raises(ValueError, match="expected 'active'"):
            dispatcher.dispatch_task(task_id)

    def test_no_eligible_workers(
        self,
        queue: WorkQueue,
        config: OverlordConfig,
        mirrors: MagicMock,
    ) -> None:
        """RuntimeError raised when no workers are available."""
        d = Dispatcher(queue, config, mirrors, {})
        task_id = _create_active_task(queue)

        with pytest.raises(RuntimeError, match="No eligible workers"):
            d.dispatch_task(task_id)

    def test_provision_failure(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        mirrors: MagicMock,
    ) -> None:
        """Provision failure results in failed task."""
        mirrors.provision_worktree.side_effect = RuntimeError("git error")
        task_id = _create_active_task(queue)

        with pytest.raises(RuntimeError):
            dispatcher.dispatch_task(task_id)

        task = queue.get_task(task_id)
        assert task.status == "failed"
        assert task.locked_by is None

    def test_unknown_project(
        self,
        queue: WorkQueue,
        config: OverlordConfig,
        mirrors: MagicMock,
    ) -> None:
        """ValueError raised for task with unknown project."""
        d = Dispatcher(queue, config, mirrors, {"claude": FakeWorker(name="claude")})
        task_id = queue.add_task(title="Test", project="unknown-project")
        queue.transition(task_id, "active", changed_by="test")

        with pytest.raises(ValueError, match="Unknown project"):
            d.dispatch_task(task_id)


# --- TestIntegration ---


class TestIntegration:
    """End-to-end integration tests with mocked workers."""

    def test_end_to_end_with_mocked_workers(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """Full end-to-end dispatch with brief generation and review."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(
            queue,
            title="Add authentication module",
            description="Implement OAuth2 flow",
        )
        result = dispatcher.dispatch_task(task_id)

        # Verify complete lifecycle
        assert result.task_id == task_id
        assert result.worker_id == "claude"
        assert result.review_status == "passed"

        task = queue.get_task(task_id)
        assert task.status == "completed"
        assert task.locked_by is None

        # Brief was generated
        brief = (wt / BRIEF_FILENAME).read_text()
        assert "OAuth2 flow" in brief
        assert "authentication" in brief

    def test_dry_run_e2e(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
        claude_worker: FakeWorker,
        gemini_worker: FakeWorker,
    ) -> None:
        """Dry-run e2e: brief generated, no execution, no review."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue, title="Refactor config")
        result = dispatcher.dispatch_task(task_id, dry_run=True)

        assert result.output_log == "dry-run"
        assert result.review_status == "skipped"
        assert len(claude_worker.execute_calls) == 0
        assert len(gemini_worker.execute_calls) == 0

        # Brief still written
        assert (wt / BRIEF_FILENAME).exists()

    def test_dispatch_result_recorded_in_queue(
        self,
        dispatcher: Dispatcher,
        queue: WorkQueue,
        tmp_path: Path,
        mirrors: MagicMock,
    ) -> None:
        """Dispatch result is persisted in the queue database."""
        wt = tmp_path / "worktree"
        wt.mkdir()
        mirrors.provision_worktree.return_value = wt

        task_id = _create_active_task(queue)
        dispatcher.dispatch_task(task_id)

        records = queue.get_dispatch_results(task_id)
        assert len(records) == 1
        rec = records[0]
        assert rec.task_id == task_id
        assert rec.worker_id == "claude"
        assert rec.branch_name.startswith("atom/")
        assert rec.mission_brief_path != ""
