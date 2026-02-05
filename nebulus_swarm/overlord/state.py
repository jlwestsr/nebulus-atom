"""SQLite state management for Overlord."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Generator, List, Optional

from nebulus_swarm.models.minion import Minion, MinionStatus

if TYPE_CHECKING:
    from nebulus_swarm.overlord.evaluator import EvaluationResult


class OverlordState:
    """Manages persistent state for the Overlord."""

    def __init__(self, db_path: str = "/var/lib/overlord/state.db"):
        """Initialize state manager.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_db()

    def _ensure_db_directory(self) -> None:
        """Ensure the database directory exists."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Minions table - active and recent minions
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS minions (
                    id TEXT PRIMARY KEY,
                    container_id TEXT,
                    repo TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'starting',
                    started_at TEXT NOT NULL,
                    last_heartbeat TEXT,
                    pr_number INTEGER,
                    error_message TEXT
                )
            """
            )

            # Work history table - completed work records
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS work_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    minion_id TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    pr_number INTEGER,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    error_message TEXT,
                    duration_seconds INTEGER
                )
            """
            )

            # Create indexes for common queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_minions_status
                ON minions(status)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_history_repo
                ON work_history(repo)
            """
            )

            # Evaluations table - evaluation results for PRs
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pr_number INTEGER NOT NULL,
                    repo TEXT NOT NULL,
                    test_score TEXT NOT NULL,
                    lint_score TEXT NOT NULL,
                    review_score TEXT NOT NULL,
                    overall TEXT NOT NULL,
                    revision_number INTEGER DEFAULT 0,
                    feedback TEXT,
                    evaluated_at TEXT NOT NULL
                )
            """
            )

    def add_minion(self, minion: Minion) -> None:
        """Add a new minion to the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO minions
                (id, container_id, repo, issue_number, status, started_at, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    minion.id,
                    minion.container_id,
                    minion.repo,
                    minion.issue_number,
                    minion.status.value,
                    minion.started_at.isoformat(),
                    minion.last_heartbeat.isoformat()
                    if minion.last_heartbeat
                    else None,
                ),
            )

    def update_minion(
        self,
        minion_id: str,
        status: Optional[MinionStatus] = None,
        container_id: Optional[str] = None,
        last_heartbeat: Optional[datetime] = None,
        pr_number: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update a minion's state."""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if container_id is not None:
            updates.append("container_id = ?")
            params.append(container_id)
        if last_heartbeat is not None:
            updates.append("last_heartbeat = ?")
            params.append(last_heartbeat.isoformat())
        if pr_number is not None:
            updates.append("pr_number = ?")
            params.append(pr_number)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        if not updates:
            return

        params.append(minion_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE minions SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    def get_minion(self, minion_id: str) -> Optional[Minion]:
        """Get a minion by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM minions WHERE id = ?", (minion_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_minion(row)
            return None

    def get_active_minions(self) -> List[Minion]:
        """Get all active (non-completed) minions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM minions WHERE status IN (?, ?)",
                (MinionStatus.STARTING.value, MinionStatus.WORKING.value),
            )
            return [self._row_to_minion(row) for row in cursor.fetchall()]

    def get_minion_by_issue(self, repo: str, issue_number: int) -> Optional[Minion]:
        """Get active minion working on a specific issue."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM minions
                WHERE repo = ? AND issue_number = ? AND status IN (?, ?)
            """,
                (
                    repo,
                    issue_number,
                    MinionStatus.STARTING.value,
                    MinionStatus.WORKING.value,
                ),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_minion(row)
            return None

    def remove_minion(self, minion_id: str) -> None:
        """Remove a minion from active tracking."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM minions WHERE id = ?", (minion_id,))

    def record_completion(
        self,
        minion: Minion,
        status: MinionStatus,
        pr_number: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Record completed work to history and remove from active minions."""
        completed_at = datetime.now()
        duration = int((completed_at - minion.started_at).total_seconds())

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Add to history
            cursor.execute(
                """
                INSERT INTO work_history
                (minion_id, repo, issue_number, pr_number, status,
                 started_at, completed_at, error_message, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    minion.id,
                    minion.repo,
                    minion.issue_number,
                    pr_number,
                    status.value,
                    minion.started_at.isoformat(),
                    completed_at.isoformat(),
                    error_message,
                    duration,
                ),
            )

            # Remove from active minions
            cursor.execute("DELETE FROM minions WHERE id = ?", (minion.id,))

    def get_work_history(
        self,
        repo: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        """Get recent work history.

        Args:
            repo: Filter by repository name.
            status: Filter by status (e.g., 'completed', 'failed', 'timeout').
            limit: Maximum number of records to return.

        Returns:
            List of work history records as dicts.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM work_history WHERE 1=1"
            params: list = []

            if repo:
                query += " AND repo = ?"
                params.append(repo)
            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY completed_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_distinct_repos(self) -> List[str]:
        """Get list of distinct repositories from work history.

        Returns:
            Sorted list of unique repo names.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT repo FROM work_history ORDER BY repo")
            return [row["repo"] for row in cursor.fetchall()]

    def save_evaluation(self, result: "EvaluationResult") -> None:
        """Save an evaluation result to the database.

        Args:
            result: EvaluationResult to persist.
        """

        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO evaluations
                   (pr_number, repo, test_score, lint_score, review_score,
                    overall, revision_number, feedback, evaluated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.pr_number,
                    result.repo,
                    result.test_score.value,
                    result.lint_score.value,
                    result.review_score.value,
                    result.overall.value,
                    result.revision_number,
                    result.combined_feedback,
                    result.timestamp.isoformat(),
                ),
            )

    def get_evaluations(self, repo: str, pr_number: int) -> List[dict]:
        """Get evaluation history for a PR.

        Args:
            repo: Repository in owner/name format.
            pr_number: Pull request number.

        Returns:
            List of evaluation records as dicts.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM evaluations WHERE repo = ? AND pr_number = ? ORDER BY evaluated_at",
                (repo, pr_number),
            ).fetchall()
            return [dict(r) for r in rows]

    def _row_to_minion(self, row: sqlite3.Row) -> Minion:
        """Convert a database row to a Minion object."""
        return Minion(
            id=row["id"],
            container_id=row["container_id"],
            repo=row["repo"],
            issue_number=row["issue_number"],
            status=MinionStatus(row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            last_heartbeat=datetime.fromisoformat(row["last_heartbeat"])
            if row["last_heartbeat"]
            else None,
            pr_number=row["pr_number"],
            error_message=row["error_message"],
        )
