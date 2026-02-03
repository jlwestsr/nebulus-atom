"""Heartbeat and status reporter for Minion → Overlord communication."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events reported to Overlord."""

    HEARTBEAT = "heartbeat"
    PROGRESS = "progress"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ReportPayload:
    """Payload sent to Overlord."""

    minion_id: str
    event: EventType
    issue: int
    message: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "minion_id": self.minion_id,
            "event": self.event.value,
            "issue": self.issue,
            "message": self.message,
            "data": self.data,
            "timestamp": datetime.now().isoformat(),
        }


class Reporter:
    """Handles communication with the Overlord."""

    def __init__(
        self,
        minion_id: str,
        issue_number: int,
        callback_url: str,
        heartbeat_interval: int = 60,
    ):
        """Initialize reporter.

        Args:
            minion_id: Unique identifier for this Minion.
            issue_number: GitHub issue being worked on.
            callback_url: Overlord endpoint URL.
            heartbeat_interval: Seconds between heartbeats.
        """
        self.minion_id = minion_id
        self.issue_number = issue_number
        self.callback_url = callback_url
        self.heartbeat_interval = heartbeat_interval

        self._session: Optional[aiohttp.ClientSession] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._current_status: str = "initializing"
        self._running = False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def _send_report(self, payload: ReportPayload) -> bool:
        """Send a report to the Overlord.

        Args:
            payload: Report payload to send.

        Returns:
            True if sent successfully.
        """
        try:
            session = await self._get_session()
            async with session.post(
                self.callback_url,
                json=payload.to_dict(),
            ) as response:
                if response.status == 200:
                    logger.debug(f"Reported {payload.event.value}: {payload.message}")
                    return True
                else:
                    logger.warning(
                        f"Report failed with status {response.status}: "
                        f"{await response.text()}"
                    )
                    return False
        except aiohttp.ClientError as e:
            logger.error(f"Failed to send report: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending report: {e}")
            return False

    async def _heartbeat_loop(self) -> None:
        """Background task that sends periodic heartbeats."""
        while self._running:
            await self.heartbeat(self._current_status)
            await asyncio.sleep(self.heartbeat_interval)

    async def start(self) -> None:
        """Start the heartbeat background task."""
        if self._running:
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Reporter started (interval={self.heartbeat_interval}s)")

    async def stop(self) -> None:
        """Stop the heartbeat task and close session."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._session and not self._session.closed:
            await self._session.close()

        logger.info("Reporter stopped")

    def update_status(self, status: str) -> None:
        """Update the current status for heartbeats.

        Args:
            status: Current activity description.
        """
        self._current_status = status

    async def heartbeat(self, message: str = "working") -> bool:
        """Send a heartbeat to Overlord.

        Args:
            message: Current status message.

        Returns:
            True if sent successfully.
        """
        payload = ReportPayload(
            minion_id=self.minion_id,
            event=EventType.HEARTBEAT,
            issue=self.issue_number,
            message=message,
        )
        return await self._send_report(payload)

    async def progress(
        self, message: str, data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Report progress on the task.

        Args:
            message: Progress description.
            data: Optional additional data.

        Returns:
            True if sent successfully.
        """
        self._current_status = message
        payload = ReportPayload(
            minion_id=self.minion_id,
            event=EventType.PROGRESS,
            issue=self.issue_number,
            message=message,
            data=data or {},
        )
        return await self._send_report(payload)

    async def complete(
        self,
        message: str = "completed",
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
        branch: Optional[str] = None,
        review_summary: Optional[str] = None,
    ) -> bool:
        """Report successful completion.

        Args:
            message: Completion message.
            pr_number: Created PR number.
            pr_url: Created PR URL.
            branch: Branch name.
            review_summary: Summary of automated PR review.

        Returns:
            True if sent successfully.
        """
        data = {}
        if pr_number:
            data["pr_number"] = pr_number
        if pr_url:
            data["pr_url"] = pr_url
        if branch:
            data["branch"] = branch
        if review_summary:
            data["review_summary"] = review_summary

        payload = ReportPayload(
            minion_id=self.minion_id,
            event=EventType.COMPLETE,
            issue=self.issue_number,
            message=message,
            data=data,
        )
        return await self._send_report(payload)

    async def error(
        self,
        message: str,
        error_type: Optional[str] = None,
        details: Optional[str] = None,
    ) -> bool:
        """Report an error.

        Args:
            message: Error summary.
            error_type: Type of error (e.g., 'timeout', 'git_error').
            details: Detailed error information.

        Returns:
            True if sent successfully.
        """
        data = {}
        if error_type:
            data["error_type"] = error_type
        if details:
            data["details"] = details

        payload = ReportPayload(
            minion_id=self.minion_id,
            event=EventType.ERROR,
            issue=self.issue_number,
            message=message,
            data=data,
        )
        return await self._send_report(payload)
