"""Overlord main entry point and orchestration."""

import asyncio
import logging
import signal
from aiohttp import web
from datetime import datetime
from typing import Optional

from nebulus_swarm.config import SwarmConfig
from nebulus_swarm.models.minion import Minion, MinionStatus
from nebulus_swarm.overlord.state import OverlordState
from nebulus_swarm.overlord.slack_bot import SlackBot
from nebulus_swarm.overlord.command_parser import CommandParser, CommandType
from nebulus_swarm.overlord.docker_manager import DockerManager

logger = logging.getLogger(__name__)


class Overlord:
    """Main Overlord controller that orchestrates Minions."""

    def __init__(self, config: SwarmConfig):
        """Initialize Overlord with configuration.

        Args:
            config: Swarm configuration object.
        """
        self.config = config
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Initialize components
        self.state = OverlordState(db_path=config.state_db_path)

        self.docker = DockerManager(
            minion_config=config.minions,
            llm_config=config.llm,
            github_token=config.github.token,
            overlord_callback_url=f"http://overlord:{config.health_port}/minion/report",
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
        return handler(command)

    def _handle_status(self, command) -> str:
        """Handle status command."""
        minions = self.state.get_active_minions()

        if not minions:
            status = "paused" if self._paused else "idle"
            return f"No active minions. Queue is {status}."

        lines = [f"*Active Minions ({len(minions)}):*"]
        for m in minions:
            emoji = "🚀" if m.status == MinionStatus.STARTING else "⚙️"
            lines.append(
                f"• {emoji} `{m.id}` - {m.repo}#{m.issue_number} ({m.status.value})"
            )

        if self._paused:
            lines.append("\n⏸️ Queue processing is paused.")

        return "\n".join(lines)

    def _handle_work(self, command) -> str:
        """Handle work command - spawn a minion."""
        if not command.repo:
            return "❌ Please specify a repository (e.g., `work on owner/repo#42`)"

        if command.issue_number is None:
            return "❌ Please specify an issue number (e.g., `work on #42`)"

        # Check if already working on this issue
        existing = self.state.get_minion_by_issue(command.repo, command.issue_number)
        if existing:
            return f"⚠️ Already working on {command.repo}#{command.issue_number} (minion `{existing.id}`)"

        # Spawn minion
        minion_id = self.docker.spawn_minion(command.repo, command.issue_number)

        # Create minion record
        minion = Minion(
            id=minion_id,
            repo=command.repo,
            issue_number=command.issue_number,
            status=MinionStatus.STARTING,
            started_at=datetime.now(),
        )
        self.state.add_minion(minion)

        return f"🚀 Spawning minion `{minion_id}` to work on {command.repo}#{command.issue_number}"

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
        # STUB: In Phase 3, this will query GitHub for labeled issues
        return "📋 *Pending Work Queue:*\n(GitHub integration coming in Phase 3)"

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

    async def _minion_report_handler(self, request: web.Request) -> web.Response:
        """Handle minion status reports.

        This endpoint receives callbacks from running Minions.
        """
        try:
            data = await request.json()
            minion_id = data.get("minion_id")
            status = data.get("status")
            pr_number = data.get("pr_number")
            error = data.get("error")

            logger.info(f"Minion report: {minion_id} -> {status}")

            if minion_id:
                minion = self.state.get_minion(minion_id)
                if minion:
                    if status in ("completed", "failed", "timeout"):
                        self.state.record_completion(
                            minion,
                            MinionStatus(status),
                            pr_number=pr_number,
                            error_message=error,
                        )
                        # Notify Slack
                        emoji = "✅" if status == "completed" else "❌"
                        msg = f"{emoji} Minion `{minion_id}` finished: {status}"
                        if pr_number:
                            msg += f" → PR #{pr_number}"
                        asyncio.create_task(self.slack.post_message(msg))
                    else:
                        self.state.update_minion(
                            minion_id,
                            status=MinionStatus(status),
                            last_heartbeat=datetime.now(),
                            pr_number=pr_number,
                        )

            return web.json_response({"ok": True})
        except Exception as e:
            logger.error(f"Error handling minion report: {e}")
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Shutting down Overlord...")

        # Stop Slack bot
        await self.slack.stop()

        # Stop health server
        if self._health_runner:
            await self._health_runner.cleanup()

        # Clean up containers (optional - could leave them running)
        # for minion in self.state.get_active_minions():
        #     self.docker.kill_minion(minion.id)

        self._running = False
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

        # Start health check server
        await self._setup_health_server()

        # Start Slack bot
        await self.slack.start()

        # Post startup message
        await self.slack.post_message(
            "🤖 *Overlord Online*\n"
            f"Monitoring channel. Type `help` for commands.\n"
            f"Queue processing: {'paused' if self._paused else 'active'}"
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

    config = SwarmConfig.from_env()
    overlord = Overlord(config)
    await overlord.run()


if __name__ == "__main__":
    asyncio.run(main())
