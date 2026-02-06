"""Tests for Overlord Notification Manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nebulus_swarm.overlord.notifications import (
    DigestStats,
    Notification,
    NotificationManager,
)


# --- Notification Dataclass Tests ---


class TestNotification:
    """Tests for the Notification dataclass."""

    def test_creates_with_timestamp(self) -> None:
        n = Notification(category="test", message="hello")
        assert n.timestamp  # Auto-generated
        assert n.category == "test"
        assert n.message == "hello"

    def test_custom_timestamp(self) -> None:
        n = Notification(
            category="test", message="hello", timestamp="2026-02-06T00:00:00"
        )
        assert n.timestamp == "2026-02-06T00:00:00"


# --- Urgent Notification Tests ---


class TestUrgentNotifications:
    """Tests for immediate notification sending."""

    @pytest.mark.asyncio
    async def test_send_urgent_with_slack(self) -> None:
        mock_bot = MagicMock()
        mock_bot.post_message = AsyncMock()
        mgr = NotificationManager(slack_bot=mock_bot)

        await mgr.send_urgent("alert!")
        mock_bot.post_message.assert_called_once_with("alert!")

    @pytest.mark.asyncio
    async def test_send_urgent_without_slack(self) -> None:
        mgr = NotificationManager()
        # Should not raise
        await mgr.send_urgent("alert!")

    @pytest.mark.asyncio
    async def test_send_urgent_disabled(self) -> None:
        mock_bot = MagicMock()
        mock_bot.post_message = AsyncMock()
        mgr = NotificationManager(slack_bot=mock_bot, urgent_enabled=False)

        await mgr.send_urgent("suppressed")
        mock_bot.post_message.assert_not_called()


# --- Accumulation Tests ---


class TestAccumulation:
    """Tests for buffering notifications for digest."""

    def test_accumulate_adds_to_buffer(self) -> None:
        mgr = NotificationManager()
        mgr.accumulate("detection", "stale branch found")
        assert mgr.buffer_size == 1

    def test_accumulate_multiple(self) -> None:
        mgr = NotificationManager()
        mgr.accumulate("detection", "finding 1")
        mgr.accumulate("execution", "task done")
        mgr.accumulate("proposal_created", "new proposal")
        assert mgr.buffer_size == 3

    def test_accumulate_updates_stats(self) -> None:
        mgr = NotificationManager()
        mgr.accumulate("detection", "d1")
        mgr.accumulate("detection", "d2")
        mgr.accumulate("proposal_created", "p1")
        mgr.accumulate("proposal_approved", "p2")
        mgr.accumulate("execution", "e1")
        mgr.accumulate("health_check", "h1")
        mgr.accumulate("test_sweep", "t1")

        assert mgr.stats.detections == 2
        assert mgr.stats.proposals_created == 1
        assert mgr.stats.proposals_approved == 1
        assert mgr.stats.executions == 1
        assert mgr.stats.health_checks == 1
        assert mgr.stats.test_sweeps == 1

    def test_unknown_category_still_buffers(self) -> None:
        mgr = NotificationManager()
        mgr.accumulate("unknown", "something")
        assert mgr.buffer_size == 1


# --- Digest Tests ---


class TestDigest:
    """Tests for daily digest formatting and sending."""

    @pytest.mark.asyncio
    async def test_send_digest_with_data(self) -> None:
        mock_bot = MagicMock()
        mock_bot.post_message = AsyncMock()
        mgr = NotificationManager(slack_bot=mock_bot)

        mgr.accumulate("detection", "stale branch in core")
        mgr.accumulate("health_check", "scan passed")
        mgr.accumulate("execution", "merge completed")

        await mgr.send_digest()
        mock_bot.post_message.assert_called_once()
        msg = mock_bot.post_message.call_args[0][0]
        assert "Daily Digest" in msg
        assert "1 detections" in msg
        assert "1 executed" in msg

    @pytest.mark.asyncio
    async def test_send_digest_clears_buffer(self) -> None:
        mgr = NotificationManager()
        mgr.accumulate("detection", "finding")
        assert mgr.buffer_size == 1

        await mgr.send_digest()
        assert mgr.buffer_size == 0
        assert mgr.stats.detections == 0

    @pytest.mark.asyncio
    async def test_send_digest_empty_no_send(self) -> None:
        mock_bot = MagicMock()
        mock_bot.post_message = AsyncMock()
        mgr = NotificationManager(slack_bot=mock_bot)

        await mgr.send_digest()
        mock_bot.post_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_digest_disabled(self) -> None:
        mock_bot = MagicMock()
        mock_bot.post_message = AsyncMock()
        mgr = NotificationManager(slack_bot=mock_bot, digest_enabled=False)

        mgr.accumulate("detection", "finding")
        await mgr.send_digest()
        mock_bot.post_message.assert_not_called()

    def test_format_digest_categories(self) -> None:
        mgr = NotificationManager()
        mgr.accumulate("detection", "stale branch")
        mgr.accumulate("detection", "ahead of main")
        mgr.accumulate("execution", "merge done")

        digest = mgr._format_digest()
        assert "detection:" in digest
        assert "execution:" in digest
        assert "stale branch" in digest

    def test_format_digest_truncates_long_lists(self) -> None:
        mgr = NotificationManager()
        for i in range(10):
            mgr.accumulate("detection", f"finding {i}")

        digest = mgr._format_digest()
        assert "and 5 more" in digest

    def test_format_digest_date(self) -> None:
        mgr = NotificationManager()
        mgr.accumulate("health_check", "scan")
        digest = mgr._format_digest()
        assert "Daily Digest" in digest
        assert "2026" in digest  # Current year


# --- DigestStats Tests ---


class TestDigestStats:
    """Tests for DigestStats dataclass."""

    def test_defaults_to_zero(self) -> None:
        stats = DigestStats()
        assert stats.health_checks == 0
        assert stats.detections == 0
        assert stats.proposals_created == 0
        assert stats.proposals_approved == 0
        assert stats.proposals_denied == 0
        assert stats.executions == 0
        assert stats.test_sweeps == 0


# --- Integration Tests ---


class TestNotificationIntegration:
    """Tests for notification manager with daemon-like usage."""

    @pytest.mark.asyncio
    async def test_mixed_urgent_and_buffered(self) -> None:
        mock_bot = MagicMock()
        mock_bot.post_message = AsyncMock()
        mgr = NotificationManager(slack_bot=mock_bot)

        # Urgent sends immediately
        await mgr.send_urgent("CRITICAL: test failure")
        assert mock_bot.post_message.call_count == 1

        # Buffered accumulates
        mgr.accumulate("detection", "stale branch")
        mgr.accumulate("health_check", "scan ok")
        assert mock_bot.post_message.call_count == 1  # No new calls

        # Digest sends accumulated
        await mgr.send_digest()
        assert mock_bot.post_message.call_count == 2  # +1 for digest

    @pytest.mark.asyncio
    async def test_multiple_digest_cycles(self) -> None:
        mgr = NotificationManager()

        # First cycle
        mgr.accumulate("detection", "d1")
        await mgr.send_digest()
        assert mgr.buffer_size == 0

        # Second cycle
        mgr.accumulate("execution", "e1")
        assert mgr.buffer_size == 1
        assert mgr.stats.executions == 1
