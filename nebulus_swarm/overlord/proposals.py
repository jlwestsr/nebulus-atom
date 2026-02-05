"""Enhancement proposal system for supervisor-identified improvements."""

import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Generator, List, Optional

logger = logging.getLogger(__name__)


class ProposalType(Enum):
    """Type of enhancement proposal."""

    NEW_SKILL = "new_skill"
    TOOL_FIX = "tool_fix"
    CONFIG_CHANGE = "config_change"
    WORKFLOW_IMPROVEMENT = "workflow_improvement"


class ProposalStatus(Enum):
    """Status of an enhancement proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


@dataclass
class EnhancementProposal:
    """A structured proposal for system improvement."""

    type: ProposalType
    title: str
    rationale: str
    proposed_action: str
    estimated_impact: str = "Medium"
    risk: str = "Low"
    status: ProposalStatus = ProposalStatus.PENDING
    related_issues: List[int] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None

    @property
    def is_actionable(self) -> bool:
        """Check if proposal still needs action."""
        return self.status in (ProposalStatus.PENDING, ProposalStatus.APPROVED)


class ProposalStore:
    """SQLite-backed storage for enhancement proposals."""

    def __init__(self, db_path: str):
        self.db_path = db_path
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
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    proposed_action TEXT NOT NULL,
                    estimated_impact TEXT DEFAULT 'Medium',
                    risk TEXT DEFAULT 'Low',
                    status TEXT NOT NULL DEFAULT 'pending',
                    related_issues TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
            """)

    def save(self, proposal: EnhancementProposal) -> None:
        """Save a proposal to the store."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO proposals
                   (id, type, title, rationale, proposed_action,
                    estimated_impact, risk, status, related_issues,
                    created_at, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    proposal.id,
                    proposal.type.value,
                    proposal.title,
                    proposal.rationale,
                    proposal.proposed_action,
                    proposal.estimated_impact,
                    proposal.risk,
                    proposal.status.value,
                    json.dumps(proposal.related_issues),
                    proposal.created_at.isoformat(),
                    proposal.resolved_at.isoformat() if proposal.resolved_at else None,
                ),
            )

    def get(self, proposal_id: str) -> Optional[EnhancementProposal]:
        """Get a proposal by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            if row:
                return self._row_to_proposal(row)
            return None

    def list_by_status(self, status: ProposalStatus) -> List[EnhancementProposal]:
        """List proposals with a given status."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC",
                (status.value,),
            ).fetchall()
            return [self._row_to_proposal(r) for r in rows]

    def update_status(self, proposal_id: str, status: ProposalStatus) -> None:
        """Update a proposal's status."""
        resolved_at = None
        if status in (ProposalStatus.REJECTED, ProposalStatus.IMPLEMENTED):
            resolved_at = datetime.now().isoformat()

        with self._conn() as conn:
            conn.execute(
                "UPDATE proposals SET status = ?, resolved_at = ? WHERE id = ?",
                (status.value, resolved_at, proposal_id),
            )

    def _row_to_proposal(self, row: sqlite3.Row) -> EnhancementProposal:
        return EnhancementProposal(
            id=row["id"],
            type=ProposalType(row["type"]),
            title=row["title"],
            rationale=row["rationale"],
            proposed_action=row["proposed_action"],
            estimated_impact=row["estimated_impact"],
            risk=row["risk"],
            status=ProposalStatus(row["status"]),
            related_issues=json.loads(row["related_issues"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"])
            if row["resolved_at"]
            else None,
        )
