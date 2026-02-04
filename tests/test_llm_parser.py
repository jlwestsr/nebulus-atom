"""Tests for LLM-powered command parser."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

pytest.importorskip("openai")

from nebulus_swarm.config import OverlordLLMConfig
from nebulus_swarm.overlord.command_parser import Command, CommandType
from nebulus_swarm.overlord.llm_parser import (
    ContextStore,
    ConversationEntry,
    LLMCommandParser,
    LLMParseResult,
    ParseResult,
)


class TestConversationEntry:
    """Tests for ConversationEntry."""

    def test_format_for_prompt_just_now(self):
        """Test formatting for recent message."""
        entry = ConversationEntry(
            timestamp=datetime.now(),
            user_id="user123",
            message="work on #42",
            parsed_command=Command(
                type=CommandType.WORK,
                issue_number=42,
                raw_text="work on #42",
            ),
        )
        formatted = entry.format_for_prompt()
        assert "just now" in formatted
        assert "user123" in formatted
        assert "work on #42" in formatted
        assert "WORK" in formatted
        assert "#42" in formatted

    def test_format_for_prompt_minutes_ago(self):
        """Test formatting for older message."""
        entry = ConversationEntry(
            timestamp=datetime.now() - timedelta(minutes=5),
            user_id="user456",
            message="status",
            parsed_command=Command(type=CommandType.STATUS, raw_text="status"),
        )
        formatted = entry.format_for_prompt()
        assert "5 min ago" in formatted
        assert "STATUS" in formatted

    def test_format_for_prompt_no_command(self):
        """Test formatting when command parsing failed."""
        entry = ConversationEntry(
            timestamp=datetime.now(),
            user_id="user789",
            message="hello there",
            parsed_command=None,
        )
        formatted = entry.format_for_prompt()
        assert "hello there" in formatted
        assert "→" not in formatted  # No command indicator


class TestContextStore:
    """Tests for ContextStore."""

    def test_add_and_get_history(self):
        """Test adding entries and retrieving history."""
        store = ContextStore(max_entries=10, ttl_minutes=30)

        store.add("channel1", "user1", "hello", None)
        store.add("channel1", "user2", "work on #42", Command(type=CommandType.WORK))

        history = store.get_history("channel1")
        assert len(history) == 2
        assert history[0].message == "hello"
        assert history[1].message == "work on #42"

    def test_channel_isolation(self):
        """Test that channels are isolated."""
        store = ContextStore()

        store.add("channel1", "user1", "msg1", None)
        store.add("channel2", "user1", "msg2", None)

        assert len(store.get_history("channel1")) == 1
        assert len(store.get_history("channel2")) == 1
        assert store.get_history("channel1")[0].message == "msg1"
        assert store.get_history("channel2")[0].message == "msg2"

    def test_max_entries_enforced(self):
        """Test that max entries limit is enforced."""
        store = ContextStore(max_entries=3, ttl_minutes=30)

        for i in range(5):
            store.add("channel1", "user1", f"msg{i}", None)

        history = store.get_history("channel1")
        assert len(history) == 3
        # Should keep the most recent 3
        assert history[0].message == "msg2"
        assert history[1].message == "msg3"
        assert history[2].message == "msg4"

    def test_ttl_expiry(self):
        """Test that old messages are pruned."""
        store = ContextStore(max_entries=10, ttl_minutes=1)

        # Add an old entry by manipulating the timestamp
        old_entry = ConversationEntry(
            timestamp=datetime.now() - timedelta(minutes=5),
            user_id="user1",
            message="old message",
            parsed_command=None,
        )
        store._contexts["channel1"] = [old_entry]

        # Add a new entry
        store.add("channel1", "user1", "new message", None)

        history = store.get_history("channel1")
        assert len(history) == 1
        assert history[0].message == "new message"

    def test_get_last_command(self):
        """Test getting the most recent successful command."""
        store = ContextStore()

        store.add("channel1", "user1", "hello", None)
        store.add(
            "channel1",
            "user1",
            "work on #42",
            Command(type=CommandType.WORK, issue_number=42),
        )
        store.add("channel1", "user1", "status", Command(type=CommandType.STATUS))

        last_cmd = store.get_last_command("channel1")
        assert last_cmd is not None
        assert last_cmd.type == CommandType.STATUS

    def test_get_last_command_skips_unknown(self):
        """Test that UNKNOWN commands are skipped."""
        store = ContextStore()

        store.add(
            "channel1",
            "user1",
            "work on #42",
            Command(type=CommandType.WORK, issue_number=42),
        )
        store.add(
            "channel1",
            "user1",
            "gibberish",
            Command(type=CommandType.UNKNOWN),
        )

        last_cmd = store.get_last_command("channel1")
        assert last_cmd is not None
        assert last_cmd.type == CommandType.WORK
        assert last_cmd.issue_number == 42

    def test_get_last_command_empty_channel(self):
        """Test getting last command from empty channel."""
        store = ContextStore()
        assert store.get_last_command("nonexistent") is None

    def test_clear_channel(self):
        """Test clearing a channel's context."""
        store = ContextStore()

        store.add("channel1", "user1", "msg1", None)
        store.add("channel1", "user1", "msg2", None)

        store.clear("channel1")

        assert len(store.get_history("channel1")) == 0


class TestParseResult:
    """Tests for ParseResult."""

    def test_success_with_command(self):
        """Test successful parse result."""
        result = ParseResult(command=Command(type=CommandType.STATUS))
        assert result.success is True
        assert result.needs_clarification is False

    def test_needs_clarification(self):
        """Test clarification request."""
        result = ParseResult(
            needs_clarification=True,
            clarification_message="Which PR?",
        )
        assert result.success is False
        assert result.needs_clarification is True
        assert result.clarification_message == "Which PR?"

    def test_no_command_is_failure(self):
        """Test that missing command is failure."""
        result = ParseResult(command=None)
        assert result.success is False


class TestLLMCommandParser:
    """Tests for LLMCommandParser."""

    def test_init_with_config(self):
        """Test parser initialization."""
        config = OverlordLLMConfig(
            enabled=True,
            model="test-model",
            timeout=10.0,
            confidence_threshold=0.8,
        )
        parser = LLMCommandParser(config=config, default_repo="owner/repo")

        assert parser.default_repo == "owner/repo"
        assert parser.config.model == "test-model"
        assert parser.config.confidence_threshold == 0.8

    @pytest.mark.asyncio
    async def test_parse_with_llm_disabled(self):
        """Test that disabled LLM falls back to regex."""
        config = OverlordLLMConfig(enabled=False)
        parser = LLMCommandParser(config=config, default_repo="owner/repo")

        result = await parser.parse("work on #42", "channel1", "user1")

        assert result.success is True
        assert result.command.type == CommandType.WORK
        assert result.command.issue_number == 42

    @pytest.mark.asyncio
    async def test_parse_regex_fallback_on_error(self):
        """Test regex fallback when LLM fails."""
        config = OverlordLLMConfig(enabled=True, timeout=0.1)
        parser = LLMCommandParser(config=config, default_repo="owner/repo")

        # Mock the LLM client to raise an error
        with patch.object(parser, "_llm_parse", side_effect=Exception("LLM error")):
            result = await parser.parse("status", "channel1", "user1")

        assert result.success is True
        assert result.command.type == CommandType.STATUS

    @pytest.mark.asyncio
    async def test_parse_regex_fallback_on_timeout(self):
        """Test regex fallback when LLM times out."""
        config = OverlordLLMConfig(enabled=True, timeout=0.01)
        parser = LLMCommandParser(config=config, default_repo="owner/repo")

        # Mock slow LLM
        async def slow_parse(*args):
            await asyncio.sleep(1)
            return LLMParseResult()

        with patch.object(parser, "_llm_parse", side_effect=slow_parse):
            result = await parser.parse("queue", "channel1", "user1")

        assert result.success is True
        assert result.command.type == CommandType.QUEUE

    @pytest.mark.asyncio
    async def test_parse_high_confidence_llm(self):
        """Test successful LLM parse with high confidence."""
        config = OverlordLLMConfig(
            enabled=True,
            confidence_threshold=0.7,
        )
        parser = LLMCommandParser(config=config, default_repo="owner/repo")

        # Mock LLM response
        async def mock_parse(*args):
            return LLMParseResult(
                command="WORK",
                issue_number=42,
                confidence=0.95,
            )

        with patch.object(parser, "_llm_parse", side_effect=mock_parse):
            result = await parser.parse(
                "hey can you start on issue 42", "channel1", "user1"
            )

        assert result.success is True
        assert result.command.type == CommandType.WORK
        assert result.command.issue_number == 42

    @pytest.mark.asyncio
    async def test_parse_low_confidence_with_clarification(self):
        """Test LLM parse with low confidence returns clarification."""
        config = OverlordLLMConfig(
            enabled=True,
            confidence_threshold=0.7,
        )
        parser = LLMCommandParser(config=config, default_repo="owner/repo")

        # Mock LLM response with low confidence and clarification
        async def mock_parse(*args):
            return LLMParseResult(
                command="UNKNOWN",
                confidence=0.4,
                clarification="Which PR would you like me to review?",
            )

        with patch.object(parser, "_llm_parse", side_effect=mock_parse):
            result = await parser.parse("check the PR", "channel1", "user1")

        assert result.success is False
        assert result.needs_clarification is True
        assert "PR" in result.clarification_message

    @pytest.mark.asyncio
    async def test_parse_low_confidence_no_clarification_fallback(self):
        """Test that low confidence without clarification falls back to regex."""
        config = OverlordLLMConfig(
            enabled=True,
            confidence_threshold=0.7,
        )
        parser = LLMCommandParser(config=config, default_repo="owner/repo")

        # Mock LLM response with low confidence but no clarification
        async def mock_parse(*args):
            return LLMParseResult(
                command="UNKNOWN",
                confidence=0.3,
                clarification=None,
            )

        with patch.object(parser, "_llm_parse", side_effect=mock_parse):
            result = await parser.parse("status", "channel1", "user1")

        # Should fall back to regex which will parse "status"
        assert result.success is True
        assert result.command.type == CommandType.STATUS

    def test_parse_llm_response_valid_json(self):
        """Test parsing valid LLM JSON response."""
        config = OverlordLLMConfig()
        parser = LLMCommandParser(config=config)

        content = '{"command": "WORK", "issue_number": 42, "confidence": 0.9}'
        result = parser._parse_llm_response(content)

        assert result.command == "WORK"
        assert result.issue_number == 42
        assert result.confidence == 0.9

    def test_parse_llm_response_with_markdown(self):
        """Test parsing LLM response with markdown code block."""
        config = OverlordLLMConfig()
        parser = LLMCommandParser(config=config)

        content = """```json
{"command": "STATUS", "confidence": 0.85}
```"""
        result = parser._parse_llm_response(content)

        assert result.command == "STATUS"
        assert result.confidence == 0.85

    def test_parse_llm_response_invalid_json(self):
        """Test handling invalid JSON in LLM response."""
        config = OverlordLLMConfig()
        parser = LLMCommandParser(config=config)

        content = "This is not JSON at all"
        result = parser._parse_llm_response(content)

        assert result.confidence == 0.0

    def test_llm_result_to_command(self):
        """Test converting LLMParseResult to Command."""
        config = OverlordLLMConfig()
        parser = LLMCommandParser(config=config, default_repo="default/repo")

        llm_result = LLMParseResult(
            command="WORK",
            issue_number=42,
            repo="custom/repo",
            confidence=0.9,
        )
        command = parser._llm_result_to_command(llm_result, "work on custom/repo#42")

        assert command.type == CommandType.WORK
        assert command.issue_number == 42
        assert command.repo == "custom/repo"
        assert command.raw_text == "work on custom/repo#42"

    def test_llm_result_to_command_uses_default_repo(self):
        """Test that default repo is used when not specified."""
        config = OverlordLLMConfig()
        parser = LLMCommandParser(config=config, default_repo="default/repo")

        llm_result = LLMParseResult(
            command="WORK",
            issue_number=42,
            repo=None,
            confidence=0.9,
        )
        command = parser._llm_result_to_command(llm_result, "work on #42")

        assert command.repo == "default/repo"

    def test_llm_result_to_command_unknown_type(self):
        """Test handling unknown command type."""
        config = OverlordLLMConfig()
        parser = LLMCommandParser(config=config)

        llm_result = LLMParseResult(
            command="INVALID_COMMAND",
            confidence=0.5,
        )
        command = parser._llm_result_to_command(llm_result, "something weird")

        assert command.type == CommandType.UNKNOWN

    def test_format_help(self):
        """Test that help formatting delegates to regex parser."""
        config = OverlordLLMConfig()
        parser = LLMCommandParser(config=config)

        help_text = parser.format_help()
        assert "status" in help_text.lower()
        assert "work" in help_text.lower()

    @pytest.mark.asyncio
    async def test_context_is_stored(self):
        """Test that messages are stored in context."""
        config = OverlordLLMConfig(enabled=False)  # Use regex to avoid mocking
        parser = LLMCommandParser(config=config, default_repo="owner/repo")

        await parser.parse("status", "channel1", "user1")
        await parser.parse("work on #42", "channel1", "user1")

        history = parser.context.get_history("channel1")
        assert len(history) == 2
        assert history[0].message == "status"
        assert history[1].message == "work on #42"
