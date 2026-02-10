"""Tests for the Governance Engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from nebulus_swarm.overlord.governance import (
    GovernanceEngine,
    GovernanceResult,
    GovernanceViolation,
    _extract_file_patterns,
)
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.work_queue import Task, WorkQueue


# --- Fixtures ---


def _make_task(
    title: str = "Add feature",
    project: str = "nebulus-core",
    description: str | None = None,
    task_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
    status: str = "active",
) -> Task:
    return Task(
        id=task_id,
        title=title,
        project=project,
        description=description,
        status=status,
    )


def _make_project_config(
    name: str = "nebulus-core",
    path: str = "/tmp/test-project",
    branch_model: str = "develop-main",
) -> ProjectConfig:
    return ProjectConfig(
        name=name,
        path=path,
        remote="git@github.com:test/test.git",
        role="core",
        branch_model=branch_model,
    )


def _make_engine(
    workspace_root: str = "/tmp/workspace",
    dispatched_tasks: list[Task] | None = None,
) -> GovernanceEngine:
    config = MagicMock(spec=OverlordConfig)
    config.workspace_root = Path(workspace_root)

    queue = MagicMock(spec=WorkQueue)
    queue.list_tasks.return_value = dispatched_tasks or []

    return GovernanceEngine(config, queue, workspace_root=Path(workspace_root))


# --- GovernanceResult / GovernanceViolation ---


def test_governance_result_approved():
    result = GovernanceResult(approved=True, violations=[])
    assert result.approved is True
    assert result.violations == []


def test_governance_violation_fields():
    v = GovernanceViolation(
        rule="test-rule",
        severity="hard-block",
        message="blocked",
        project="test-project",
    )
    assert v.rule == "test-rule"
    assert v.severity == "hard-block"


# --- Root workspace check ---


def test_root_workspace_blocked(tmp_path):
    """Dispatch to workspace root should be hard-blocked."""
    engine = _make_engine(workspace_root=str(tmp_path))
    pc = _make_project_config(path=str(tmp_path))

    violation = engine._check_root_workspace(pc)
    assert violation is not None
    assert violation.rule == "root-workspace"
    assert violation.severity == "hard-block"


def test_root_workspace_allowed(tmp_path):
    """Dispatch to a sub-project should be allowed."""
    project_dir = tmp_path / "nebulus-core"
    project_dir.mkdir()
    engine = _make_engine(workspace_root=str(tmp_path))
    pc = _make_project_config(path=str(project_dir))

    violation = engine._check_root_workspace(pc)
    assert violation is None


# --- Concurrency check ---


def test_concurrency_blocked():
    """Same project with dispatched task should be hard-blocked."""
    existing = _make_task(
        task_id="bbbbbbbb-0000-0000-0000-000000000002",
        title="Other task",
        project="nebulus-core",
        status="dispatched",
    )
    engine = _make_engine(dispatched_tasks=[existing])
    task = _make_task()

    violation = engine._check_concurrency(task)
    assert violation is not None
    assert violation.rule == "concurrency"
    assert violation.severity == "hard-block"


def test_concurrency_allowed_different_project():
    """Different project with dispatched task should be allowed."""
    existing = _make_task(
        task_id="bbbbbbbb-0000-0000-0000-000000000002",
        title="Other task",
        project="nebulus-edge",
        status="dispatched",
    )
    engine = _make_engine(dispatched_tasks=[existing])
    task = _make_task(project="nebulus-core")

    violation = engine._check_concurrency(task)
    assert violation is None


def test_concurrency_allowed_same_task():
    """Same task should not conflict with itself."""
    task = _make_task()
    engine = _make_engine(dispatched_tasks=[task])

    violation = engine._check_concurrency(task)
    assert violation is None


# --- Branch policy check ---


@patch("subprocess.run")
def test_branch_policy_valid(mock_run):
    """Valid branch name should pass."""
    mock_run.return_value = MagicMock(stdout="feat/add-widget\n")
    engine = _make_engine()
    pc = _make_project_config(branch_model="develop-main")

    violation = engine._check_branch_policy(pc)
    assert violation is None


@patch("subprocess.run")
def test_branch_policy_invalid(mock_run):
    """Invalid branch name should warn."""
    mock_run.return_value = MagicMock(stdout="random-branch\n")
    engine = _make_engine()
    pc = _make_project_config(branch_model="develop-main")

    violation = engine._check_branch_policy(pc)
    assert violation is not None
    assert violation.rule == "branch-policy"
    assert violation.severity == "warning"
    assert "random-branch" in violation.message


@patch("subprocess.run")
def test_branch_policy_develop_ok(mock_run):
    """develop branch should pass."""
    mock_run.return_value = MagicMock(stdout="develop\n")
    engine = _make_engine()
    pc = _make_project_config(branch_model="develop-main")

    violation = engine._check_branch_policy(pc)
    assert violation is None


def test_branch_policy_skipped_for_other_models():
    """Non develop-main branch models should skip check."""
    engine = _make_engine()
    pc = _make_project_config(branch_model="trunk")

    violation = engine._check_branch_policy(pc)
    assert violation is None


# --- Strategic drift ---


def test_strategic_drift_flagged():
    """Task not matching keywords should produce a warning."""
    engine = _make_engine()
    engine.set_priority_keywords(["security", "performance"])
    task = _make_task(title="Add color theme", description="UI polish work")

    violation = engine._check_strategic_drift(task)
    assert violation is not None
    assert violation.rule == "strategic-drift"
    assert violation.severity == "warning"


def test_strategic_drift_matched():
    """Task matching keywords should pass."""
    engine = _make_engine()
    engine.set_priority_keywords(["security", "performance"])
    task = _make_task(
        title="Harden API security",
        description="Add auth headers",
    )

    violation = engine._check_strategic_drift(task)
    assert violation is None


def test_strategic_drift_no_keywords():
    """No keywords configured should skip check."""
    engine = _make_engine()
    task = _make_task(title="Random work")

    violation = engine._check_strategic_drift(task)
    assert violation is None


# --- pre_dispatch_check ---


@patch("subprocess.run")
def test_pre_dispatch_check_approved(mock_run):
    """Clean task should be approved."""
    mock_run.return_value = MagicMock(stdout="feat/new-feature\n")
    engine = _make_engine()
    task = _make_task()
    pc = _make_project_config()

    result = engine.pre_dispatch_check(task, pc)
    assert result.approved is True
    assert len(result.violations) == 0


def test_pre_dispatch_check_blocked_by_root_workspace(tmp_path):
    """Root workspace violation should block dispatch."""
    engine = _make_engine(workspace_root=str(tmp_path))
    task = _make_task()
    pc = _make_project_config(path=str(tmp_path))

    result = engine.pre_dispatch_check(task, pc)
    assert result.approved is False
    assert any(v.rule == "root-workspace" for v in result.violations)


# --- Conflict detection ---


def test_check_conflict_overlap():
    """Overlapping file paths should trigger conflict."""
    engine = _make_engine()
    task = _make_task(description="Modify nebulus_swarm/overlord/dispatcher.py")
    active = _make_task(
        task_id="cccccccc-0000-0000-0000-000000000003",
        title="Refactor dispatcher",
        description="Update nebulus_swarm/overlord/dispatcher.py",
    )

    violation = engine.check_conflict(task, [active])
    assert violation is not None
    assert violation.rule == "conflict"
    assert violation.severity == "hard-block"


def test_check_conflict_no_overlap():
    """Non-overlapping paths should not conflict."""
    engine = _make_engine()
    task = _make_task(description="Modify nebulus_swarm/overlord/focus.py")
    active = _make_task(
        task_id="cccccccc-0000-0000-0000-000000000003",
        title="Update governance",
        description="Modify nebulus_swarm/overlord/governance.py",
    )

    violation = engine.check_conflict(task, [active])
    assert violation is None


def test_check_conflict_no_description():
    """Task without description should not conflict."""
    engine = _make_engine()
    task = _make_task(description=None)
    active = _make_task(
        task_id="cccccccc-0000-0000-0000-000000000003",
        description="Modify some/file.py",
    )

    violation = engine.check_conflict(task, [active])
    assert violation is None


def test_check_conflict_skip_self():
    """Task should not conflict with itself."""
    engine = _make_engine()
    task = _make_task(description="Modify some/file.py")

    violation = engine.check_conflict(task, [task])
    assert violation is None


# --- _extract_file_patterns ---


def test_extract_file_patterns_py():
    patterns = _extract_file_patterns("Update foo/bar.py and baz/qux.py")
    assert "foo/bar.py" in patterns
    assert "baz/qux.py" in patterns


def test_extract_file_patterns_module():
    patterns = _extract_file_patterns("Check nebulus_swarm/overlord")
    assert "nebulus_swarm/overlord" in patterns


def test_extract_file_patterns_empty():
    patterns = _extract_file_patterns("No file paths here")
    assert len(patterns) == 0
