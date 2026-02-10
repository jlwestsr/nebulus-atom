"""End-to-end integration tests for Overlord Phase 3.

Tests the full lifecycle: daemon → schedule → detect → propose →
approve → execute → notify.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nebulus_swarm.overlord.action_scope import ActionScope
from nebulus_swarm.overlord.dispatch import DispatchPlan, DispatchResult, DispatchStep
from nebulus_swarm.overlord.overlord_daemon import OverlordDaemon
from nebulus_swarm.overlord.proposal_manager import (
    ProposalManager,
    ProposalState,
    ProposalStore,
)
from nebulus_swarm.overlord.registry import (
    OverlordConfig,
    ProjectConfig,
    ScheduleConfig,
    ScheduledTask,
)
from nebulus_swarm.overlord.slack_commands import SlackCommandRouter


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Build a test config."""
    projects = {}
    for name in ("core", "prime", "edge"):
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name,
            path=d,
            remote=f"test/{name}",
            role="tooling",
            depends_on=["core"] if name != "core" else [],
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
        schedule=ScheduleConfig(tasks=[ScheduledTask(name="scan", cron="0 * * * *")]),
    )


# --- Full Lifecycle Tests ---


class TestFullLifecycle:
    """Tests for the complete Phase 3 lifecycle."""

    @pytest.mark.asyncio
    async def test_propose_approve_execute(self, tmp_path: Path) -> None:
        """Full lifecycle: propose → approve → execute."""
        _make_config(tmp_path)
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        dispatch.execute.return_value = DispatchResult(status="success")
        mgr = ProposalManager(store=store, dispatch=dispatch)

        scope = ActionScope(
            projects=["core"],
            branches=["develop", "main"],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        plan = DispatchPlan(
            task="merge core develop to main",
            steps=[DispatchStep(id="s1", action="merge", project="core")],
            scope=scope,
            estimated_duration=30,
            requires_approval=True,
        )

        # Propose
        pid = await mgr.propose("merge core", scope, "routine merge", plan=plan)
        assert store.get(pid).state == ProposalState.PENDING

        # Approve via thread reply
        proposal = store.get(pid)
        proposal.thread_ts = "1234.5678"
        store.save(proposal)

        result_msg = await mgr.handle_reply("1234.5678", "approve")
        assert "approved" in result_msg.lower()
        assert store.get(pid).state == ProposalState.COMPLETED

    @pytest.mark.asyncio
    async def test_propose_deny_lifecycle(self, tmp_path: Path) -> None:
        """Lifecycle: propose → deny."""
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        mgr = ProposalManager(store=store, dispatch=dispatch)

        scope = ActionScope(
            projects=["prime"],
            branches=["develop"],
            destructive=True,
            reversible=False,
            affects_remote=False,
            estimated_impact="high",
        )
        pid = await mgr.propose("dangerous operation", scope, "needs review")
        proposal = store.get(pid)
        proposal.thread_ts = "deny.thread"
        store.save(proposal)

        result_msg = await mgr.handle_reply("deny.thread", "deny")
        assert "denied" in result_msg.lower()
        assert store.get(pid).state == ProposalState.DENIED

    @pytest.mark.asyncio
    async def test_detect_propose_approve(self, tmp_path: Path) -> None:
        """Detection → proposal → approval pipeline."""
        config = _make_config(tmp_path)
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        dispatch.execute.return_value = DispatchResult(status="success")
        mgr = ProposalManager(store=store, dispatch=dispatch)

        router = SlackCommandRouter(config, proposal_manager=mgr)

        # Simulate a merge that requires approval
        mock_plan = MagicMock()
        mock_plan.task = "merge core develop to main"
        mock_plan.steps = [MagicMock()]
        mock_plan.scope = MagicMock(projects=["core"], estimated_impact="high")
        mock_plan.requires_approval = True

        with patch.object(router.task_parser, "parse", return_value=mock_plan):
            result = await router.handle("merge core develop to main", "U123", "C456")
            assert "proposal" in result.lower()

        # Verify proposal was created
        pending = store.list_pending()
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_slack_command_through_router(self, tmp_path: Path) -> None:
        """Slack command routes through the full stack."""
        config = _make_config(tmp_path)
        router = SlackCommandRouter(config)

        # Status command
        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []
        mock_status.git = MagicMock(branch="develop", clean=True)

        with patch(
            "nebulus_swarm.overlord.slack_commands.scan_ecosystem",
            return_value=[mock_status],
        ):
            result = await router.handle("status", "U123", "C456")
            assert "core" in result

        # Help command
        result = await router.handle("help", "U123", "C456")
        assert "approve" in result
        assert "deny" in result


# --- Daemon Integration Tests ---


class TestDaemonIntegration:
    """Tests for daemon with all Phase 3 components wired."""

    @pytest.mark.asyncio
    async def test_daemon_starts_and_stops(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.DEFAULT_PROPOSALS_DB",
            str(tmp_path / "proposals.db"),
        ):
            daemon = OverlordDaemon(config)

        async def stop_soon():
            await asyncio.sleep(0.05)
            daemon._shutdown_event.set()

        env_patch = {
            "SLACK_BOT_TOKEN": "",
            "SLACK_APP_TOKEN": "",
            "SLACK_CHANNEL_ID": "",
        }
        with patch.dict(os.environ, env_patch):
            asyncio.create_task(stop_soon())
            await daemon.run()
        assert not daemon.is_running

    @pytest.mark.asyncio
    async def test_daemon_scan_with_detection(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.DEFAULT_PROPOSALS_DB",
            str(tmp_path / "proposals.db"),
        ):
            daemon = OverlordDaemon(config)

        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []
        mock_status.git = MagicMock(
            branch="develop", clean=True, ahead=5, stale_branches=[]
        )
        mock_status.tests = MagicMock(has_tests=True)

        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            return_value=[mock_status],
        ):
            task = ScheduledTask(name="scan", cron="0 * * * *")
            await daemon._execute_scheduled_task(task)

        # Check notification was accumulated
        assert daemon.notifications.stats.health_checks == 1

    @pytest.mark.asyncio
    async def test_daemon_all_components_wired(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.DEFAULT_PROPOSALS_DB",
            str(tmp_path / "proposals.db"),
        ):
            daemon = OverlordDaemon(config)

        assert daemon.command_router is not None
        assert daemon.proposal_manager is not None
        assert daemon.detection_engine is not None
        assert daemon.notifications is not None
        assert daemon.command_router.proposal_manager is daemon.proposal_manager


# --- Notification Integration Tests ---


class TestNotificationIntegration:
    """Tests for notification system with daemon pipeline."""

    @pytest.mark.asyncio
    async def test_scan_accumulates_notification(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.DEFAULT_PROPOSALS_DB",
            str(tmp_path / "proposals.db"),
        ):
            daemon = OverlordDaemon(config)

        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []
        mock_status.git = MagicMock(
            branch="develop", clean=True, ahead=0, stale_branches=[]
        )
        mock_status.tests = MagicMock(has_tests=True)

        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            return_value=[mock_status],
        ):
            await daemon._execute_scheduled_task(
                ScheduledTask(name="scan", cron="0 * * * *")
            )

        assert daemon.notifications.buffer_size >= 1

    @pytest.mark.asyncio
    async def test_test_sweep_accumulates_notification(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.DEFAULT_PROPOSALS_DB",
            str(tmp_path / "proposals.db"),
        ):
            daemon = OverlordDaemon(config)

        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.tests = MagicMock(has_tests=True)

        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            return_value=[mock_status],
        ):
            await daemon._execute_scheduled_task(
                ScheduledTask(name="test-all", cron="0 2 * * *")
            )

        assert daemon.notifications.stats.test_sweeps == 1

    @pytest.mark.asyncio
    async def test_digest_after_scan_cycle(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.DEFAULT_PROPOSALS_DB",
            str(tmp_path / "proposals.db"),
        ):
            daemon = OverlordDaemon(config)

        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []
        mock_status.git = MagicMock(
            branch="develop", clean=True, ahead=0, stale_branches=[]
        )
        mock_status.tests = MagicMock(has_tests=True)

        # Run a scan
        with patch(
            "nebulus_swarm.overlord.overlord_daemon.scan_ecosystem",
            return_value=[mock_status],
        ):
            await daemon._execute_scheduled_task(
                ScheduledTask(name="scan", cron="0 * * * *")
            )

        # Send digest
        await daemon.notifications.send_digest()
        assert daemon.notifications.buffer_size == 0
