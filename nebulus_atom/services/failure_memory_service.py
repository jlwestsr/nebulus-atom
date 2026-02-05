"""
Failure memory service for tracking tool errors and recognizing patterns.

Persists tool failures in SQLite, classifies errors by type, tracks
resolution rates, and feeds failure context into the cognition system.
"""

import json
import os
import re
import sqlite3
import time
import uuid
from typing import List, Optional

from nebulus_atom.models.failure_memory import (
    FailureContext,
    FailurePattern,
    FailureRecord,
)
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)

# Safe keys to keep when sanitizing tool arguments
_SAFE_ARG_KEYS = {"path", "command", "query", "name", "filename", "directory"}

# Error classification regexes (order matters — first match wins)
_ERROR_CLASSIFIERS = [
    (r"(?i)file not found|no such file|FileNotFoundError", "file_not_found"),
    (r"(?i)no module named|ModuleNotFoundError", "missing_module"),
    (r"(?i)expecting value|extra data|invalid control|JSONDecodeError", "invalid_json"),
    (r"(?i)invalid syntax|unexpected indent|SyntaxError", "syntax_error"),
    (r"(?i)permission denied|PermissionError", "permission_denied"),
    (r"(?i)timed? ?out|TimeoutError", "timeout"),
    (r"(?i)non-zero exit|command failed|CalledProcessError", "command_failed"),
]


class FailureMemoryService:
    """Tracks tool failures and builds pattern-based context for cognition."""

    def __init__(self, db_path: str = "nebulus_atom/data/failure_memory.db") -> None:
        """Initialize with SQLite database path."""
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create the failures table if it doesn't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS failures (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                timestamp REAL,
                tool_name TEXT,
                error_type TEXT,
                error_message TEXT,
                args_context TEXT,
                recovery_attempted TEXT DEFAULT '',
                resolved INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
        conn.close()

    def record_failure(
        self,
        session_id: str,
        tool_name: str,
        error_message: str,
        args: Optional[dict] = None,
    ) -> FailureRecord:
        """Record a tool failure.

        Args:
            session_id: Current session identifier.
            tool_name: Name of the tool that failed.
            error_message: The error message string.
            args: Raw tool arguments (will be sanitized).

        Returns:
            The created FailureRecord.
        """
        error_type = self._classify_error(error_message)
        sanitized = self._sanitize_args(args or {})
        record = FailureRecord(
            id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=time.time(),
            tool_name=tool_name,
            error_type=error_type,
            error_message=error_message[:500],
            args_context=sanitized,
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO failures "
            "(id, session_id, timestamp, tool_name, error_type, error_message, args_context, recovery_attempted, resolved) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.session_id,
                record.timestamp,
                record.tool_name,
                record.error_type,
                record.error_message,
                json.dumps(record.args_context),
                record.recovery_attempted,
                0,
            ),
        )
        conn.commit()
        conn.close()

        logger.info(
            f"Recorded failure: tool={tool_name}, type={error_type}, "
            f"session={session_id}"
        )
        return record

    def mark_resolved(self, tool_name: str, error_type: str) -> bool:
        """Mark the most recent unresolved failure of this type as resolved.

        Args:
            tool_name: Tool name to match.
            error_type: Error type to match.

        Returns:
            True if a row was updated, False otherwise.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE failures SET resolved = 1 "
            "WHERE id = ("
            "  SELECT id FROM failures "
            "  WHERE tool_name = ? AND error_type = ? AND resolved = 0 "
            "  ORDER BY timestamp DESC LIMIT 1"
            ")",
            (tool_name, error_type),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if updated:
            logger.debug(f"Marked resolved: tool={tool_name}, error_type={error_type}")
        return updated

    def query_similar_failures(
        self, tool_name: str, error_type: Optional[str] = None
    ) -> FailurePattern:
        """Query aggregated failure pattern for a tool and optional error type.

        Args:
            tool_name: The tool to query.
            error_type: Optional error type filter. If None, aggregates all types.

        Returns:
            FailurePattern with counts.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if error_type:
            cursor.execute(
                "SELECT COUNT(*), SUM(resolved) FROM failures "
                "WHERE tool_name = ? AND error_type = ?",
                (tool_name, error_type),
            )
        else:
            cursor.execute(
                "SELECT COUNT(*), SUM(resolved) FROM failures WHERE tool_name = ?",
                (tool_name,),
            )

        row = cursor.fetchone()
        conn.close()

        count = row[0] or 0
        resolved = int(row[1] or 0)
        return FailurePattern(
            tool_name=tool_name,
            error_type=error_type or "all",
            occurrence_count=count,
            resolved_count=resolved,
        )

    def build_failure_context(
        self, tool_names: Optional[List[str]] = None
    ) -> FailureContext:
        """Build a FailureContext for a set of tools.

        Args:
            tool_names: Tools to check. If None, checks all recorded tools.

        Returns:
            FailureContext with patterns and warnings.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if tool_names:
            placeholders = ",".join("?" for _ in tool_names)
            cursor.execute(
                f"SELECT tool_name, error_type, COUNT(*), SUM(resolved) "
                f"FROM failures "
                f"WHERE tool_name IN ({placeholders}) "
                f"GROUP BY tool_name, error_type",
                tool_names,
            )
        else:
            cursor.execute(
                "SELECT tool_name, error_type, COUNT(*), SUM(resolved) "
                "FROM failures "
                "GROUP BY tool_name, error_type"
            )

        rows = cursor.fetchall()
        conn.close()

        patterns = []
        warnings = []

        for row in rows:
            pattern = FailurePattern(
                tool_name=row[0],
                error_type=row[1],
                occurrence_count=row[2],
                resolved_count=int(row[3] or 0),
            )
            if pattern.occurrence_count > 0:
                patterns.append(pattern)
                if pattern.occurrence_count >= 3:
                    warnings.append(
                        f"Tool '{pattern.tool_name}' has failed {pattern.occurrence_count} times "
                        f"with {pattern.error_type} errors "
                        f"(resolution rate: {pattern.resolution_rate:.0%})"
                    )

        return FailureContext(patterns=patterns, warning_messages=warnings)

    def get_failure_summary_for_llm(self, context: FailureContext) -> str:
        """Generate a human-readable failure summary for LLM context.

        Args:
            context: The FailureContext to summarize.

        Returns:
            Summary string, or empty string if no relevant patterns.
        """
        if not context.patterns:
            return ""

        lines = ["[Failure Memory]"]
        for pattern in context.patterns:
            lines.append(
                f"- {pattern.tool_name}/{pattern.error_type}: "
                f"{pattern.occurrence_count} failures, "
                f"{pattern.resolution_rate:.0%} resolved, "
                f"penalty={pattern.confidence_penalty:.2f}"
            )

        if context.warning_messages:
            lines.append("")
            for warning in context.warning_messages:
                lines.append(f"WARNING: {warning}")

        lines.append(f"Total confidence penalty: {context.total_penalty:.2f}")
        return "\n".join(lines)

    @staticmethod
    def _classify_error(error_message: str) -> str:
        """Classify an error message into a known type.

        Args:
            error_message: Raw error message string.

        Returns:
            Error type string.
        """
        for pattern, error_type in _ERROR_CLASSIFIERS:
            if re.search(pattern, error_message):
                return error_type
        return "unknown"

    @staticmethod
    def _sanitize_args(args: dict) -> dict:
        """Sanitize tool arguments, keeping only safe keys.

        Args:
            args: Raw tool arguments.

        Returns:
            Dict with only safe keys preserved.
        """
        return {k: v for k, v in args.items() if k in _SAFE_ARG_KEYS}


class FailureMemoryServiceManager:
    """Manages a singleton FailureMemoryService instance."""

    def __init__(self) -> None:
        """Initialize the manager."""
        self.service = FailureMemoryService()

    def get_service(self, session_id: str = "default") -> FailureMemoryService:
        """Get the FailureMemoryService instance."""
        return self.service
