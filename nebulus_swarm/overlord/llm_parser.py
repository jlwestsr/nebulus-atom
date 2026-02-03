"""LLM-powered command parser for Overlord."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from openai import AsyncOpenAI

from nebulus_swarm.config import OverlordLLMConfig
from nebulus_swarm.overlord.command_parser import Command, CommandParser, CommandType

logger = logging.getLogger(__name__)


@dataclass
class ConversationEntry:
    """Single message in conversation history."""

    timestamp: datetime
    user_id: str
    message: str
    parsed_command: Optional[Command] = None

    def format_for_prompt(self) -> str:
        """Format entry for LLM prompt context."""
        age = datetime.now() - self.timestamp
        if age.total_seconds() < 60:
            age_str = "just now"
        elif age.total_seconds() < 3600:
            age_str = f"{int(age.total_seconds() / 60)} min ago"
        else:
            age_str = f"{int(age.total_seconds() / 3600)} hr ago"

        cmd_str = ""
        if self.parsed_command and self.parsed_command.type != CommandType.UNKNOWN:
            cmd_str = f" → {self.parsed_command.type.value.upper()}"
            if self.parsed_command.issue_number:
                cmd_str += f" #{self.parsed_command.issue_number}"
            elif self.parsed_command.pr_number:
                cmd_str += f" PR#{self.parsed_command.pr_number}"

        return f'[{age_str}] {self.user_id}: "{self.message}"{cmd_str}'


class ContextStore:
    """In-memory conversation context per channel."""

    def __init__(self, max_entries: int = 10, ttl_minutes: int = 30):
        """Initialize context store.

        Args:
            max_entries: Maximum messages to keep per channel.
            ttl_minutes: Time-to-live for messages in minutes.
        """
        self.max_entries = max_entries
        self.ttl_minutes = ttl_minutes
        self._contexts: Dict[str, List[ConversationEntry]] = {}

    def add(
        self,
        channel_id: str,
        user_id: str,
        message: str,
        command: Optional[Command] = None,
    ) -> None:
        """Store a message and its parsed result.

        Args:
            channel_id: Slack channel ID.
            user_id: User who sent the message.
            message: Raw message text.
            command: Parsed command result (if any).
        """
        if channel_id not in self._contexts:
            self._contexts[channel_id] = []

        entry = ConversationEntry(
            timestamp=datetime.now(),
            user_id=user_id,
            message=message,
            parsed_command=command,
        )

        self._contexts[channel_id].append(entry)

        # Prune old entries
        self._prune(channel_id)

    def get_history(self, channel_id: str) -> List[ConversationEntry]:
        """Get recent messages for context, pruning expired entries.

        Args:
            channel_id: Slack channel ID.

        Returns:
            List of recent conversation entries.
        """
        if channel_id not in self._contexts:
            return []

        self._prune(channel_id)
        return self._contexts[channel_id].copy()

    def get_last_command(self, channel_id: str) -> Optional[Command]:
        """Get the most recent successful command.

        Args:
            channel_id: Slack channel ID.

        Returns:
            Last successful command or None.
        """
        history = self.get_history(channel_id)
        for entry in reversed(history):
            if (
                entry.parsed_command
                and entry.parsed_command.type != CommandType.UNKNOWN
            ):
                return entry.parsed_command
        return None

    def clear(self, channel_id: str) -> None:
        """Clear context for a channel.

        Args:
            channel_id: Slack channel ID.
        """
        if channel_id in self._contexts:
            del self._contexts[channel_id]

    def _prune(self, channel_id: str) -> None:
        """Remove expired and excess entries.

        Args:
            channel_id: Slack channel ID.
        """
        if channel_id not in self._contexts:
            return

        cutoff = datetime.now() - timedelta(minutes=self.ttl_minutes)

        # Remove expired
        self._contexts[channel_id] = [
            e for e in self._contexts[channel_id] if e.timestamp > cutoff
        ]

        # Trim to max entries
        if len(self._contexts[channel_id]) > self.max_entries:
            self._contexts[channel_id] = self._contexts[channel_id][-self.max_entries :]


@dataclass
class LLMParseResult:
    """Result from LLM parsing attempt."""

    command: str = "UNKNOWN"
    issue_number: Optional[int] = None
    pr_number: Optional[int] = None
    repo: Optional[str] = None
    minion_id: Optional[str] = None
    confidence: float = 0.0
    clarification: Optional[str] = None


@dataclass
class ParseResult:
    """Final parse result returned to caller."""

    command: Optional[Command] = None
    needs_clarification: bool = False
    clarification_message: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if parsing succeeded."""
        return self.command is not None and not self.needs_clarification


SYSTEM_PROMPT_TEMPLATE = '''You are the Nebulus Overlord's command interpreter. Parse user messages into structured commands.

## Available Commands

1. STATUS - Check what minions are doing
2. WORK - Start a minion on an issue (requires: issue_number, optional: repo)
3. STOP - Stop a minion (requires: issue_number OR minion_id)
4. QUEUE - Show pending work
5. PAUSE - Pause automatic processing
6. RESUME - Resume automatic processing
7. HISTORY - Show recent completed work
8. REVIEW - Review a PR (requires: pr_number, optional: repo)
9. HELP - Show available commands

## Response Format

Respond with JSON only, no other text:
{{"command": "WORK", "issue_number": 42, "repo": null, "confidence": 0.95}}

Fields:
- command: One of the command names above, or "UNKNOWN"
- issue_number: Integer if applicable, null otherwise
- pr_number: Integer if applicable, null otherwise
- repo: String "owner/repo" if specified, null to use default
- minion_id: String if stopping a specific minion, null otherwise
- confidence: Float 0.0-1.0 indicating certainty
- clarification: String with question if confidence < 0.7

## Context

Default repo: {default_repo}

{conversation_history}

## Examples

User: "hey can you start working on issue 42"
{{"command": "WORK", "issue_number": 42, "confidence": 0.95}}

User: "do the same for 43" (after working on 42)
{{"command": "WORK", "issue_number": 43, "confidence": 0.90}}

User: "what's up"
{{"command": "STATUS", "confidence": 0.85}}

User: "stop that" (after starting work on #42)
{{"command": "STOP", "issue_number": 42, "confidence": 0.85}}

User: "take a look at the PR"
{{"command": "UNKNOWN", "confidence": 0.3, "clarification": "Which PR would you like me to review? Please specify a number like 'review PR #42'"}}

Now parse this message:
User: "{message}"'''


class LLMCommandParser:
    """LLM-powered command parser with context and fallback."""

    def __init__(
        self,
        config: OverlordLLMConfig,
        default_repo: Optional[str] = None,
    ):
        """Initialize parser.

        Args:
            config: LLM configuration.
            default_repo: Default repository for commands.
        """
        self.config = config
        self.default_repo = default_repo

        # LLM client
        self._client: Optional[AsyncOpenAI] = None

        # Context store
        self.context = ContextStore(
            max_entries=config.context_max_entries,
            ttl_minutes=config.context_ttl_minutes,
        )

        # Regex fallback
        self._regex_parser = CommandParser(default_repo=default_repo)

    @property
    def client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.config.base_url,
                api_key="not-needed",
                timeout=self.config.timeout,
            )
        return self._client

    async def parse(
        self,
        text: str,
        channel_id: str,
        user_id: str,
    ) -> ParseResult:
        """Parse a message into a Command.

        Args:
            text: Raw message text.
            channel_id: Slack channel ID for context.
            user_id: User ID for context.

        Returns:
            ParseResult with command or clarification request.
        """
        # If LLM disabled, use regex directly
        if not self.config.enabled:
            command = self._regex_parser.parse(text)
            self.context.add(channel_id, user_id, text, command)
            return ParseResult(command=command)

        try:
            # Try LLM with timeout
            llm_result = await asyncio.wait_for(
                self._llm_parse(text, channel_id),
                timeout=self.config.timeout,
            )

            # Convert to Command
            command = self._llm_result_to_command(llm_result, text)

            # Check confidence
            if llm_result.confidence >= self.config.confidence_threshold:
                self.context.add(channel_id, user_id, text, command)
                return ParseResult(command=command)

            # Low confidence - check for clarification
            if llm_result.clarification:
                # Still store the attempt for context
                self.context.add(channel_id, user_id, text, None)
                return ParseResult(
                    needs_clarification=True,
                    clarification_message=llm_result.clarification,
                )

            # Low confidence, no clarification - try regex
            logger.debug(
                f"LLM confidence {llm_result.confidence:.2f} below threshold, "
                "falling back to regex"
            )
            return self._regex_fallback(text, channel_id, user_id)

        except asyncio.TimeoutError:
            logger.warning(
                f"LLM timeout after {self.config.timeout}s, falling back to regex"
            )
            return self._regex_fallback(text, channel_id, user_id)

        except Exception as e:
            logger.warning(f"LLM parse failed: {e}, falling back to regex")
            return self._regex_fallback(text, channel_id, user_id)

    async def _llm_parse(self, text: str, channel_id: str) -> LLMParseResult:
        """Call LLM to parse message.

        Args:
            text: Message to parse.
            channel_id: Channel for context.

        Returns:
            LLMParseResult from model.
        """
        # Build conversation history
        history = self.context.get_history(channel_id)
        if history:
            history_lines = ["Recent conversation:"]
            for entry in history[-5:]:  # Last 5 for prompt size
                history_lines.append(entry.format_for_prompt())
            conversation_history = "\n".join(history_lines)
        else:
            conversation_history = "No recent conversation."

        # Build prompt
        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            default_repo=self.default_repo or "(not set)",
            conversation_history=conversation_history,
            message=text,
        )

        # Call LLM
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Low temperature for consistency
            max_tokens=200,
        )

        # Parse response
        content = response.choices[0].message.content or ""
        return self._parse_llm_response(content)

    def _parse_llm_response(self, content: str) -> LLMParseResult:
        """Parse LLM response JSON.

        Args:
            content: Raw LLM response.

        Returns:
            LLMParseResult extracted from response.
        """
        # Try to extract JSON from response
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        # Find JSON object
        match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if not match:
            logger.warning(f"No JSON found in LLM response: {content[:100]}")
            return LLMParseResult(confidence=0.0)

        try:
            data = json.loads(match.group())
            return LLMParseResult(
                command=data.get("command", "UNKNOWN").upper(),
                issue_number=data.get("issue_number"),
                pr_number=data.get("pr_number"),
                repo=data.get("repo"),
                minion_id=data.get("minion_id"),
                confidence=float(data.get("confidence", 0.0)),
                clarification=data.get("clarification"),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM JSON: {e}")
            return LLMParseResult(confidence=0.0)

    def _llm_result_to_command(self, result: LLMParseResult, raw_text: str) -> Command:
        """Convert LLMParseResult to Command.

        Args:
            result: LLM parsing result.
            raw_text: Original message text.

        Returns:
            Command object.
        """
        try:
            cmd_type = CommandType(result.command.lower())
        except ValueError:
            cmd_type = CommandType.UNKNOWN

        return Command(
            type=cmd_type,
            repo=result.repo or self.default_repo,
            issue_number=result.issue_number,
            pr_number=result.pr_number,
            minion_id=result.minion_id,
            raw_text=raw_text,
        )

    def _regex_fallback(self, text: str, channel_id: str, user_id: str) -> ParseResult:
        """Fall back to regex parser.

        Args:
            text: Message to parse.
            channel_id: Channel for context storage.
            user_id: User for context storage.

        Returns:
            ParseResult from regex parser.
        """
        command = self._regex_parser.parse(text)
        self.context.add(channel_id, user_id, text, command)
        return ParseResult(command=command)

    def format_help(self) -> str:
        """Generate help text.

        Returns:
            Formatted help string.
        """
        return self._regex_parser.format_help()

    async def close(self) -> None:
        """Clean up resources."""
        if self._client:
            await self._client.close()
            self._client = None
