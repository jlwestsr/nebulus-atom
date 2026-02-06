"""Async proposal lifecycle manager with Slack thread integration.

Manages the detect -> propose -> approve/deny -> execute cycle.
Posts proposals to Slack, tracks approval state via thread replies,
and executes approved proposals through DispatchEngine.

Built on top of the existing ProposalStore from proposals.py.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Generator, Optional

if TYPE_CHECKING:
    from nebulus_swarm.overlord.action_scope import ActionScope
    from nebulus_swarm.overlord.dispatch import (
        DispatchEngine,
        DispatchPlan,
        DispatchResult,
    )
    from nebulus_swarm.overlord.memory import OverlordMemory
    from nebulus_swarm.overlord.slack_bot import SlackBot

logger = logging.getLogger(__name__)


class ProposalState(Enum):
    """State machine for proposal lifecycle."""

    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class Proposal:
    """A tracked proposal with Slack thread binding."""

    id: str
    task: str
    scope_projects: list[str]
    scope_impact: str
    affects_remote: bool
    reason: str
    state: ProposalState
    thread_ts: Optional[str] = None
    created_at: str = ""
    resolved_at: Optional[str] = None
    result_summary: Optional[str] = None

    @property
    def is_pending(self) -> bool:
        """Check if proposal is still awaiting a decision."""
        return self.state == ProposalState.PENDING


class ProposalStore:
    """SQLite-backed storage for Slack-aware proposals."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

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
                CREATE TABLE IF NOT EXISTS overlord_proposals (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    scope_projects TEXT NOT NULL,
                    scope_impact TEXT NOT NULL,
                    affects_remote INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    thread_ts TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    result_summary TEXT
                )
            """)

    def save(self, proposal: Proposal) -> None:
        """Save or update a proposal."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO overlord_proposals
                   (id, task, scope_projects, scope_impact, affects_remote,
                    reason, state, thread_ts, created_at, resolved_at,
                    result_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    proposal.id,
                    proposal.task,
                    ",".join(proposal.scope_projects),
                    proposal.scope_impact,
                    1 if proposal.affects_remote else 0,
                    proposal.reason,
                    proposal.state.value,
                    proposal.thread_ts,
                    proposal.created_at,
                    proposal.resolved_at,
                    proposal.result_summary,
                ),
            )

    def get(self, proposal_id: str) -> Optional[Proposal]:
        """Get a proposal by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM overlord_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            return self._row_to_proposal(row) if row else None

    def get_by_thread(self, thread_ts: str) -> Optional[Proposal]:
        """Get a proposal by its Slack thread timestamp."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM overlord_proposals WHERE thread_ts = ? AND state = 'pending'",
                (thread_ts,),
            ).fetchone()
            return self._row_to_proposal(row) if row else None

    def list_pending(self) -> list[Proposal]:
        """List all pending proposals."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM overlord_proposals WHERE state = 'pending' "
                "ORDER BY created_at ASC"
            ).fetchall()
            return [self._row_to_proposal(r) for r in rows]

    def update_state(
        self,
        proposal_id: str,
        state: ProposalState,
        result_summary: Optional[str] = None,
    ) -> None:
        """Update a proposal's state."""
        resolved_at = None
        if state in (
            ProposalState.COMPLETED,
            ProposalState.FAILED,
            ProposalState.DENIED,
            ProposalState.EXPIRED,
        ):
            resolved_at = datetime.now(timezone.utc).isoformat()

        with self._conn() as conn:
            conn.execute(
                "UPDATE overlord_proposals SET state = ?, resolved_at = ?, "
                "result_summary = ? WHERE id = ?",
                (state.value, resolved_at, result_summary, proposal_id),
            )

    def cleanup_expired(self, ttl_minutes: int = 30) -> int:
        """Mark expired pending proposals. Returns count expired."""
        from datetime import timedelta

        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
        ).isoformat()

        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE overlord_proposals SET state = 'expired', "
                "resolved_at = ? WHERE state = 'pending' AND created_at < ?",
                (datetime.now(timezone.utc).isoformat(), cutoff),
            )
            return cursor.rowcount

    def _row_to_proposal(self, row: sqlite3.Row) -> Proposal:
        return Proposal(
            id=row["id"],
            task=row["task"],
            scope_projects=row["scope_projects"].split(",")
            if row["scope_projects"]
            else [],
            scope_impact=row["scope_impact"],
            affects_remote=bool(row["affects_remote"]),
            reason=row["reason"],
            state=ProposalState(row["state"]),
            thread_ts=row["thread_ts"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            result_summary=row["result_summary"],
        )


class ProposalManager:
    """Manages detect -> propose -> approve/deny -> execute lifecycle."""

    def __init__(
        self,
        store: ProposalStore,
        dispatch: DispatchEngine,
        slack_bot: Optional[SlackBot] = None,
        memory: Optional[OverlordMemory] = None,
    ):
        """Initialize the proposal manager.

        Args:
            store: SQLite-backed proposal store.
            dispatch: Dispatch engine for executing approved proposals.
            slack_bot: Optional Slack bot for posting proposals.
            memory: Optional memory store for logging outcomes.
        """
        self.store = store
        self.dispatch = dispatch
        self.slack_bot = slack_bot
        self.memory = memory
        # In-memory cache of plans keyed by proposal_id
        self._plans: dict[str, DispatchPlan] = {}

    async def propose(
        self,
        task: str,
        scope: ActionScope,
        reason: str,
        plan: Optional[DispatchPlan] = None,
    ) -> str:
        """Create a proposal, post to Slack, return proposal_id.

        Args:
            task: Natural language description of the proposed action.
            scope: ActionScope describing blast radius.
            reason: Why this action is proposed.
            plan: Optional pre-built dispatch plan.

        Returns:
            Proposal ID string.
        """
        proposal = Proposal(
            id=str(uuid.uuid4())[:8],
            task=task,
            scope_projects=scope.projects,
            scope_impact=scope.estimated_impact,
            affects_remote=scope.affects_remote,
            reason=reason,
            state=ProposalState.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if plan:
            self._plans[proposal.id] = plan

        # Post to Slack
        message = _format_proposal_message(proposal)
        if self.slack_bot:
            try:
                response = await self.slack_bot.app.client.chat_postMessage(
                    channel=self.slack_bot.channel_id,
                    text=message,
                )
                proposal.thread_ts = response.get("ts")
            except Exception as e:
                logger.error("Failed to post proposal to Slack: %s", e)

        self.store.save(proposal)
        logger.info("Created proposal %s: %s", proposal.id, task)
        return proposal.id

    async def handle_reply(self, thread_ts: str, text: str) -> Optional[str]:
        """Handle a Slack thread reply that may be an approval or denial.

        Args:
            thread_ts: Thread timestamp to match against proposals.
            text: Reply text (looking for "approve" or "deny").

        Returns:
            Response message if matched, None otherwise.
        """
        proposal = self.store.get_by_thread(thread_ts)
        if not proposal:
            return None

        normalized = text.strip().lower()

        if normalized in ("approve", "approved", "yes", "lgtm"):
            self.store.update_state(proposal.id, ProposalState.APPROVED)
            result = await self.execute_approved(proposal.id)
            if result and result.status == "success":
                return f"Proposal {proposal.id} approved and executed successfully."
            elif result:
                return f"Proposal {proposal.id} approved but execution failed: {result.reason}"
            return f"Proposal {proposal.id} approved."

        if normalized in ("deny", "denied", "no", "reject"):
            self.store.update_state(
                proposal.id, ProposalState.DENIED, result_summary="Denied by user"
            )
            return f"Proposal {proposal.id} denied."

        return None  # Not a recognized approval/denial reply

    async def execute_approved(self, proposal_id: str) -> Optional[DispatchResult]:
        """Execute an approved proposal via DispatchEngine.

        Args:
            proposal_id: ID of the approved proposal.

        Returns:
            DispatchResult or None if no plan cached.
        """
        plan = self._plans.get(proposal_id)
        if not plan:
            logger.warning("No plan cached for proposal %s", proposal_id)
            return None

        self.store.update_state(proposal_id, ProposalState.EXECUTING)

        try:
            result = await asyncio.to_thread(self.dispatch.execute, plan, True)
        except Exception as e:
            self.store.update_state(
                proposal_id, ProposalState.FAILED, result_summary=str(e)
            )
            logger.error("Proposal %s execution failed: %s", proposal_id, e)
            return None

        if result.status == "success":
            self.store.update_state(
                proposal_id,
                ProposalState.COMPLETED,
                result_summary="Executed successfully",
            )
            if self.memory:
                await asyncio.to_thread(
                    self.memory.remember,
                    "decision",
                    f"Approved and executed: {plan.task}",
                    project=plan.scope.projects[0] if plan.scope.projects else None,
                )
        else:
            self.store.update_state(
                proposal_id, ProposalState.FAILED, result_summary=result.reason
            )

        # Notify Slack
        proposal = self.store.get(proposal_id)
        if self.slack_bot and proposal and proposal.thread_ts:
            status_msg = f"Proposal {proposal_id}: {result.status}" + (
                f" — {result.reason}" if result.reason else ""
            )
            await self.slack_bot.post_message(status_msg, thread_ts=proposal.thread_ts)

        # Clean up cached plan
        self._plans.pop(proposal_id, None)
        return result

    async def cleanup_expired(self, ttl_minutes: int = 30) -> int:
        """Mark expired proposals.

        Args:
            ttl_minutes: Minutes after which pending proposals expire.

        Returns:
            Number of proposals expired.
        """
        count = await asyncio.to_thread(self.store.cleanup_expired, ttl_minutes)
        if count:
            logger.info("Expired %d proposals", count)
        return count


def _format_proposal_message(proposal: Proposal) -> str:
    """Format a proposal for Slack posting."""
    remote = "affects remote" if proposal.affects_remote else "local only"
    return (
        f"Proposal: {proposal.task}\n\n"
        f"Scope: {', '.join(proposal.scope_projects)} | "
        f"{remote} | estimated: {proposal.scope_impact}\n"
        f"Reason: {proposal.reason}\n\n"
        f'Reply "approve" or "deny" in this thread.\n'
        f"Auto-expires in 30 minutes."
    )
