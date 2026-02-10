"""Tests for PM role in dispatcher and mission brief."""

from __future__ import annotations

from pathlib import Path


from nebulus_swarm.overlord.dispatcher import DispatchContext
from nebulus_swarm.overlord.mission_brief import (
    _PM_ROLE_SECTION,
    generate_mission_brief,
)
from nebulus_swarm.overlord.registry import ProjectConfig
from nebulus_swarm.overlord.work_queue import Task
from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerConfig, WorkerResult


# --- Fixtures ---


class FakeWorker(BaseWorker):
    worker_type: str = "fake"

    def __init__(self) -> None:
        super().__init__(WorkerConfig(enabled=True))

    @property
    def available(self) -> bool:
        return True

    def execute(self, prompt, project_path, task_type="feature", model=None):
        return WorkerResult(
            success=True, output="done", model_used="fake", worker_type="fake"
        )


def _make_ctx(
    role: str | None = None,
    focus_context: str | None = None,
    worktree_path: Path | None = None,
) -> DispatchContext:
    task = Task(
        id="aaaaaaaa-0000-0000-0000-000000000001",
        title="Test task",
        project="nebulus-core",
        status="dispatched",
    )
    pc = ProjectConfig(
        name="nebulus-core",
        path="/tmp/test",
        remote="git@github.com:test/test.git",
        role="core",
    )
    return DispatchContext(
        task=task,
        project_config=pc,
        worker=FakeWorker(),
        worktree_path=worktree_path,
        role=role,
        focus_context=focus_context,
    )


# --- DispatchContext fields ---


def test_dispatch_context_role_field():
    ctx = _make_ctx(role="pm")
    assert ctx.role == "pm"


def test_dispatch_context_focus_context_field():
    ctx = _make_ctx(focus_context="# Context\nStuff here")
    assert ctx.focus_context == "# Context\nStuff here"


def test_dispatch_context_defaults():
    ctx = _make_ctx()
    assert ctx.role is None
    assert ctx.focus_context is None


# --- Mission brief PM sections ---


def test_pm_brief_includes_role_section(tmp_path):
    """PM role brief should include the PM Role section."""
    ctx = _make_ctx(role="pm", worktree_path=tmp_path)
    brief_path = generate_mission_brief(ctx)
    content = brief_path.read_text()

    assert "## Role: Project Manager" in content
    assert "sequencing" in content
    assert "Deprioritize: code generation" in content


def test_pm_brief_includes_focus_context(tmp_path):
    """PM brief with focus context should include it."""
    focus_str = "## Business Priorities\n- **Security** (high): Harden APIs"
    ctx = _make_ctx(role="pm", focus_context=focus_str, worktree_path=tmp_path)
    brief_path = generate_mission_brief(ctx)
    content = brief_path.read_text()

    assert "## Ecosystem Context" in content
    assert "Business Priorities" in content
    assert "Security" in content


def test_default_brief_omits_pm_section(tmp_path):
    """Default role brief should not include PM section."""
    ctx = _make_ctx(role=None, worktree_path=tmp_path)
    brief_path = generate_mission_brief(ctx)
    content = brief_path.read_text()

    assert "## Role: Project Manager" not in content


def test_default_brief_omits_focus_context(tmp_path):
    """Default brief without focus context should not include it."""
    ctx = _make_ctx(role=None, focus_context=None, worktree_path=tmp_path)
    brief_path = generate_mission_brief(ctx)
    content = brief_path.read_text()

    assert "## Ecosystem Context" not in content


def test_pm_role_section_constant():
    """PM role section constant should contain expected content."""
    assert "Project Manager" in _PM_ROLE_SECTION
    assert "sequencing" in _PM_ROLE_SECTION
    assert "dependency analysis" in _PM_ROLE_SECTION


# --- Dispatch CLI --role flag ---


def test_dispatch_commands_has_role_option():
    """dispatch run command should accept --role option."""
    from nebulus_atom.commands.dispatch_commands import dispatch_run
    import inspect

    sig = inspect.signature(dispatch_run)
    assert "role" in sig.parameters


def test_dispatch_context_role_propagation(tmp_path):
    """Setting role on context should persist through brief generation."""
    ctx = _make_ctx(role="pm", worktree_path=tmp_path)
    assert ctx.role == "pm"
    brief_path = generate_mission_brief(ctx)
    content = brief_path.read_text()
    assert "Project Manager" in content
