"""Tests for the halt (kill switch) command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from nebulus_atom.commands.overlord_commands import overlord_app
from nebulus_swarm.overlord.work_queue import Task

runner = CliRunner()


def _make_task(
    task_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
    title: str = "Test task",
    project: str = "nebulus-core",
    status: str = "dispatched",
    locked_by: str | None = None,
) -> Task:
    return Task(
        id=task_id,
        title=title,
        project=project,
        status=status,
        locked_by=locked_by,
    )


@patch("nebulus_atom.commands.overlord_commands._load_queue_for_halt")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.check_running")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.stop_daemon")
def test_halt_cancels_dispatched(mock_stop, mock_running, mock_queue):
    """Halt should transition dispatched tasks to failed."""
    dispatched_task = _make_task(status="dispatched")
    queue = MagicMock()
    queue.list_tasks.side_effect = lambda status: (
        [dispatched_task] if status == "dispatched" else []
    )
    mock_queue.return_value = queue
    mock_running.return_value = False

    result = runner.invoke(overlord_app, ["halt"])

    assert result.exit_code == 0
    assert "1 task(s) cancelled" in result.output
    queue.transition.assert_called_once_with(
        dispatched_task.id, "failed", changed_by="human", reason="Halted by user"
    )


@patch("nebulus_atom.commands.overlord_commands._load_queue_for_halt")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.check_running")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.stop_daemon")
def test_halt_cancels_active_locked(mock_stop, mock_running, mock_queue):
    """Halt should cancel active tasks that have a lock."""
    active_task = _make_task(status="active", locked_by="claude")
    queue = MagicMock()
    queue.list_tasks.side_effect = lambda status: (
        [active_task] if status == "active" else []
    )
    mock_queue.return_value = queue
    mock_running.return_value = False

    result = runner.invoke(overlord_app, ["halt"])

    assert result.exit_code == 0
    assert "1 task(s) cancelled" in result.output
    queue.transition.assert_called_once()


@patch("nebulus_atom.commands.overlord_commands._load_queue_for_halt")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.check_running")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.stop_daemon")
def test_halt_stops_daemon(mock_stop, mock_running, mock_queue):
    """Halt should stop the daemon if running."""
    queue = MagicMock()
    queue.list_tasks.return_value = []
    mock_queue.return_value = queue
    mock_running.return_value = True
    mock_stop.return_value = True

    result = runner.invoke(overlord_app, ["halt"])

    assert result.exit_code == 0
    assert "Daemon stopped" in result.output
    mock_stop.assert_called_once_with(timeout=5.0)


@patch("nebulus_atom.commands.overlord_commands._load_queue_for_halt")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.check_running")
def test_halt_no_dispatched_tasks(mock_running, mock_queue):
    """Halt with no dispatched tasks should succeed."""
    queue = MagicMock()
    queue.list_tasks.return_value = []
    mock_queue.return_value = queue
    mock_running.return_value = False

    result = runner.invoke(overlord_app, ["halt"])

    assert result.exit_code == 0
    assert "0 task(s) cancelled" in result.output


@patch("nebulus_atom.commands.overlord_commands._load_queue_for_halt")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.check_running")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.stop_daemon")
def test_halt_daemon_not_running(mock_stop, mock_running, mock_queue):
    """Halt when daemon isn't running should report that."""
    queue = MagicMock()
    queue.list_tasks.return_value = []
    mock_queue.return_value = queue
    mock_running.return_value = False

    result = runner.invoke(overlord_app, ["halt"])

    assert result.exit_code == 0
    assert "not running" in result.output.lower()
    mock_stop.assert_not_called()


@patch("nebulus_atom.commands.overlord_commands._load_queue_for_halt")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.check_running")
@patch("nebulus_swarm.overlord.overlord_daemon.OverlordDaemon.stop_daemon")
def test_halt_logs_actor_human(mock_stop, mock_running, mock_queue):
    """Halt should log transitions with actor='human'."""
    task = _make_task(status="dispatched")
    queue = MagicMock()
    queue.list_tasks.side_effect = lambda status: (
        [task] if status == "dispatched" else []
    )
    mock_queue.return_value = queue
    mock_running.return_value = False

    runner.invoke(overlord_app, ["halt"])

    call_kwargs = queue.transition.call_args
    assert call_kwargs[1]["changed_by"] == "human" or call_kwargs[0][2] == "human"
