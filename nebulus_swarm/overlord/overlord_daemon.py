"""Overlord Background Daemon with scheduled sweeps and Slack integration.

Runs as a persistent async process. Connects to Slack via Socket Mode,
executes scheduled tasks via croniter, and routes detections through
the ProposalManager for approval.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from croniter import croniter

from nebulus_swarm.overlord.autonomy import AutonomyEngine
from nebulus_swarm.overlord.dispatch import DispatchEngine
from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.memory import OverlordMemory
from nebulus_swarm.overlord.model_router import ModelRouter
from nebulus_swarm.overlord.proposal_manager import ProposalManager, ProposalStore
from nebulus_swarm.overlord.registry import ScheduleConfig, ScheduledTask
from nebulus_swarm.overlord.scanner import scan_ecosystem
from nebulus_swarm.overlord.slack_bot import SlackBot
from nebulus_swarm.overlord.slack_commands import SlackCommandRouter
from nebulus_swarm.overlord.task_parser import TaskParser

if TYPE_CHECKING:
    from nebulus_swarm.overlord.registry import OverlordConfig

logger = logging.getLogger(__name__)

# Default DB path for proposals
DEFAULT_PROPOSALS_DB = os.path.expanduser("~/.atom/overlord/proposals.db")


class OverlordDaemon:
    """Persistent daemon process with scheduled sweeps and Slack integration."""

    def __init__(self, config: OverlordConfig):
        """Initialize the daemon with the full Overlord stack.

        Args:
            config: Overlord configuration.
        """
        self.config = config
        self._shutdown_event = asyncio.Event()
        self._running = False

        # Build Phase 2 stack
        self.graph = DependencyGraph(config)
        self.autonomy = AutonomyEngine(config)
        self.router = ModelRouter(config)
        self.dispatch = DispatchEngine(config, self.autonomy, self.graph, self.router)
        self.memory = OverlordMemory()
        self.task_parser = TaskParser(self.graph)

        # Phase 3 components
        self.proposal_store = ProposalStore(DEFAULT_PROPOSALS_DB)
        self.proposal_manager = ProposalManager(
            store=self.proposal_store,
            dispatch=self.dispatch,
            memory=self.memory,
        )
        self.command_router = SlackCommandRouter(
            config, proposal_manager=self.proposal_manager
        )

        # Slack bot (configured lazily via environment)
        self.slack_bot: Optional[SlackBot] = None

        # Schedule config
        self.schedule = config.schedule or ScheduleConfig.default()

    async def run(self) -> None:
        """Start the daemon: Slack bot + scheduler loop."""
        self._running = True
        logger.info("Overlord daemon starting...")

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_shutdown)

        tasks: list[asyncio.Task] = []

        # Start Slack bot if tokens are available
        bot_token = os.environ.get("SLACK_BOT_TOKEN")
        app_token = os.environ.get("SLACK_APP_TOKEN")
        channel_id = os.environ.get("SLACK_CHANNEL_ID")

        if bot_token and app_token and channel_id:
            self.slack_bot = SlackBot(
                bot_token=bot_token,
                app_token=app_token,
                channel_id=channel_id,
                message_handler=self.command_router.handle,
                thread_reply_handler=self.proposal_manager.handle_reply,
            )
            self.proposal_manager.slack_bot = self.slack_bot
            tasks.append(asyncio.create_task(self._run_slack()))
            logger.info("Slack bot configured for channel %s", channel_id)
        else:
            logger.warning("Slack tokens not set — running without Slack integration")

        # Start scheduler
        tasks.append(asyncio.create_task(self._scheduler_loop()))

        # Start proposal cleanup loop
        tasks.append(asyncio.create_task(self._cleanup_loop()))

        # Wait for shutdown
        await self._shutdown_event.wait()
        logger.info("Shutdown signal received, stopping...")

        # Cancel background tasks
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        await self.shutdown()
        logger.info("Overlord daemon stopped.")

    async def _run_slack(self) -> None:
        """Run the Slack bot, handling reconnection."""
        try:
            if self.slack_bot:
                await self.slack_bot.start()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Slack bot crashed")

    async def _scheduler_loop(self) -> None:
        """croniter-based task scheduling loop."""
        # Build next-fire times for each enabled task
        now = datetime.now(timezone.utc)
        schedule_iters: list[tuple[ScheduledTask, croniter]] = []

        for task in self.schedule.tasks:
            if not task.enabled or not task.cron:
                continue
            try:
                cron = croniter(task.cron, now)
                schedule_iters.append((task, cron))
                logger.info(
                    "Scheduled task '%s' with cron '%s' (next: %s)",
                    task.name,
                    task.cron,
                    cron.get_next(datetime),
                )
                # Reset iterator to start fresh
                schedule_iters[-1] = (task, croniter(task.cron, now))
            except (ValueError, KeyError) as e:
                logger.error("Invalid cron for task '%s': %s", task.name, e)

        if not schedule_iters:
            logger.info("No scheduled tasks configured, scheduler idle")
            try:
                await self._shutdown_event.wait()
            except asyncio.CancelledError:
                pass
            return

        try:
            while not self._shutdown_event.is_set():
                now = datetime.now(timezone.utc)
                next_fires = []

                for task, cron_iter in schedule_iters:
                    next_dt = cron_iter.get_next(datetime)
                    next_fires.append((next_dt, task, cron_iter))

                # Find soonest task
                next_fires.sort(key=lambda x: x[0])
                next_dt, next_task, _ = next_fires[0]

                # Sleep until next fire time
                sleep_seconds = max(
                    0, (next_dt - datetime.now(timezone.utc)).total_seconds()
                )
                logger.debug(
                    "Next task '%s' in %.0f seconds", next_task.name, sleep_seconds
                )

                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=sleep_seconds
                    )
                    break  # Shutdown was signaled
                except asyncio.TimeoutError:
                    pass  # Time to fire

                await self._execute_scheduled_task(next_task)

        except asyncio.CancelledError:
            pass

    async def _execute_scheduled_task(self, task: ScheduledTask) -> None:
        """Run a scheduled task.

        Args:
            task: The scheduled task definition.
        """
        logger.info("Executing scheduled task: %s", task.name)

        try:
            if task.name == "scan":
                results = await asyncio.to_thread(scan_ecosystem, self.config)
                issues = [r for r in results if r.issues]
                if issues:
                    summary = ", ".join(
                        f"{r.name}: {len(r.issues)} issues" for r in issues
                    )
                    if self.slack_bot:
                        await self.slack_bot.post_message(f"Scheduled scan: {summary}")
                logger.info(
                    "Scan complete: %d/%d healthy",
                    len(results) - len(issues),
                    len(results),
                )

            elif task.name == "test-all":
                results = await asyncio.to_thread(scan_ecosystem, self.config)
                no_tests = [r for r in results if not r.tests.has_tests]
                if no_tests and self.slack_bot:
                    names = ", ".join(r.name for r in no_tests)
                    await self.slack_bot.post_message(
                        f"Test sweep: {names} have no tests detected"
                    )
                logger.info("Test-all sweep complete")

            elif task.name == "clean-stale-branches":
                results = await asyncio.to_thread(scan_ecosystem, self.config)
                stale = [
                    (r.name, r.git.stale_branches)
                    for r in results
                    if r.git.stale_branches
                ]
                if stale and self.slack_bot:
                    lines = ["Stale branches detected:"]
                    for name, branches in stale:
                        lines.append(f"  {name}: {', '.join(branches)}")
                    await self.slack_bot.post_message("\n".join(lines))
                logger.info(
                    "Stale branch check complete: %d projects with stale branches",
                    len(stale),
                )

            else:
                logger.warning("Unknown scheduled task: %s", task.name)

            # Log to memory
            await asyncio.to_thread(
                self.memory.remember,
                "pattern",
                f"Scheduled task '{task.name}' executed",
            )

        except Exception:
            logger.exception("Failed to execute scheduled task: %s", task.name)

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired proposals."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=300)
                    break
                except asyncio.TimeoutError:
                    pass
                await self.proposal_manager.cleanup_expired()
        except asyncio.CancelledError:
            pass

    async def shutdown(self) -> None:
        """Graceful shutdown: stop Slack, close connections."""
        self._running = False
        if self.slack_bot:
            await self.slack_bot.stop()
        logger.info("Daemon shutdown complete")

    def _signal_shutdown(self) -> None:
        """Handle SIGINT/SIGTERM."""
        logger.info("Received shutdown signal")
        self._shutdown_event.set()

    @property
    def is_running(self) -> bool:
        """Check if daemon is currently running."""
        return self._running
