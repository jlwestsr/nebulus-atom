"""Overlord main entry point and orchestration."""

import asyncio
import logging
import os
import signal
from datetime import datetime, timedelta
from typing import Optional

from aiohttp import web

from nebulus_swarm.config import SwarmConfig
from nebulus_swarm.models.minion import Minion, MinionStatus
from nebulus_swarm.overlord.command_parser import CommandParser, CommandType
from nebulus_swarm.overlord.docker_manager import DockerManager
from nebulus_swarm.overlord.slack_bot import SlackBot
from nebulus_swarm.overlord.state import OverlordState

logger = logging.getLogger(__name__)

# Watchdog configuration
WATCHDOG_INTERVAL = 60  # Check every 60 seconds
HEARTBEAT_TIMEOUT = 300  # 5 minutes without heartbeat = stuck


class Overlord:
    """Main Overlord controller that orchestrates Minions."""

    def __init__(self, config: SwarmConfig, stub_mode: bool = False):
        """Initialize Overlord with configuration.

        Args:
            config: Swarm configuration object.
            stub_mode: If True, don't actually spawn containers.
        """
        self.config = config
        self.stub_mode = stub_mode
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Initialize components
        self.state = OverlordState(db_path=config.state_db_path)

        self.docker = DockerManager(
            minion_config=config.minions,
            llm_config=config.llm,
            github_token=config.github.token,
            overlord_callback_url=f"http://overlord:{config.health_port}/minion/report",
            stub_mode=stub_mode,
        )

        self.parser = CommandParser(default_repo=config.github.default_repo)

        self.slack = SlackBot(
            bot_token=config.slack.bot_token,
            app_token=config.slack.app_token,
            channel_id=config.slack.channel_id,
            message_handler=self._handle_message,
        )

        # Health check server
        self._health_app: Optional[web.Application] = None
        self._health_runner: Optional[web.AppRunner] = None

        # Background tasks
        self._watchdog_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

        # Queue processing state
        self._paused = False

    def _handle_message(self, user_id: str, text: str) -> str:
        """Handle incoming Slack message.

        Args:
            user_id: Slack user ID.
            text: Message text.

        Returns:
            Response message to send back.
        """
        command = self.parser.parse(text)
        logger.info(f"Parsed command from {user_id}: {command.type.value}")

        handlers = {
            CommandType.STATUS: self._handle_status,
            CommandType.WORK: self._handle_work,
            CommandType.STOP: self._handle_stop,
            CommandType.QUEUE: self._handle_queue,
            CommandType.PAUSE: self._handle_pause,
            CommandType.RESUME: self._handle_resume,
            CommandType.HISTORY: self._handle_history,
            CommandType.HELP: self._handle_help,
            CommandType.UNKNOWN: self._handle_unknown,
        }

        handler = handlers.get(command.type, self._handle_unknown)
        try:
            return handler(command)
        except Exception as e:
            logger.exception(f"Error handling command: {e}")
            return f"❌ Error: {e}"

    def _handle_status(self, command) -> str:
        """Handle status command."""
        minions = self.state.get_active_minions()

        if not minions:
            status = "paused" if self._paused else "idle"
            docker_status = "✅" if self.docker.is_available() else "❌"
            return f"No active minions. Queue is {status}. Docker: {docker_status}"

        lines = [f"*Active Minions ({len(minions)}):*"]
        for m in minions:
            emoji = "🚀" if m.status == MinionStatus.STARTING else "⚙️"
            # Check container status
            container_status = self.docker.get_minion_status(m.id)
            status_str = f"({m.status.value}"
            if container_status and container_status != "running":
                status_str += f", container: {container_status}"
            status_str += ")"
            lines.append(f"• {emoji} `{m.id}` - {m.repo}#{m.issue_number} {status_str}")

        if self._paused:
            lines.append("\n⏸️ Queue processing is paused.")

        return "\n".join(lines)

    def _handle_work(self, command) -> str:
        """Handle work command - spawn a minion."""
        if not command.repo:
            return "❌ Please specify a repository (e.g., `work on owner/repo#42`)"

        if command.issue_number is None:
            return "❌ Please specify an issue number (e.g., `work on #42`)"

        # Check if Docker is available
        if not self.docker.is_available():
            return "❌ Docker is not available. Cannot spawn minions."

        # Check concurrent limit
        active_count = len(self.state.get_active_minions())
        if active_count >= self.config.minions.max_concurrent:
            return f"⚠️ Max concurrent minions ({self.config.minions.max_concurrent}) reached. Wait for one to finish."

        # Check if already working on this issue
        existing = self.state.get_minion_by_issue(command.repo, command.issue_number)
        if existing:
            return f"⚠️ Already working on {command.repo}#{command.issue_number} (minion `{existing.id}`)"

        try:
            # Spawn minion
            minion_id = self.docker.spawn_minion(command.repo, command.issue_number)

            # Create minion record
            minion = Minion(
                id=minion_id,
                repo=command.repo,
                issue_number=command.issue_number,
                status=MinionStatus.STARTING,
                started_at=datetime.now(),
                last_heartbeat=datetime.now(),
            )
            self.state.add_minion(minion)

            return f"🚀 Spawning minion `{minion_id}` to work on {command.repo}#{command.issue_number}"

        except Exception as e:
            logger.exception(f"Failed to spawn minion: {e}")
            return f"❌ Failed to spawn minion: {e}"

    def _handle_stop(self, command) -> str:
        """Handle stop command - kill a minion."""
        if command.minion_id:
            # Stop by minion ID
            minion = self.state.get_minion(command.minion_id)
            if not minion:
                return f"❌ Minion `{command.minion_id}` not found"

            self.docker.kill_minion(command.minion_id)
            self.state.record_completion(
                minion,
                MinionStatus.FAILED,
                error_message="Manually stopped by user",
            )
            return f"🛑 Stopped minion `{command.minion_id}`"

        elif command.issue_number is not None:
            # Stop by issue number
            repo = command.repo or self.config.github.default_repo
            if not repo:
                return "❌ Please specify a repository or set a default"

            minion = self.state.get_minion_by_issue(repo, command.issue_number)
            if not minion:
                return f"❌ No minion working on {repo}#{command.issue_number}"

            self.docker.kill_minion(minion.id)
            self.state.record_completion(
                minion,
                MinionStatus.FAILED,
                error_message="Manually stopped by user",
            )
            return f"🛑 Stopped minion `{minion.id}` (was working on #{command.issue_number})"

        return "❌ Please specify an issue number or minion ID to stop"

    def _handle_queue(self, command) -> str:
        """Handle queue command - show pending work."""
        # TODO: In Phase 4, this will query GitHub for labeled issues
        return "📋 *Pending Work Queue:*\n(GitHub integration coming in Phase 4)"

    def _handle_pause(self, command) -> str:
        """Handle pause command."""
        if self._paused:
            return "⏸️ Queue processing is already paused."

        self._paused = True
        return "⏸️ Queue processing paused. Active minions will continue."

    def _handle_resume(self, command) -> str:
        """Handle resume command."""
        if not self._paused:
            return "▶️ Queue processing is already running."

        self._paused = False
        return "▶️ Queue processing resumed."

    def _handle_history(self, command) -> str:
        """Handle history command - show recent work."""
        history = self.state.get_work_history(limit=10)

        if not history:
            return "📜 No work history yet."

        lines = ["*Recent Work:*"]
        for h in history:
            emoji = "✅" if h["status"] == "completed" else "❌"
            pr_link = f" → PR #{h['pr_number']}" if h.get("pr_number") else ""
            lines.append(f"• {emoji} {h['repo']}#{h['issue_number']}{pr_link}")

        return "\n".join(lines)

    def _handle_help(self, command) -> str:
        """Handle help command."""
        return self.parser.format_help()

    def _handle_unknown(self, command) -> str:
        """Handle unknown command."""
        return (
            f"🤔 I don't understand: `{command.raw_text}`\n"
            "Type `help` to see available commands."
        )

    async def _setup_health_server(self) -> None:
        """Set up health check HTTP server."""
        self._health_app = web.Application()
        self._health_app.router.add_get("/health", self._health_handler)
        self._health_app.router.add_get("/status", self._status_handler)
        self._health_app.router.add_post("/minion/report", self._minion_report_handler)

        self._health_runner = web.AppRunner(self._health_app)
        await self._health_runner.setup()

        site = web.TCPSite(self._health_runner, "0.0.0.0", self.config.health_port)
        await site.start()
        logger.info(f"Health check server started on port {self.config.health_port}")

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Handle health check requests."""
        active_minions = len(self.state.get_active_minions())
        return web.json_response(
            {
                "status": "healthy",
                "active_minions": active_minions,
                "paused": self._paused,
                "docker_available": self.docker.is_available(),
            }
        )

    async def _status_handler(self, request: web.Request) -> web.Response:
        """Handle detailed status requests."""
        minions = self.state.get_active_minions()
        docker_minions = self.docker.list_minions()

        return web.json_response(
            {
                "status": "healthy",
                "paused": self._paused,
                "docker_available": self.docker.is_available(),
                "active_minions": [m.to_dict() for m in minions],
                "docker_containers": docker_minions,
                "config": {
                    "max_concurrent": self.config.minions.max_concurrent,
                    "timeout_minutes": self.config.minions.timeout_minutes,
                },
            }
        )

    async def _minion_report_handler(self, request: web.Request) -> web.Response:
        """Handle minion status reports.

        This endpoint receives callbacks from running Minions.
        """
        try:
            data = await request.json()
            minion_id = data.get("minion_id")
            event = data.get("event", "unknown")
            issue = data.get("issue")
            message = data.get("message", "")
            report_data = data.get("data", {})

            logger.info(f"Minion report: {minion_id} -> {event}: {message}")

            if not minion_id:
                return web.json_response(
                    {"ok": False, "error": "missing minion_id"}, status=400
                )

            minion = self.state.get_minion(minion_id)
            if not minion:
                logger.warning(f"Report from unknown minion: {minion_id}")
                return web.json_response(
                    {"ok": False, "error": "unknown minion"}, status=404
                )

            # Handle different event types
            if event == "heartbeat":
                self.state.update_minion(
                    minion_id,
                    last_heartbeat=datetime.now(),
                )

            elif event == "progress":
                self.state.update_minion(
                    minion_id,
                    status=MinionStatus.WORKING,
                    last_heartbeat=datetime.now(),
                )
                # Relay progress to Slack
                asyncio.create_task(
                    self.slack.post_message(
                        f"⚙️ Minion `{minion_id}` on #{issue}: {message}"
                    )
                )

            elif event == "complete":
                pr_number = report_data.get("pr_number")
                pr_url = report_data.get("pr_url")

                self.state.record_completion(
                    minion,
                    MinionStatus.COMPLETED,
                    pr_number=pr_number,
                )

                # Notify Slack
                msg = f"✅ Minion `{minion_id}` completed #{issue}"
                if pr_url:
                    msg += f"\n→ {pr_url}"
                elif pr_number:
                    msg += f" → PR #{pr_number}"

                asyncio.create_task(self.slack.post_message(msg))

                # Clean up container
                self.docker.kill_minion(minion_id)

            elif event == "error":
                error_type = report_data.get("error_type", "unknown")
                details = report_data.get("details", "")

                self.state.record_completion(
                    minion,
                    MinionStatus.FAILED,
                    error_message=f"{error_type}: {message}",
                )

                # Notify Slack
                msg = f"❌ Minion `{minion_id}` failed on #{issue}: {message}"
                if details:
                    msg += f"\n> {details[:200]}"

                asyncio.create_task(self.slack.post_message(msg))

                # Clean up container
                self.docker.kill_minion(minion_id)

            return web.json_response({"ok": True})

        except Exception as e:
            logger.exception(f"Error handling minion report: {e}")
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _watchdog_loop(self) -> None:
        """Background task that monitors for stuck Minions."""
        logger.info("Watchdog started")

        while self._running:
            try:
                await self._check_stuck_minions()
                await self._sync_container_states()
            except Exception as e:
                logger.exception(f"Watchdog error: {e}")

            await asyncio.sleep(WATCHDOG_INTERVAL)

        logger.info("Watchdog stopped")

    async def _check_stuck_minions(self) -> None:
        """Check for Minions that haven't sent heartbeats."""
        timeout_threshold = datetime.now() - timedelta(seconds=HEARTBEAT_TIMEOUT)

        for minion in self.state.get_active_minions():
            # Skip if no heartbeat recorded yet (just started)
            if not minion.last_heartbeat:
                continue

            if minion.last_heartbeat < timeout_threshold:
                logger.warning(f"Minion {minion.id} appears stuck (no heartbeat)")

                # Kill the container
                self.docker.kill_minion(minion.id)

                # Record failure
                self.state.record_completion(
                    minion,
                    MinionStatus.TIMEOUT,
                    error_message="No heartbeat - terminated by watchdog",
                )

                # Notify Slack
                await self.slack.post_message(
                    f"☠️ Minion `{minion.id}` on #{minion.issue_number} went silent, terminated by watchdog"
                )

    async def _sync_container_states(self) -> None:
        """Sync state with actual container statuses."""
        for minion in self.state.get_active_minions():
            container_status = self.docker.get_minion_status(minion.id)

            # Container exited without reporting
            if container_status == "exited":
                logger.warning(f"Minion {minion.id} container exited without reporting")

                # Get logs for debugging
                logs = self.docker.get_minion_logs(minion.id, tail=50)
                if logs:
                    logger.debug(f"Container logs:\n{logs}")

                # Clean up
                self.docker.kill_minion(minion.id)
                self.state.record_completion(
                    minion,
                    MinionStatus.FAILED,
                    error_message="Container exited unexpectedly",
                )

                await self.slack.post_message(
                    f"💀 Minion `{minion.id}` on #{minion.issue_number} container exited unexpectedly"
                )

            # Container doesn't exist (removed externally?)
            elif container_status is None and not self.stub_mode:
                logger.warning(f"Minion {minion.id} container not found")
                self.state.record_completion(
                    minion,
                    MinionStatus.FAILED,
                    error_message="Container not found",
                )

    async def _cleanup_loop(self) -> None:
        """Background task that cleans up dead containers."""
        while self._running:
            try:
                cleaned = self.docker.cleanup_dead_containers()
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} dead containers")
            except Exception as e:
                logger.exception(f"Cleanup error: {e}")

            # Run every 5 minutes
            await asyncio.sleep(300)

    async def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Shutting down Overlord...")

        self._running = False

        # Cancel background tasks
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Stop Slack bot
        await self.slack.stop()

        # Stop health server
        if self._health_runner:
            await self._health_runner.cleanup()

        self._shutdown_event.set()
        logger.info("Overlord shutdown complete")

    def _signal_handler(self, sig: signal.Signals) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        asyncio.create_task(self._shutdown())

    async def run(self) -> None:
        """Run the Overlord main loop."""
        logger.info("Starting Overlord...")

        # Validate configuration
        errors = self.config.validate()
        if errors:
            for error in errors:
                logger.error(f"Config error: {error}")
            raise ValueError(f"Configuration errors: {errors}")

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: self._signal_handler(s))

        self._running = True

        # Ensure Docker network exists
        if not self.stub_mode:
            self.docker.ensure_network()
            self.docker.sync_active_containers()

        # Start health check server
        await self._setup_health_server()

        # Start background tasks
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        # Start Slack bot
        await self.slack.start()

        # Post startup message
        await self.slack.post_message(
            "🤖 *Overlord Online*\n"
            f"Monitoring channel. Type `help` for commands.\n"
            f"Queue processing: {'paused' if self._paused else 'active'}\n"
            f"Max concurrent minions: {self.config.minions.max_concurrent}"
        )

        logger.info("Overlord is running")

        # Wait for shutdown signal
        await self._shutdown_event.wait()


async def main() -> None:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Check for stub mode from environment
    stub_mode = os.environ.get("OVERLORD_STUB_MODE", "false").lower() == "true"

    config = SwarmConfig.from_env()
    overlord = Overlord(config, stub_mode=stub_mode)
    await overlord.run()


if __name__ == "__main__":
    asyncio.run(main())
