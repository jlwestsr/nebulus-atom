"""Tests for Overlord Background Daemon."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nebulus_swarm.overlord.overlord_daemon import OverlordDaemon
from nebulus_swarm.overlord.registry import (
    OverlordConfig,
    ProjectConfig,
    ScheduleConfig,
    ScheduledTask,
)


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Build a test config with schedule."""
    projects = {}
    for name in ("core", "prime"):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name, path=d, remote=f"test/{name}", role="tooling"
        )

    return OverlordConfig(
        projects=projects,
        autonomy_global="cautious",
        models={
            "local": {
                "endpoint": "http://localhost:5000",
                "model": "test",
                "tier": "local",
            }
        },
        schedule=ScheduleConfig(
            tasks=[
                ScheduledTask(name="scan", cron="0 * * * *"),
                ScheduledTask(name="test-all", cron="0 2 * * *"),
                ScheduledTask(name="clean-stale-branches", cron="0 3 * * 0"),
            ]
        ),
    )


def _make_daemon(tmp_path: Path) -> OverlordDaemon:
    """Build a daemon with test config."""
    config = _make_config(tmp_path)
    with patch(
        "nebulus_swarm.overlord.overlord_daemon.DEFAULT_PROPOSALS_DB",
        str(tmp_path / "proposals.db"),
    ):
        return OverlordDaemon(config)


# --- Daemon Lifecycle Tests ---


class TestDaemonLifecycle:
    """Tests for daemon creation and lifecycle."""

    def test_creates_with_config(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        assert daemon.config is not None
        assert daemon.graph is not None
        assert daemon.autonomy is not None
        assert daemon.dispatch is not None
        assert daemon.proposal_manager is not None
        assert daemon.command_router is not None

    def test_not_running_initially(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        assert daemon.is_running is False

    @pytest.mark.asyncio
    async def test_run_and_shutdown(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)

        async def stop_soon():
            await asyncio.sleep(0.1)
            daemon._shutdown_event.set()

        asyncio.create_task(stop_soon())
        await daemon.run()
        assert daemon.is_running is False

    @pytest.mark.asyncio
    async def test_shutdown_stops_slack_bot(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        mock_bot = MagicMock()
        mock_bot.stop = AsyncMock()
        daemon.slack_bot = mock_bot

        await daemon.shutdown()
        mock_bot.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_without_slack(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        daemon.slack_bot = None
        await daemon.shutdown()
        assert daemon.is_running is False


# --- Scheduler Tests ---


class TestScheduler:
    """Tests for scheduler cron parsing and triggering."""

    def test_schedule_config_default(self) -> None:
        default = ScheduleConfig.default()
        assert len(default.tasks) == 3
        names = [t.name for t in default.tasks]
        assert "scan" in names
        assert "test-all" in names
        assert "clean-stale-branches" in names

    def test_schedule_config_custom(self) -> None:
        config = ScheduleConfig(tasks=[ScheduledTask(name="scan", cron="*/5 * * * *")])
        assert len(config.tasks) == 1
        assert config.tasks[0].cron == "*/5 * * * *"

    def test_scheduled_task_enabled_by_default(self) -> None:
        task = ScheduledTask(name="test", cron="0 * * * *")
        assert task.enabled is True

    def test_scheduled_task_can_be_disabled(self) -> None:
        task = ScheduledTask(name="test", cron="0 * * * *", enabled=False)
        assert task.enabled is False

    def test_daemon_uses_config_schedule(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        assert len(daemon.schedule.tasks) == 3

    def test_daemon_default_schedule_when_empty(self, tmp_path: Path) -> None:
        config = OverlordConfig(
            projects={
                "core": ProjectConfig(
                    name="core",
                    path=tmp_path / "core",
                    remote="test/core",
                    role="tooling",
                )
            },
            models={
                "local": {
                    "endpoint": "http://localhost:5000",
                    "model": "test",
                    "tier": "local",
                }
            },
        )
        (tmp_path / "core").mkdir(exist_ok=True)
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.DEFAULT_PROPOSALS_DB",
            str(tmp_path / "proposals.db"),
        ):
            daemon = OverlordDaemon(config)
        # Empty schedule config has no tasks
        assert isinstance(daemon.schedule, ScheduleConfig)


# --- Task Execution Tests ---


class TestTaskExecution:
    """Tests for scheduled task execution via DispatchEngine."""

    @pytest.mark.asyncio
    async def test_execute_scan_task(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []

        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            return_value=[mock_status],
        ):
            task = ScheduledTask(name="scan", cron="0 * * * *")
            await daemon._execute_scheduled_task(task)
            # No assertions needed — just checking it doesn't raise

    @pytest.mark.asyncio
    async def test_execute_scan_with_issues(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        mock_bot = MagicMock()
        mock_bot.post_message = AsyncMock()
        daemon.slack_bot = mock_bot

        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = ["Dirty working tree"]

        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            return_value=[mock_status],
        ):
            task = ScheduledTask(name="scan", cron="0 * * * *")
            await daemon._execute_scheduled_task(task)
            mock_bot.post_message.assert_called_once()
            call_text = mock_bot.post_message.call_args[0][0]
            assert "core" in call_text

    @pytest.mark.asyncio
    async def test_execute_test_all_task(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.tests = MagicMock(has_tests=True)

        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            return_value=[mock_status],
        ):
            task = ScheduledTask(name="test-all", cron="0 2 * * *")
            await daemon._execute_scheduled_task(task)

    @pytest.mark.asyncio
    async def test_execute_clean_stale_branches(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        mock_bot = MagicMock()
        mock_bot.post_message = AsyncMock()
        daemon.slack_bot = mock_bot

        mock_status = MagicMock()
        mock_status.name = "prime"
        mock_status.git = MagicMock(stale_branches=["old-feature", "dead-branch"])

        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            return_value=[mock_status],
        ):
            task = ScheduledTask(name="clean-stale-branches", cron="0 3 * * 0")
            await daemon._execute_scheduled_task(task)
            mock_bot.post_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_unknown_task(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        task = ScheduledTask(name="unknown-task", cron="0 * * * *")
        # Should log warning but not raise
        await daemon._execute_scheduled_task(task)

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            side_effect=RuntimeError("git error"),
        ):
            task = ScheduledTask(name="scan", cron="0 * * * *")
            # Should not raise
            await daemon._execute_scheduled_task(task)


# --- Autonomy Gating Tests ---


class TestAutonomyGating:
    """Tests for autonomy gating on scheduled tasks."""

    def test_daemon_respects_cautious_autonomy(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        assert daemon.autonomy.get_level() == "cautious"

    def test_proposal_manager_wired(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        assert daemon.proposal_manager is not None
        assert daemon.command_router.proposal_manager is daemon.proposal_manager

    def test_dispatch_uses_autonomy(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        assert daemon.dispatch is not None
        # DispatchEngine has an autonomy reference
        assert daemon.dispatch.autonomy is daemon.autonomy

    def test_cautious_blocks_auto_execute(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        from nebulus_swarm.overlord.action_scope import ActionScope

        scope = ActionScope(
            projects=["core"],
            branches=["develop", "main"],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        assert daemon.autonomy.can_auto_execute("merge", scope) is False


# --- Graceful Shutdown Tests ---


class TestGracefulShutdown:
    """Tests for graceful daemon shutdown."""

    @pytest.mark.asyncio
    async def test_signal_sets_event(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        assert not daemon._shutdown_event.is_set()
        daemon._signal_shutdown()
        assert daemon._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_cleanup_loop_stops_on_shutdown(self, tmp_path: Path) -> None:
        daemon = _make_daemon(tmp_path)
        daemon._shutdown_event.set()
        # Should return quickly
        await asyncio.wait_for(daemon._cleanup_loop(), timeout=2)


# --- CLI Integration Tests ---


class TestCLIIntegration:
    """Tests for daemon CLI commands."""

    def test_daemon_command_exists(self) -> None:
        from nebulus_atom.commands.overlord_commands import overlord_app

        # Check daemon command is registered
        commands = {
            cmd.name or cmd.callback.__name__
            for cmd in overlord_app.registered_commands
        }
        assert "daemon" in commands

    def test_schedule_config_parsing(self, tmp_path: Path) -> None:
        from nebulus_swarm.overlord.registry import ScheduleConfig, ScheduledTask

        config = ScheduleConfig(
            tasks=[
                ScheduledTask(name="scan", cron="*/10 * * * *"),
                ScheduledTask(name="test-all", cron="0 0 * * *", enabled=False),
            ]
        )
        assert config.tasks[0].enabled is True
        assert config.tasks[1].enabled is False
