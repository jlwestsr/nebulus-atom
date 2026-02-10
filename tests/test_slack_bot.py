"""Tests for Overlord Slack Bot."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nebulus_swarm.overlord.slack_bot import SlackBot


@pytest.fixture
def mock_slack_bot() -> SlackBot:
    """Create a SlackBot with mocked Slack app."""
    with patch("nebulus_swarm.overlord.slack_bot.AsyncApp") as MockApp:
        mock_app = MagicMock()
        mock_app.event = MagicMock(return_value=lambda f: f)
        MockApp.return_value = mock_app

        bot = SlackBot(
            bot_token="xoxb-test",
            app_token="xapp-test",
            channel_id="C123",
        )
        bot.app = mock_app
        return bot


class TestGetThreadHistory:
    """Tests for get_thread_history method."""

    @pytest.mark.asyncio
    async def test_returns_human_replies(self, mock_slack_bot: SlackBot) -> None:
        mock_slack_bot.app.client.conversations_replies = AsyncMock(
            return_value={
                "messages": [
                    {"user": "U123", "text": "Original post", "ts": "1000.0000"},
                    {
                        "user": "U456",
                        "text": "approve",
                        "ts": "1000.1000",
                    },
                    {
                        "bot_id": "B789",
                        "text": "Bot reply",
                        "ts": "1000.2000",
                    },
                    {"user": "U789", "text": "deny", "ts": "1000.3000"},
                ]
            }
        )

        replies = await mock_slack_bot.get_thread_history("1000.0000")
        assert len(replies) == 3  # 3 human messages, 1 bot filtered out
        assert replies[0]["user"] == "U123"
        assert replies[1]["text"] == "approve"
        assert replies[2]["text"] == "deny"

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self, mock_slack_bot: SlackBot) -> None:
        mock_slack_bot.app.client.conversations_replies = AsyncMock(
            side_effect=RuntimeError("API failure")
        )

        replies = await mock_slack_bot.get_thread_history("1000.0000")
        assert replies == []
