"""Slack Bot integration for Overlord using Slack Bolt."""

import logging
from typing import Callable, Optional

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)


class SlackBot:
    """Slack bot for Overlord communication."""

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        channel_id: str,
        message_handler: Optional[Callable[[str, str], str]] = None,
    ):
        """Initialize Slack bot.

        Args:
            bot_token: Slack bot OAuth token (xoxb-...).
            app_token: Slack app-level token for Socket Mode (xapp-...).
            channel_id: Channel ID to monitor and post to.
            message_handler: Callback for processing messages.
                            Takes (user_id, message_text) and returns response.
        """
        self.bot_token = bot_token
        self.app_token = app_token
        self.channel_id = channel_id
        self.message_handler = message_handler

        # Initialize Slack Bolt app
        self.app = AsyncApp(token=bot_token)
        self._setup_handlers()

        self._handler: Optional[AsyncSocketModeHandler] = None

    def _setup_handlers(self) -> None:
        """Set up Slack event handlers."""

        @self.app.event("message")
        async def handle_message(event: dict, say: Callable) -> None:
            """Handle incoming messages."""
            # Ignore bot's own messages
            if event.get("bot_id"):
                return

            # Only respond in configured channel
            if event.get("channel") != self.channel_id:
                return

            user = event.get("user", "unknown")
            text = event.get("text", "").strip()

            if not text:
                return

            logger.info(f"Received message from {user}: {text}")

            # Handle ping as a special case
            if text.lower() == "ping":
                await say("pong 🏓")
                return

            # Forward to message handler if configured
            if self.message_handler:
                try:
                    response = self.message_handler(user, text)
                    if response:
                        await say(response)
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    await say(f"❌ Error processing command: {e}")
            else:
                await say(
                    "👋 Overlord is running, but no command handler is configured."
                )

        @self.app.event("app_mention")
        async def handle_mention(event: dict, say: Callable) -> None:
            """Handle @mentions of the bot."""
            user = event.get("user", "unknown")
            text = event.get("text", "").strip()

            # Remove the mention from the text
            # Format is usually "<@BOT_ID> message"
            if " " in text:
                text = text.split(" ", 1)[1].strip()

            logger.info(f"Mentioned by {user}: {text}")

            if self.message_handler:
                try:
                    response = self.message_handler(user, text)
                    if response:
                        await say(response)
                except Exception as e:
                    logger.error(f"Error handling mention: {e}")
                    await say(f"❌ Error: {e}")

    async def start(self) -> None:
        """Start the Slack bot in Socket Mode."""
        logger.info("Starting Slack bot in Socket Mode...")
        self._handler = AsyncSocketModeHandler(self.app, self.app_token)
        await self._handler.start_async()

    async def stop(self) -> None:
        """Stop the Slack bot."""
        if self._handler:
            logger.info("Stopping Slack bot...")
            await self._handler.close_async()

    async def post_message(self, text: str, thread_ts: Optional[str] = None) -> None:
        """Post a message to the configured channel.

        Args:
            text: Message text to post.
            thread_ts: Optional thread timestamp to reply in a thread.
        """
        try:
            await self.app.client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                thread_ts=thread_ts,
            )
        except Exception as e:
            logger.error(f"Failed to post message: {e}")

    async def post_minion_update(
        self,
        minion_id: str,
        issue_number: int,
        status: str,
        details: Optional[str] = None,
    ) -> None:
        """Post a minion status update.

        Args:
            minion_id: Minion identifier.
            issue_number: GitHub issue number.
            status: Status emoji and text (e.g., "🚀 Starting").
            details: Optional additional details.
        """
        message = f"{status} Minion `{minion_id}` on #{issue_number}"
        if details:
            message += f"\n> {details}"

        await self.post_message(message)


async def test_connection(bot_token: str, app_token: str) -> bool:
    """Test Slack connection without starting the full bot.

    Args:
        bot_token: Slack bot OAuth token.
        app_token: Slack app-level token.

    Returns:
        True if connection successful, False otherwise.
    """
    try:
        app = AsyncApp(token=bot_token)
        response = await app.client.auth_test()
        logger.info(f"Connected to Slack as: {response['user']}")
        return True
    except Exception as e:
        logger.error(f"Slack connection test failed: {e}")
        return False
