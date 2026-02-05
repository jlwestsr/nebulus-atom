"""Worker scope enforcement for Minion file access."""

import fnmatch
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)


class ScopeMode(Enum):
    """Scope enforcement mode."""

    UNRESTRICTED = "unrestricted"
    DIRECTORY = "directory"
    EXPLICIT = "explicit"


@dataclass
class ScopeConfig:
    """Configuration for Minion write scope."""

    mode: ScopeMode = ScopeMode.UNRESTRICTED
    allowed_patterns: List[str] = field(default_factory=list)

    @classmethod
    def unrestricted(cls) -> "ScopeConfig":
        """Create an unrestricted scope."""
        return cls(mode=ScopeMode.UNRESTRICTED)

    @classmethod
    def from_json(cls, json_str: str) -> "ScopeConfig":
        """Parse scope from JSON string (MINION_SCOPE env var).

        Args:
            json_str: JSON array of allowed path patterns.

        Returns:
            ScopeConfig. Unrestricted if empty or invalid.
        """
        if not json_str or not json_str.strip():
            return cls.unrestricted()
        try:
            patterns = json.loads(json_str)
            if not isinstance(patterns, list) or not patterns:
                return cls.unrestricted()
            return cls(mode=ScopeMode.DIRECTORY, allowed_patterns=patterns)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"Invalid MINION_SCOPE JSON, using unrestricted: {json_str[:100]}"
            )
            return cls.unrestricted()

    def to_json(self) -> str:
        """Serialize allowed patterns to JSON."""
        return json.dumps(self.allowed_patterns)

    def is_write_allowed(self, path: str) -> bool:
        """Check if writing to a path is allowed.

        Args:
            path: Relative file path to check.

        Returns:
            True if write is allowed.
        """
        if self.mode == ScopeMode.UNRESTRICTED:
            return True

        for pattern in self.allowed_patterns:
            if self.mode == ScopeMode.EXPLICIT:
                if path == pattern:
                    return True
            else:  # DIRECTORY
                if fnmatch.fnmatch(path, pattern):
                    return True
        return False

    def violation_message(self, path: str) -> str:
        """Generate a human-readable violation message.

        Args:
            path: The path that was blocked.

        Returns:
            Error message explaining the restriction.
        """
        allowed = ", ".join(self.allowed_patterns)
        return (
            f"Write to '{path}' is outside your assigned scope. "
            f"Allowed paths: [{allowed}]. "
            f"If you need to modify this file, use task_blocked to request expanded scope."
        )
