"""Integration tests for Track 5: Atom Focus & PM Mode.

Validates acceptance criteria end-to-end with mocked workers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from nebulus_swarm.overlord.dispatcher import DispatchContext, Dispatcher
from nebulus_swarm.overlord.focus import build_focus_context
from nebulus_swarm.overlord.governance import (
    GovernanceEngine,
)
from nebulus_swarm.overlord.mission_brief import generate_mission_brief
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.work_queue import Task, WorkQueue
from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerConfig, WorkerResult


# --- Test helpers ---


class FakeWorker(BaseWorker):
    worker_type: str = "fake"

    def __init__(self, name: str = "fake", result: WorkerResult | None = None):
        super().__init__(WorkerConfig(enabled=True))
        self.worker_type = name
        self._result = result or WorkerResult(
            success=True, output="done", model_used="test", worker_type=name
        )

    @property
    def available(self) -> bool:
        return True

    def execute(self, prompt, project_path, task_type="feature", model=None):
        return self._result


def _make_task(**kwargs) -> Task:
    defaults = {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "title": "Test task",
        "project": "nebulus-core",
        "status": "active",
    }
    defaults.update(kwargs)
    return Task(**defaults)


def _make_project_config(**kwargs) -> ProjectConfig:
    defaults = {
        "name": "nebulus-core",
        "path": "/tmp/test-project",
        "remote": "git@github.com:test/test.git",
        "role": "core",
        "branch_model": "develop-main",
    }
    defaults.update(kwargs)
    return ProjectConfig(**defaults)


# --- AC1: Focus context returns synthesized content ---


def test_focus_context_synthesizes_business(tmp_path):
    """Focus context should parse BUSINESS.md into structured data."""
    (tmp_path / "BUSINESS.md").write_text(
        "# Business\n\n"
        "## Priorities\n\n"
        "| Name | Priority | Description |\n"
        "|------|----------|-------------|\n"
        "| Security | High | Harden APIs |\n"
    )
    ctx = build_focus_context(tmp_path)
    prompt = ctx.format_for_prompt()

    assert "Security" in prompt
    assert "Harden APIs" in prompt


# --- AC2: PM mode deprioritizes code generation ---


def test_pm_brief_contains_strategic_prompt(tmp_path):
    """PM mode mission brief should contain PM-specific directives."""
    ctx = DispatchContext(
        task=_make_task(),
        project_config=_make_project_config(),
        worker=FakeWorker(),
        worktree_path=tmp_path,
        role="pm",
    )
    brief_path = generate_mission_brief(ctx)
    content = brief_path.read_text()

    assert "Deprioritize: code generation" in content
    assert "sequencing" in content


# --- AC3: Root workspace dispatch blocked ---


def test_root_workspace_dispatch_blocked(tmp_path):
    """Governance should block dispatch to workspace root."""
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = tmp_path
    queue = MagicMock(spec=WorkQueue)
    queue.list_tasks.return_value = []

    engine = GovernanceEngine(config, queue, workspace_root=tmp_path)
    pc = _make_project_config(path=str(tmp_path))
    task = _make_task()

    result = engine.pre_dispatch_check(task, pc)
    assert result.approved is False
    assert any(v.rule == "root-workspace" for v in result.violations)


# --- AC4: Concurrent dispatch to same project blocked ---


def test_concurrent_dispatch_blocked():
    """Governance should block concurrent dispatch to same project."""
    existing = _make_task(
        id="bbbbbbbb-0000-0000-0000-000000000002", status="dispatched"
    )
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = Path("/tmp/workspace")
    queue = MagicMock(spec=WorkQueue)
    queue.list_tasks.return_value = [existing]

    engine = GovernanceEngine(config, queue)
    pc = _make_project_config()
    task = _make_task()

    result = engine.pre_dispatch_check(task, pc)
    assert result.approved is False
    assert any(v.rule == "concurrency" for v in result.violations)


# --- AC5: Branch policy violation detected ---


@patch("subprocess.run")
def test_branch_policy_violation_detected(mock_run):
    """Governance should warn on non-standard branch names."""
    mock_run.return_value = MagicMock(stdout="wip-random\n")
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = Path("/tmp/workspace")
    queue = MagicMock(spec=WorkQueue)
    queue.list_tasks.return_value = []

    engine = GovernanceEngine(config, queue)
    pc = _make_project_config(path="/tmp/test-other")
    task = _make_task()

    result = engine.pre_dispatch_check(task, pc)
    # Branch policy is a warning, not a hard-block
    assert result.approved is True
    assert any(v.rule == "branch-policy" for v in result.violations)


# --- AC6: Strategic drift flagged ---


def test_strategic_drift_flagged():
    """Tasks not matching priority keywords should be flagged."""
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = Path("/tmp/workspace")
    queue = MagicMock(spec=WorkQueue)
    queue.list_tasks.return_value = []

    engine = GovernanceEngine(config, queue)
    engine.set_priority_keywords(["security", "performance"])

    pc = _make_project_config(path="/tmp/test-other")
    task = _make_task(title="Add color theme", description="UI polish work")

    result = engine.pre_dispatch_check(task, pc)
    assert result.approved is True  # warning, not block
    assert any(v.rule == "strategic-drift" for v in result.violations)


# --- AC7: Conflict escalation ---


def test_conflict_escalation_blocks():
    """File conflict between tasks should produce hard-block."""
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = Path("/tmp/workspace")
    queue = MagicMock(spec=WorkQueue)

    engine = GovernanceEngine(config, queue)
    task = _make_task(description="Modify nebulus_swarm/overlord/dispatcher.py")
    active = _make_task(
        id="cccccccc-0000-0000-0000-000000000003",
        title="Refactor dispatcher",
        description="Update nebulus_swarm/overlord/dispatcher.py",
    )

    conflict = engine.check_conflict(task, [active])
    assert conflict is not None
    assert conflict.severity == "hard-block"


# --- AC8: Pre-dispatch scan blocks unhealthy repo ---


def test_pre_dispatch_scan_blocks_unhealthy(tmp_path):
    """Dispatcher should block dispatch to unhealthy repos."""
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = Path("/tmp/workspace")
    config.projects = {"nebulus-core": _make_project_config()}
    config.cost_controls = MagicMock(daily_ceiling_usd=10.0, warning_threshold_pct=80.0)

    queue = MagicMock(spec=WorkQueue)
    task = _make_task()
    queue.get_task.return_value = task
    queue.list_tasks.return_value = []

    worker = FakeWorker(name="claude")
    mirrors = MagicMock()
    mirrors.provision_worktree.return_value = tmp_path

    dispatcher = Dispatcher(
        queue, config, mirrors, {"claude": worker}, daily_ceiling_usd=10.0
    )

    # Mock the private method directly since scanner import is internal
    issues = ["3 tests failing", "uncommitted changes"]
    with patch.object(dispatcher, "_run_pre_dispatch_scan", return_value=issues):
        dispatcher.dispatch_task(task.id, dry_run=False, skip_review=True)

    # Should have failed due to unhealthy repo — check transition to "failed" was called
    fail_calls = [
        c
        for c in queue.transition.call_args_list
        if len(c.args) >= 2 and c.args[1] == "failed"
    ]
    assert len(fail_calls) >= 1
    assert (
        "unhealthy"
        in fail_calls[-1]
        .kwargs.get(
            "reason", fail_calls[-1].args[3] if len(fail_calls[-1].args) > 3 else ""
        )
        .lower()
        or "unhealthy" in str(fail_calls[-1]).lower()
    )


# --- AC9: nebulus-core downstream impact logged ---


def test_downstream_impact_logged(tmp_path):
    """Dispatching nebulus-core changes should log downstream projects."""
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = tmp_path
    config.projects = {"nebulus-core": _make_project_config()}

    queue = MagicMock(spec=WorkQueue)
    mirrors = MagicMock()
    worker = FakeWorker(name="claude")

    dispatcher = Dispatcher(
        queue, config, mirrors, {"claude": worker}, daily_ceiling_usd=10.0
    )

    task = _make_task(project="nebulus-core")

    with patch.object(dispatcher, "_log_downstream_impact") as mock_log:
        queue.get_task.return_value = task
        queue.list_tasks.return_value = []
        mirrors.provision_worktree.return_value = tmp_path
        queue.check_budget_available.return_value = (True, 0.0)

        with patch.object(dispatcher, "_run_pre_dispatch_scan", return_value=[]):
            try:
                dispatcher.dispatch_task(task.id, skip_review=True)
            except Exception:
                pass  # May fail on later steps, we just need to verify log call

        mock_log.assert_called_once_with(task)


# --- AC10: Halt command integration ---


@patch("nebulus_atom.commands.overlord_commands._load_queue_for_halt")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.check_running")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.stop_daemon")
def test_halt_full_integration(mock_stop, mock_running, mock_queue):
    """Halt should cancel dispatched tasks and stop daemon."""
    from typer.testing import CliRunner
    from nebulus_atom.commands.overlord_commands import overlord_app

    runner = CliRunner()

    dispatched = _make_task(status="dispatched")
    active_locked = _make_task(
        id="dddddddd-0000-0000-0000-000000000004",
        status="active",
        locked_by="claude",
    )

    queue = MagicMock()
    queue.list_tasks.side_effect = lambda status: {
        "dispatched": [dispatched],
        "active": [active_locked],
    }.get(status, [])
    mock_queue.return_value = queue
    mock_running.return_value = True
    mock_stop.return_value = True

    result = runner.invoke(overlord_app, ["halt"])

    assert result.exit_code == 0
    assert "2 task(s) cancelled" in result.output
    assert "Daemon stopped" in result.output
    assert queue.transition.call_count == 2


# --- Full pipeline: focus → governance → dispatch ---


def test_full_pm_pipeline(tmp_path):
    """Full pipeline: build context → governance check → generate brief."""
    # Create workspace files
    (tmp_path / "BUSINESS.md").write_text(
        "# Business\n\n"
        "## Priorities\n\n"
        "| Name | Priority | Description |\n"
        "|------|----------|-------------|\n"
        "| Security | High | Harden APIs |\n\n"
        "## Governance\n"
        "- All changes need review\n"
    )
    plans_dir = tmp_path / "docs" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-02-10-track5.md").write_text(
        "# Track 5 PM Mode\nImplement PM-aware dispatch.\n"
    )

    # Build context
    ctx = build_focus_context(tmp_path)
    assert len(ctx.business_priorities) >= 1
    assert len(ctx.governance_rules) >= 1

    # Format for prompt
    prompt = ctx.format_for_prompt()
    assert "Security" in prompt
    assert "All changes need review" in prompt

    # Governance check
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = tmp_path
    queue = MagicMock(spec=WorkQueue)
    queue.list_tasks.return_value = []

    engine = GovernanceEngine(config, queue, workspace_root=tmp_path)
    engine.set_priority_keywords(["security"])

    sub_project = tmp_path / "nebulus-core"
    sub_project.mkdir()
    pc = _make_project_config(path=str(sub_project), branch_model="trunk")
    task = _make_task(title="Harden API security", description="Add auth headers")

    gov_result = engine.pre_dispatch_check(task, pc)
    assert gov_result.approved is True

    # Generate PM brief
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    dispatch_ctx = DispatchContext(
        task=task,
        project_config=pc,
        worker=FakeWorker(),
        worktree_path=worktree,
        role="pm",
        focus_context=prompt,
    )
    brief_path = generate_mission_brief(dispatch_ctx)
    brief_content = brief_path.read_text()

    assert "Project Manager" in brief_content
    assert "Ecosystem Context" in brief_content
    assert "Security" in brief_content
