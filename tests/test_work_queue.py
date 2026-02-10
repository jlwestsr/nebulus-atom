"""Tests for the work queue module."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nebulus_swarm.overlord.work_queue import (
    DispatchResultRecord,
    TRANSITIONS,
    WorkQueue,
)


@pytest.fixture
def queue(tmp_path: Path) -> WorkQueue:
    """Create a work queue with a temp database."""
    return WorkQueue(db_path=tmp_path / "test_queue.db")


def _add_sample_task(queue: WorkQueue, **kwargs) -> str:
    """Helper to add a task with sensible defaults."""
    defaults = {"title": "Test task", "project": "nebulus-core"}
    defaults.update(kwargs)
    return queue.add_task(**defaults)


class TestSchema:
    """Tests for schema constraints."""

    def test_status_check_constraint(self, queue: WorkQueue) -> None:
        """Invalid status rejected by CHECK constraint."""
        task_id = _add_sample_task(queue)
        with pytest.raises(sqlite3.IntegrityError):
            with queue._get_connection() as conn:
                conn.execute(
                    "UPDATE tasks SET status = 'invalid' WHERE id = ?",
                    (task_id,),
                )

    def test_priority_check_constraint(self, queue: WorkQueue) -> None:
        """Invalid priority rejected by CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            with queue._get_connection() as conn:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO tasks (id, project, title, status, priority, "
                    "complexity, retry_count, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'backlog', 'invalid', 'medium', 0, ?, ?)",
                    ("test-id", "proj", "title", now, now),
                )

    def test_unique_external_id_source(self, queue: WorkQueue) -> None:
        """UNIQUE constraint on (external_id, external_source)."""
        _add_sample_task(queue, external_id="42", external_source="github:org/repo")
        with pytest.raises(sqlite3.IntegrityError):
            _add_sample_task(queue, external_id="42", external_source="github:org/repo")

    def test_self_dependency_check(self, queue: WorkQueue) -> None:
        """CHECK constraint prevents self-dependency."""
        task_id = _add_sample_task(queue)
        with pytest.raises((sqlite3.IntegrityError, ValueError)):
            queue.add_dependency(task_id, task_id)

    def test_fk_cascade_on_delete(self, queue: WorkQueue) -> None:
        """FK CASCADE deletes dependent rows when task is deleted."""
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "active", "test")

        with queue._get_connection() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            logs = conn.execute(
                "SELECT * FROM task_log WHERE task_id = ?", (task_id,)
            ).fetchall()
            assert len(logs) == 0

    def test_null_external_id_allowed(self, queue: WorkQueue) -> None:
        """Tasks without external_id are valid."""
        task_id = _add_sample_task(queue)
        task = queue.get_task(task_id)
        assert task is not None
        assert task.external_id is None


class TestAddAndGet:
    """Tests for add_task and get_task."""

    def test_add_returns_uuid(self, queue: WorkQueue) -> None:
        """add_task returns a valid UUID."""
        task_id = _add_sample_task(queue)
        assert len(task_id) == 36  # UUID format

    def test_get_returns_task(self, queue: WorkQueue) -> None:
        """get_task returns a Task dataclass."""
        task_id = _add_sample_task(queue, title="My task", project="nebulus-atom")
        task = queue.get_task(task_id)
        assert task is not None
        assert task.title == "My task"
        assert task.project == "nebulus-atom"
        assert task.status == "backlog"

    def test_get_nonexistent_returns_none(self, queue: WorkQueue) -> None:
        """get_task returns None for missing ID."""
        assert queue.get_task("nonexistent-id") is None

    def test_list_all(self, queue: WorkQueue) -> None:
        """list_tasks returns all tasks."""
        _add_sample_task(queue, title="Task 1")
        _add_sample_task(queue, title="Task 2")
        tasks = queue.list_tasks()
        assert len(tasks) == 2

    def test_list_with_filters(self, queue: WorkQueue) -> None:
        """list_tasks filters by status and project."""
        t1 = _add_sample_task(queue, project="core")
        _add_sample_task(queue, project="edge")
        queue.transition(t1, "active", "test")

        active = queue.list_tasks(status="active")
        assert len(active) == 1
        assert active[0].id == t1

        core = queue.list_tasks(project="core")
        assert len(core) == 1

        edge_backlog = queue.list_tasks(status="backlog", project="edge")
        assert len(edge_backlog) == 1


class TestStateMachine:
    """Tests for state machine transitions."""

    def test_backlog_to_active(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        task = queue.transition(task_id, "active", "user")
        assert task.status == "active"

    def test_active_to_dispatched(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "active", "user")
        task = queue.transition(task_id, "dispatched", "dispatch-engine")
        assert task.status == "dispatched"

    def test_dispatched_to_in_review(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "active", "user")
        queue.transition(task_id, "dispatched", "engine")
        task = queue.transition(task_id, "in_review", "engine")
        assert task.status == "in_review"

    def test_in_review_to_completed(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "active", "user")
        queue.transition(task_id, "dispatched", "engine")
        queue.transition(task_id, "in_review", "engine")
        task = queue.transition(task_id, "completed", "reviewer")
        assert task.status == "completed"

    def test_in_review_to_active_rework(self, queue: WorkQueue) -> None:
        """Rework: in_review -> active is valid."""
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "active", "user")
        queue.transition(task_id, "dispatched", "engine")
        queue.transition(task_id, "in_review", "engine")
        task = queue.transition(task_id, "active", "reviewer", reason="needs rework")
        assert task.status == "active"

    def test_failed_to_backlog_retry(self, queue: WorkQueue) -> None:
        """Retry: failed -> backlog increments retry_count."""
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "failed", "system")
        task = queue.transition(task_id, "backlog", "user", reason="retry")
        assert task.status == "backlog"
        assert task.retry_count == 1

    def test_completed_is_terminal(self, queue: WorkQueue) -> None:
        """Completed tasks cannot transition anywhere."""
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "active", "user")
        queue.transition(task_id, "dispatched", "engine")
        queue.transition(task_id, "in_review", "engine")
        queue.transition(task_id, "completed", "reviewer")

        with pytest.raises(ValueError, match="Invalid transition"):
            queue.transition(task_id, "backlog", "user")

    def test_invalid_transition_raises(self, queue: WorkQueue) -> None:
        """Invalid transitions raise ValueError."""
        task_id = _add_sample_task(queue)
        with pytest.raises(ValueError, match="Invalid transition"):
            queue.transition(task_id, "completed", "user")

    def test_transition_nonexistent_raises(self, queue: WorkQueue) -> None:
        """Transitioning a nonexistent task raises ValueError."""
        with pytest.raises(ValueError, match="Task not found"):
            queue.transition("nonexistent", "active", "user")

    def test_all_valid_transitions_covered(self) -> None:
        """Verify TRANSITIONS dict covers all statuses."""
        from nebulus_swarm.overlord.work_queue import VALID_STATUSES

        assert set(TRANSITIONS.keys()) == VALID_STATUSES


class TestLocking:
    """Tests for task locking."""

    def test_lock_task(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        task = queue.lock_task(task_id, "worker-1")
        assert task.locked_by == "worker-1"
        assert task.locked_at is not None

    def test_unlock_task(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        queue.lock_task(task_id, "worker-1")
        queue.unlock_task(task_id)
        task = queue.get_task(task_id)
        assert task.locked_by is None
        assert task.locked_at is None

    def test_double_lock_raises(self, queue: WorkQueue) -> None:
        """Locking an already-locked task raises ValueError."""
        task_id = _add_sample_task(queue)
        queue.lock_task(task_id, "worker-1")
        with pytest.raises(ValueError, match="already locked"):
            queue.lock_task(task_id, "worker-2")

    def test_lock_nonexistent_raises(self, queue: WorkQueue) -> None:
        with pytest.raises(ValueError, match="Task not found"):
            queue.lock_task("nonexistent", "worker-1")

    def test_reclaim_stale_locks(self, queue: WorkQueue) -> None:
        """Stale locks are reclaimed after timeout."""
        task_id = _add_sample_task(queue)
        queue.lock_task(task_id, "worker-1")

        # Backdate the lock
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        with queue._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET locked_at = ? WHERE id = ?",
                (old_ts, task_id),
            )

        reclaimed = queue.reclaim_stale_locks(timeout_minutes=30)
        assert task_id in reclaimed

        task = queue.get_task(task_id)
        assert task.locked_by is None

    def test_fresh_lock_not_reclaimed(self, queue: WorkQueue) -> None:
        """Recent locks are NOT reclaimed."""
        task_id = _add_sample_task(queue)
        queue.lock_task(task_id, "worker-1")

        reclaimed = queue.reclaim_stale_locks(timeout_minutes=30)
        assert task_id not in reclaimed

        task = queue.get_task(task_id)
        assert task.locked_by == "worker-1"


class TestDependencies:
    """Tests for task dependency management."""

    def test_add_and_get_dependency(self, queue: WorkQueue) -> None:
        t1 = _add_sample_task(queue, title="Dep")
        t2 = _add_sample_task(queue, title="Main")
        queue.add_dependency(t2, t1)

        deps = queue.get_dependencies(t2)
        assert len(deps) == 1
        assert deps[0].id == t1

    def test_self_dependency_raises(self, queue: WorkQueue) -> None:
        t1 = _add_sample_task(queue)
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            queue.add_dependency(t1, t1)

    def test_eligible_excludes_pending_deps(self, queue: WorkQueue) -> None:
        """Tasks with incomplete deps are NOT eligible for dispatch."""
        t1 = _add_sample_task(queue, title="Dep")
        t2 = _add_sample_task(queue, title="Main")
        queue.add_dependency(t2, t1)

        queue.transition(t2, "active", "user")
        eligible = queue.get_eligible_for_dispatch()
        assert all(t.id != t2 for t in eligible)

    def test_eligible_includes_completed_deps(self, queue: WorkQueue) -> None:
        """Tasks with all deps completed ARE eligible."""
        t1 = _add_sample_task(queue, title="Dep")
        t2 = _add_sample_task(queue, title="Main")
        queue.add_dependency(t2, t1)

        # Complete the dependency
        queue.transition(t1, "active", "user")
        queue.transition(t1, "dispatched", "engine")
        queue.transition(t1, "in_review", "engine")
        queue.transition(t1, "completed", "reviewer")

        # Activate the main task
        queue.transition(t2, "active", "user")

        eligible = queue.get_eligible_for_dispatch()
        assert any(t.id == t2 for t in eligible)

    def test_eligible_excludes_locked(self, queue: WorkQueue) -> None:
        """Locked tasks are NOT eligible for dispatch."""
        t1 = _add_sample_task(queue)
        queue.transition(t1, "active", "user")
        queue.lock_task(t1, "worker-1")

        eligible = queue.get_eligible_for_dispatch()
        assert all(t.id != t1 for t in eligible)

    def test_eligible_project_filter(self, queue: WorkQueue) -> None:
        """Project filter on get_eligible_for_dispatch works."""
        t1 = _add_sample_task(queue, project="core")
        t2 = _add_sample_task(queue, project="edge")
        queue.transition(t1, "active", "user")
        queue.transition(t2, "active", "user")

        core_eligible = queue.get_eligible_for_dispatch(project="core")
        assert len(core_eligible) == 1
        assert core_eligible[0].id == t1


class TestDispatchResults:
    """Tests for dispatch result recording."""

    def test_record_and_retrieve(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        result = DispatchResultRecord(
            task_id=task_id,
            worker_id="claude-code",
            model_id="opus",
            branch_name="feat/test",
            review_status="pending",
            usage_stats={"tokens": 1500},
            output_log="Done.",
        )
        rid = queue.record_dispatch_result(result)
        assert rid > 0

        results = queue.get_dispatch_results(task_id)
        assert len(results) == 1
        assert results[0].worker_id == "claude-code"

    def test_json_roundtrip(self, queue: WorkQueue) -> None:
        """usage_stats survives JSON serialization."""
        task_id = _add_sample_task(queue)
        stats = {"input_tokens": 500, "output_tokens": 1000, "model": "opus"}
        result = DispatchResultRecord(
            task_id=task_id,
            worker_id="w1",
            usage_stats=stats,
        )
        queue.record_dispatch_result(result)

        results = queue.get_dispatch_results(task_id)
        assert results[0].usage_stats == stats

    def test_multiple_results_per_task(self, queue: WorkQueue) -> None:
        """Multiple dispatch results can exist for one task."""
        task_id = _add_sample_task(queue)
        for i in range(3):
            queue.record_dispatch_result(
                DispatchResultRecord(task_id=task_id, worker_id=f"w{i}")
            )

        results = queue.get_dispatch_results(task_id)
        assert len(results) == 3


class TestUpsertFromGithub:
    """Tests for GitHub issue sync upsert."""

    def test_new_insert(self, queue: WorkQueue) -> None:
        task_id, is_new = queue.upsert_from_github(
            external_id="42",
            external_source="github:org/repo",
            title="Fix bug",
            project="nebulus-core",
        )
        assert is_new is True
        task = queue.get_task(task_id)
        assert task.title == "Fix bug"
        assert task.status == "backlog"

    def test_update_existing(self, queue: WorkQueue) -> None:
        task_id_1, _ = queue.upsert_from_github(
            external_id="42",
            external_source="github:org/repo",
            title="Fix bug",
            project="nebulus-core",
        )
        task_id_2, is_new = queue.upsert_from_github(
            external_id="42",
            external_source="github:org/repo",
            title="Fix bug (updated)",
            project="nebulus-core",
        )
        assert is_new is False
        assert task_id_1 == task_id_2
        task = queue.get_task(task_id_2)
        assert task.title == "Fix bug (updated)"

    def test_is_new_flag(self, queue: WorkQueue) -> None:
        _, is_new_1 = queue.upsert_from_github("1", "gh:repo", "Task", "proj")
        _, is_new_2 = queue.upsert_from_github("1", "gh:repo", "Task", "proj")
        assert is_new_1 is True
        assert is_new_2 is False

    def test_does_not_overwrite_status(self, queue: WorkQueue) -> None:
        """Upsert should not reset a task's status."""
        task_id, _ = queue.upsert_from_github("99", "gh:repo", "Task", "proj")
        queue.transition(task_id, "active", "user")

        queue.upsert_from_github("99", "gh:repo", "Updated title", "proj")
        task = queue.get_task(task_id)
        assert task.status == "active"
        assert task.title == "Updated title"


class TestTaskLog:
    """Tests for task audit log."""

    def test_transition_records_log(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "active", "user")

        log = queue.get_task_log(task_id)
        assert len(log) == 1
        assert log[0].old_status == "backlog"
        assert log[0].new_status == "active"
        assert log[0].changed_by == "user"

    def test_log_ordered_by_timestamp(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "active", "user")
        queue.transition(task_id, "dispatched", "engine")
        queue.transition(task_id, "in_review", "engine")

        log = queue.get_task_log(task_id)
        assert len(log) == 3
        assert [e.new_status for e in log] == ["active", "dispatched", "in_review"]

    def test_log_includes_reason(self, queue: WorkQueue) -> None:
        task_id = _add_sample_task(queue)
        queue.transition(task_id, "failed", "system", reason="timeout")

        log = queue.get_task_log(task_id)
        assert log[0].reason == "timeout"
