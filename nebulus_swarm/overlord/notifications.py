"""Notification manager for Overlord Phase 3.

Routes notifications by urgency (immediate vs. buffered digest).
Accumulates events during the day and sends a formatted daily digest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nebulus_swarm.overlord.slack_bot import SlackBot

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """A single notification event."""

    category: str  # "detection", "proposal", "execution", "scheduled"
    message: str
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class DigestStats:
    """Accumulated statistics for the daily digest."""

    health_checks: int = 0
    detections: int = 0
    proposals_created: int = 0
    proposals_approved: int = 0
    proposals_denied: int = 0
    executions: int = 0
    test_sweeps: int = 0


class NotificationManager:
    """Routes notifications by urgency, accumulates digest."""

    def __init__(
        self,
        slack_bot: Optional[SlackBot] = None,
        urgent_enabled: bool = True,
        digest_enabled: bool = True,
    ):
        """Initialize the notification manager.

        Args:
            slack_bot: Optional Slack bot for sending messages.
            urgent_enabled: Whether to send immediate notifications.
            digest_enabled: Whether to accumulate and send digests.
        """
        self.slack_bot = slack_bot
        self.urgent_enabled = urgent_enabled
        self.digest_enabled = digest_enabled
        self._buffer: list[Notification] = []
        self.stats = DigestStats()

    async def send_urgent(self, message: str) -> None:
        """Send an immediate notification to Slack.

        Args:
            message: Message text to send immediately.
        """
        if not self.urgent_enabled:
            logger.debug("Urgent notification suppressed: %s", message[:80])
            return

        if self.slack_bot:
            await self.slack_bot.post_message(message)
        logger.info("Urgent notification: %s", message[:80])

    def accumulate(self, category: str, message: str) -> None:
        """Buffer a notification for the daily digest.

        Args:
            category: Notification category.
            message: Notification message.
        """
        self._buffer.append(Notification(category=category, message=message))

        # Update stats
        if category == "detection":
            self.stats.detections += 1
        elif category == "proposal_created":
            self.stats.proposals_created += 1
        elif category == "proposal_approved":
            self.stats.proposals_approved += 1
        elif category == "proposal_denied":
            self.stats.proposals_denied += 1
        elif category == "execution":
            self.stats.executions += 1
        elif category == "health_check":
            self.stats.health_checks += 1
        elif category == "test_sweep":
            self.stats.test_sweeps += 1

    async def send_digest(self) -> None:
        """Format and send the accumulated daily digest."""
        if not self.digest_enabled:
            logger.debug("Digest suppressed")
            return

        if not self._buffer and not self._has_activity():
            logger.info("No activity to report in digest")
            return

        message = self._format_digest()

        if self.slack_bot:
            await self.slack_bot.post_message(message)

        logger.info("Daily digest sent (%d buffered events)", len(self._buffer))
        self._buffer.clear()
        self.stats = DigestStats()

    def _has_activity(self) -> bool:
        """Check if there's any activity to report."""
        s = self.stats
        return any(
            [
                s.health_checks,
                s.detections,
                s.proposals_created,
                s.executions,
                s.test_sweeps,
            ]
        )

    def _format_digest(self) -> str:
        """Format the daily digest message.

        Returns:
            Formatted digest string for Slack.
        """
        now = datetime.now(timezone.utc).strftime("%b %d, %Y")
        s = self.stats

        lines = [f"Overlord Daily Digest — {now}", ""]

        # Activity summary
        activity_parts = []
        if s.detections:
            activity_parts.append(f"{s.detections} detections")
        if s.proposals_created:
            activity_parts.append(f"{s.proposals_created} proposals")
        if s.executions:
            activity_parts.append(f"{s.executions} executed")
        if activity_parts:
            lines.append(f"Activity: {', '.join(activity_parts)}")

        # Scheduled task summary
        sched_parts = []
        if s.health_checks:
            sched_parts.append(f"{s.health_checks} health checks")
        if s.test_sweeps:
            sched_parts.append(f"{s.test_sweeps} test sweeps")
        if sched_parts:
            lines.append(f"Scheduled: {', '.join(sched_parts)}")

        # Buffered events by category
        if self._buffer:
            lines.append("")
            by_cat: dict[str, list[str]] = {}
            for n in self._buffer:
                by_cat.setdefault(n.category, []).append(n.message)

            for cat, messages in sorted(by_cat.items()):
                lines.append(f"{cat}:")
                for msg in messages[-5:]:  # Last 5 per category
                    lines.append(f"  - {msg}")
                if len(messages) > 5:
                    lines.append(f"  ... and {len(messages) - 5} more")

        return "\n".join(lines)

    @property
    def buffer_size(self) -> int:
        """Number of buffered notifications."""
        return len(self._buffer)
