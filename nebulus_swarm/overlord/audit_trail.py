"""Hybrid audit trail for compliance logging.

Provides tamper-evident semantic logging with hash chains and Ed25519 signing.
Designed for regulated industries requiring audit trails.
"""

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


class LogEvent(Enum):
    """Types of events in the audit trail."""

    TASK_RECEIVED = "task_received"
    TASK_DISPATCHED = "task_dispatched"
    WORKER_RESULT = "worker_result"
    EVALUATION_COMPLETE = "evaluation_complete"
    TASK_COMPLETE = "task_complete"
    TASK_ABANDONED = "task_abandoned"
    REVISION_REQUESTED = "revision_requested"


@dataclass
class SemanticLog:
    """A semantic log entry capturing intent and reasoning."""

    event: LogEvent
    task_id: str
    timestamp: datetime
    data: Dict[str, Any]  # Event-specific data
    reasoning: str = ""  # Supervisor's reasoning for the action
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    previous_hash: str = ""  # Hash of previous log entry (chain)
    signature: str = ""  # Ed25519 signature of this entry

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "event": self.event.value,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "reasoning": self.reasoning,
            "previous_hash": self.previous_hash,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SemanticLog":
        """Create from dictionary."""
        return cls(
            id=d["id"],
            event=LogEvent(d["event"]),
            task_id=d["task_id"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            data=d.get("data", {}),
            reasoning=d.get("reasoning", ""),
            previous_hash=d.get("previous_hash", ""),
            signature=d.get("signature", ""),
        )

    def compute_hash(self) -> str:
        """Compute hash of this log entry (excluding signature)."""
        content = {
            "id": self.id,
            "event": self.event.value,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "reasoning": self.reasoning,
            "previous_hash": self.previous_hash,
        }
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


class AuditTrail:
    """Manages semantic logging with hash chain and optional signing.

    Each log entry contains:
    - Event type and timestamp
    - Task ID and event-specific data
    - Supervisor's reasoning
    - Hash of previous entry (tamper evidence)
    - Optional Ed25519 signature
    """

    def __init__(self, db_path: str, signing_key: Optional[bytes] = None):
        """Initialize audit trail.

        Args:
            db_path: Path to SQLite database.
            signing_key: Optional Ed25519 private key for signing (32 bytes).
        """
        self.db_path = db_path
        self._signing_key = signing_key
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    event TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    data TEXT NOT NULL,
                    reasoning TEXT,
                    previous_hash TEXT,
                    signature TEXT,
                    entry_hash TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_id ON audit_logs(task_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_logs(timestamp)"
            )

    def _get_last_hash(self) -> str:
        """Get hash of the most recent log entry."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT entry_hash FROM audit_logs ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            return row["entry_hash"] if row else ""

    def _sign(self, content: str) -> str:
        """Sign content with Ed25519 key if available."""
        if not self._signing_key:
            return ""
        try:
            import base64

            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )

            key = Ed25519PrivateKey.from_private_bytes(self._signing_key)
            signature = key.sign(content.encode())
            return base64.b64encode(signature).decode()
        except ImportError:
            logger.debug("cryptography not available, skipping signature")
            return ""
        except Exception as e:
            logger.warning(f"Signing failed: {e}")
            return ""

    def log(
        self,
        event: LogEvent,
        task_id: str,
        data: Dict[str, Any],
        reasoning: str = "",
    ) -> SemanticLog:
        """Add a log entry to the audit trail.

        Args:
            event: Type of event.
            task_id: ID of the task this event relates to.
            data: Event-specific data.
            reasoning: Supervisor's reasoning for this action.

        Returns:
            The created SemanticLog entry.
        """
        entry = SemanticLog(
            event=event,
            task_id=task_id,
            timestamp=datetime.now(),
            data=data,
            reasoning=reasoning,
            previous_hash=self._get_last_hash(),
        )

        # Compute hash and sign
        entry_hash = entry.compute_hash()
        entry.signature = self._sign(entry_hash)

        # Store in database
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO audit_logs
                   (id, event, task_id, timestamp, data, reasoning, previous_hash, signature, entry_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id,
                    entry.event.value,
                    entry.task_id,
                    entry.timestamp.isoformat(),
                    json.dumps(entry.data),
                    entry.reasoning,
                    entry.previous_hash,
                    entry.signature,
                    entry_hash,
                ),
            )

        logger.debug(f"Audit log: {event.value} for task {task_id}")
        return entry

    def get_logs_for_task(self, task_id: str) -> List[SemanticLog]:
        """Get all log entries for a specific task."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs WHERE task_id = ? ORDER BY timestamp",
                (task_id,),
            ).fetchall()
            return [self._row_to_log(r) for r in rows]

    def get_all_logs(self, limit: int = 1000) -> List[SemanticLog]:
        """Get all log entries, most recent first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_log(r) for r in rows]

    def _row_to_log(self, row: sqlite3.Row) -> SemanticLog:
        return SemanticLog(
            id=row["id"],
            event=LogEvent(row["event"]),
            task_id=row["task_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            data=json.loads(row["data"]),
            reasoning=row["reasoning"] or "",
            previous_hash=row["previous_hash"] or "",
            signature=row["signature"] or "",
        )

    def verify_integrity(self) -> tuple[bool, List[str]]:
        """Verify the hash chain integrity.

        Returns:
            Tuple of (is_valid, list_of_issues).
        """
        issues = []
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs ORDER BY timestamp"
            ).fetchall()

        if not rows:
            return True, []

        previous_hash = ""
        for row in rows:
            log = self._row_to_log(row)
            stored_hash = row["entry_hash"]

            # Check previous hash chain
            if log.previous_hash != previous_hash:
                issues.append(
                    f"Chain break at {log.id}: expected previous_hash={previous_hash[:8]}..., got {log.previous_hash[:8]}..."
                )

            # Verify entry hash
            computed_hash = log.compute_hash()
            if computed_hash != stored_hash:
                issues.append(
                    f"Hash mismatch at {log.id}: computed={computed_hash[:8]}..., stored={stored_hash[:8]}..."
                )

            previous_hash = stored_hash

        return len(issues) == 0, issues

    def export(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Export audit trail as JSON-serializable dict.

        Args:
            task_id: Optional task ID to filter by.

        Returns:
            Dict with logs and integrity status.
        """
        if task_id:
            logs = self.get_logs_for_task(task_id)
        else:
            logs = self.get_all_logs()

        is_valid, issues = self.verify_integrity()

        return {
            "exported_at": datetime.now().isoformat(),
            "integrity_valid": is_valid,
            "integrity_issues": issues,
            "log_count": len(logs),
            "logs": [log.to_dict() for log in logs],
        }


def generate_signing_key() -> bytes:
    """Generate a new Ed25519 signing key."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.generate()
        return key.private_bytes_raw()
    except ImportError:
        logger.warning("cryptography not available, cannot generate signing key")
        return b""


def load_or_create_signing_key(key_path: Path) -> Optional[bytes]:
    """Load signing key from file or create new one."""
    if key_path.exists():
        return key_path.read_bytes()

    key = generate_signing_key()
    if key:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        logger.info(f"Generated new signing key at {key_path}")
    return key if key else None
