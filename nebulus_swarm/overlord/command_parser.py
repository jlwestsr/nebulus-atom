"""Command parser for Overlord Slack messages."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommandType(Enum):
    """Types of commands the Overlord can handle."""

    STATUS = "status"
    WORK = "work"
    STOP = "stop"
    QUEUE = "queue"
    PAUSE = "pause"
    RESUME = "resume"
    HISTORY = "history"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class Command:
    """Parsed command from a Slack message."""

    type: CommandType
    repo: Optional[str] = None
    issue_number: Optional[int] = None
    minion_id: Optional[str] = None
    raw_text: str = ""


class CommandParser:
    """Parses natural language commands from Slack messages."""

    # Regex patterns for command matching
    PATTERNS = {
        # "status" or "what's the status" or "how's it going"
        CommandType.STATUS: [
            r"^status$",
            r"what'?s the status",
            r"how'?s it going",
            r"what are (?:the )?minions doing",
            r"show (?:me )?status",
        ],
        # "work on #42" or "start issue 42" or "work on repo/name#42"
        CommandType.WORK: [
            r"work (?:on )?(?:issue )?#?(\d+)",
            r"start (?:on )?(?:issue )?#?(\d+)",
            r"work (?:on )?([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)#(\d+)",
            r"start (?:on )?([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)#(\d+)",
        ],
        # "stop #42" or "stop minion on 42" or "kill minion-abc123"
        CommandType.STOP: [
            r"stop (?:issue )?#?(\d+)",
            r"stop (?:the )?minion (?:on )?#?(\d+)",
            r"kill (?:minion[- ])?([a-zA-Z0-9-]+)",
            r"cancel #?(\d+)",
        ],
        # "queue" or "what's in the queue" or "list work"
        CommandType.QUEUE: [
            r"^queue$",
            r"what'?s in (?:the )?queue",
            r"show (?:the )?queue",
            r"list (?:the )?(?:work|issues|queue)",
            r"pending (?:work|issues)",
        ],
        # "pause" or "pause work" or "hold"
        CommandType.PAUSE: [
            r"^pause$",
            r"pause (?:work|processing|queue)",
            r"^hold$",
            r"stop (?:the )?queue",
        ],
        # "resume" or "continue" or "unpause"
        CommandType.RESUME: [
            r"^resume$",
            r"resume (?:work|processing|queue)",
            r"^continue$",
            r"^unpause$",
            r"start (?:the )?queue",
        ],
        # "history" or "show history" or "recent work"
        CommandType.HISTORY: [
            r"^history$",
            r"show (?:me )?history",
            r"recent (?:work|prs?|completions?)",
            r"what (?:did|have) (?:the )?minions? (?:do|done)",
        ],
        # "help" or "commands" or "what can you do"
        CommandType.HELP: [
            r"^help$",
            r"^commands?$",
            r"what can you do",
            r"how do (?:I|you) use",
        ],
    }

    def __init__(self, default_repo: Optional[str] = None):
        """Initialize parser.

        Args:
            default_repo: Default repository for commands without explicit repo.
        """
        self.default_repo = default_repo

    def parse(self, text: str) -> Command:
        """Parse a message into a Command.

        Args:
            text: Raw message text from Slack.

        Returns:
            Parsed Command object.
        """
        text = text.strip().lower()

        for cmd_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return self._build_command(cmd_type, match, text)

        # No pattern matched
        return Command(type=CommandType.UNKNOWN, raw_text=text)

    def _build_command(
        self, cmd_type: CommandType, match: re.Match, raw_text: str
    ) -> Command:
        """Build a Command object from a regex match.

        Args:
            cmd_type: The type of command matched.
            match: The regex match object.
            raw_text: Original message text.

        Returns:
            Command object with extracted parameters.
        """
        cmd = Command(type=cmd_type, raw_text=raw_text)

        groups = match.groups()

        if cmd_type == CommandType.WORK:
            if len(groups) == 2:
                # repo/name#issue format
                cmd.repo = groups[0]
                cmd.issue_number = int(groups[1])
            elif len(groups) == 1:
                # just issue number
                cmd.issue_number = int(groups[0])
                cmd.repo = self.default_repo

        elif cmd_type == CommandType.STOP:
            if groups:
                # Could be issue number or minion ID
                try:
                    cmd.issue_number = int(groups[0])
                except ValueError:
                    cmd.minion_id = groups[0]

        return cmd

    def format_help(self) -> str:
        """Generate help text for available commands.

        Returns:
            Formatted help string.
        """
        return """🤖 *Overlord Commands*

*Status & Info:*
• `status` - Show active minions and their tasks
• `queue` - Show pending work from GitHub
• `history` - Show recent completed work

*Work Management:*
• `work on #42` - Start a minion on issue #42
• `work on owner/repo#42` - Start on specific repo
• `stop #42` - Stop the minion working on issue #42
• `stop minion-abc123` - Stop a specific minion

*Queue Control:*
• `pause` - Pause automatic queue processing
• `resume` - Resume automatic queue processing

*Other:*
• `ping` - Check if I'm alive
• `help` - Show this message
"""
