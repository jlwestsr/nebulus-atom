"""Tests for Swarm Dashboard data client and Overlord changes."""

import json
import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock slack_bolt before importing Overlord modules
sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("slack_bolt.adapter", MagicMock())
sys.modules.setdefault("slack_bolt.adapter.socket_mode", MagicMock())
sys.modules.setdefault("slack_bolt.adapter.socket_mode.async_handler", MagicMock())
sys.modules.setdefault("slack_bolt.async_app", MagicMock())


# ---------------------------------------------------------------------------
# OverlordState: get_work_history status filter + get_distinct_repos
# ---------------------------------------------------------------------------


class TestOverlordStateFilters:
    """Tests for new OverlordState query features."""

    def _make_state(self, db_path: str):
        """Create an OverlordState with test data."""
        from nebulus_swarm.overlord.state import OverlordState

        state = OverlordState(db_path=db_path)

        # Insert test history data
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        records = [
            (
                "m-1",
                "owner/repo-a",
                1,
                10,
                "completed",
                "2026-01-01T10:00:00",
                "2026-01-01T10:05:00",
                None,
                300,
            ),
            (
                "m-2",
                "owner/repo-a",
                2,
                None,
                "failed",
                "2026-01-01T11:00:00",
                "2026-01-01T11:03:00",
                "git_error: push failed",
                180,
            ),
            (
                "m-3",
                "owner/repo-b",
                3,
                11,
                "completed",
                "2026-01-02T10:00:00",
                "2026-01-02T10:10:00",
                None,
                600,
            ),
            (
                "m-4",
                "owner/repo-a",
                4,
                None,
                "timeout",
                "2026-01-02T11:00:00",
                "2026-01-02T11:30:00",
                "No heartbeat",
                1800,
            ),
            (
                "m-5",
                "owner/repo-b",
                5,
                12,
                "completed",
                "2026-01-03T10:00:00",
                "2026-01-03T10:08:00",
                None,
                480,
            ),
        ]

        for r in records:
            cursor.execute(
                """INSERT INTO work_history
                   (minion_id, repo, issue_number, pr_number, status,
                    started_at, completed_at, error_message, duration_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                r,
            )
        conn.commit()
        conn.close()

        return state

    def test_get_work_history_no_filters(self, tmp_path):
        """get_work_history returns all records without filters."""
        state = self._make_state(str(tmp_path / "test.db"))
        history = state.get_work_history()
        assert len(history) == 5

    def test_get_work_history_repo_filter(self, tmp_path):
        """get_work_history filters by repo."""
        state = self._make_state(str(tmp_path / "test.db"))
        history = state.get_work_history(repo="owner/repo-a")
        assert len(history) == 3
        assert all(h["repo"] == "owner/repo-a" for h in history)

    def test_get_work_history_status_filter(self, tmp_path):
        """get_work_history filters by status."""
        state = self._make_state(str(tmp_path / "test.db"))
        history = state.get_work_history(status="completed")
        assert len(history) == 3
        assert all(h["status"] == "completed" for h in history)

    def test_get_work_history_combined_filters(self, tmp_path):
        """get_work_history combines repo and status filters."""
        state = self._make_state(str(tmp_path / "test.db"))
        history = state.get_work_history(repo="owner/repo-a", status="completed")
        assert len(history) == 1
        assert history[0]["issue_number"] == 1

    def test_get_work_history_limit(self, tmp_path):
        """get_work_history respects limit."""
        state = self._make_state(str(tmp_path / "test.db"))
        history = state.get_work_history(limit=2)
        assert len(history) == 2

    def test_get_distinct_repos(self, tmp_path):
        """get_distinct_repos returns sorted unique repo names."""
        state = self._make_state(str(tmp_path / "test.db"))
        repos = state.get_distinct_repos()
        assert repos == ["owner/repo-a", "owner/repo-b"]

    def test_get_distinct_repos_empty(self, tmp_path):
        """get_distinct_repos returns empty list when no history."""
        from nebulus_swarm.overlord.state import OverlordState

        state = OverlordState(db_path=str(tmp_path / "empty.db"))
        repos = state.get_distinct_repos()
        assert repos == []


# ---------------------------------------------------------------------------
# SwarmDataClient
# ---------------------------------------------------------------------------


class TestSwarmDataClient:
    """Tests for the SwarmDataClient."""

    def test_init(self):
        """Client initializes with URL and DB path."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        client = SwarmDataClient(
            overlord_url="http://localhost:9090",
            state_db_path="/tmp/test.db",
        )
        assert client.overlord_url == "http://localhost:9090"

    def test_url_trailing_slash_stripped(self):
        """Client strips trailing slash from URL."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        client = SwarmDataClient(overlord_url="http://localhost:8080/")
        assert client.overlord_url == "http://localhost:8080"

    @patch("nebulus_swarm.dashboard.data.requests.get")
    def test_get_status_success(self, mock_get):
        """get_status returns parsed JSON on success."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"status": "healthy"}
        mock_get.return_value.raise_for_status = MagicMock()

        client = SwarmDataClient()
        result = client.get_status()

        assert result == {"status": "healthy"}
        mock_get.assert_called_once_with("http://localhost:8080/status", timeout=5)

    @patch("nebulus_swarm.dashboard.data.requests.get")
    def test_get_status_connection_error(self, mock_get):
        """get_status returns None when Overlord is unreachable."""
        import requests as req

        from nebulus_swarm.dashboard.data import SwarmDataClient

        mock_get.side_effect = req.ConnectionError("Connection refused")

        client = SwarmDataClient()
        result = client.get_status()
        assert result is None

    @patch("nebulus_swarm.dashboard.data.requests.get")
    def test_api_caching(self, mock_get):
        """API responses are cached within TTL."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"status": "healthy"}
        mock_get.return_value.raise_for_status = MagicMock()

        client = SwarmDataClient()

        # First call
        client.get_status()
        # Second call should use cache
        client.get_status()

        assert mock_get.call_count == 1  # Only one actual request

    @patch("nebulus_swarm.dashboard.data.requests.get")
    def test_get_queue(self, mock_get):
        """get_queue returns parsed JSON."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"issues": [], "paused": False}
        mock_get.return_value.raise_for_status = MagicMock()

        client = SwarmDataClient()
        result = client.get_queue()
        assert result == {"issues": [], "paused": False}

    @patch("nebulus_swarm.dashboard.data.requests.get")
    def test_is_overlord_reachable(self, mock_get):
        """is_overlord_reachable returns True when API responds."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"status": "healthy"}
        mock_get.return_value.raise_for_status = MagicMock()

        client = SwarmDataClient()
        assert client.is_overlord_reachable() is True

    def test_get_work_history_with_state(self, tmp_path):
        """get_work_history reads from state DB."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        db_path = str(tmp_path / "state.db")

        # Create DB with test data
        from nebulus_swarm.overlord.state import OverlordState

        OverlordState(db_path=db_path)  # Creates schema
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO work_history
               (minion_id, repo, issue_number, pr_number, status,
                started_at, completed_at, error_message, duration_seconds)
               VALUES ('m-1', 'o/r', 1, 10, 'completed',
                       '2026-01-01T10:00:00', '2026-01-01T10:05:00', NULL, 300)"""
        )
        conn.commit()
        conn.close()

        client = SwarmDataClient(state_db_path=db_path)
        history = client.get_work_history()
        assert len(history) == 1
        assert history[0]["status"] == "completed"

    def test_get_work_history_no_db(self):
        """get_work_history returns empty list when DB is inaccessible."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        client = SwarmDataClient(state_db_path="/nonexistent/path/state.db")
        # Force state to None
        client._state = None
        history = client.get_work_history()
        assert history == []

    def test_get_metrics_empty(self):
        """get_metrics returns empty metrics when no data."""
        from nebulus_swarm.dashboard.data import SwarmDataClient

        client = SwarmDataClient(state_db_path="/nonexistent/path/state.db")
        client._state = None
        m = client.get_metrics()
        assert m["total"] == 0
        assert m["completion_rate"] == 0

    def test_get_metrics_with_data(self, tmp_path):
        """get_metrics computes correct aggregates."""
        from nebulus_swarm.dashboard.data import SwarmDataClient
        from nebulus_swarm.overlord.state import OverlordState

        db_path = str(tmp_path / "state.db")
        OverlordState(db_path=db_path)

        conn = sqlite3.connect(db_path)
        records = [
            (
                "m-1",
                "o/r",
                1,
                10,
                "completed",
                "2026-01-01T10:00:00",
                "2026-01-01T10:05:00",
                None,
                300,
            ),
            (
                "m-2",
                "o/r",
                2,
                None,
                "failed",
                "2026-01-01T11:00:00",
                "2026-01-01T11:03:00",
                "git_error: push",
                180,
            ),
            (
                "m-3",
                "o/r",
                3,
                11,
                "completed",
                "2026-01-01T12:00:00",
                "2026-01-01T12:10:00",
                None,
                600,
            ),
        ]
        for r in records:
            conn.execute(
                """INSERT INTO work_history
                   (minion_id, repo, issue_number, pr_number, status,
                    started_at, completed_at, error_message, duration_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                r,
            )
        conn.commit()
        conn.close()

        client = SwarmDataClient(state_db_path=db_path)
        m = client.get_metrics()

        assert m["total"] == 3
        assert m["completed"] == 2
        assert m["failed"] == 1
        assert m["completion_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert m["avg_duration"] == pytest.approx(360, abs=1)
        assert len(m["daily_stats"]) == 1
        assert "git_error" in m["error_types"]


# ---------------------------------------------------------------------------
# Overlord: /queue endpoint and /status pending_questions
# ---------------------------------------------------------------------------


class TestOverlordQueueEndpoint:
    """Tests for the new Overlord /queue endpoint."""

    @pytest.mark.asyncio
    async def test_queue_handler_returns_cached_data(self):
        """GET /queue returns cached scan results."""
        from nebulus_swarm.overlord.main import Overlord

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._last_queue_scan = [
                {"repo": "o/r", "number": 1, "title": "Fix bug", "priority": 0}
            ]
            overlord._paused = False

        request = MagicMock()
        response = await overlord._queue_handler(request)
        body = json.loads(response.body)

        assert len(body["issues"]) == 1
        assert body["issues"][0]["number"] == 1
        assert body["paused"] is False

    @pytest.mark.asyncio
    async def test_queue_handler_empty(self):
        """GET /queue returns empty list when no scan has run."""
        from nebulus_swarm.overlord.main import Overlord

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._last_queue_scan = []
            overlord._paused = True

        request = MagicMock()
        response = await overlord._queue_handler(request)
        body = json.loads(response.body)

        assert body["issues"] == []
        assert body["paused"] is True


class TestOverlordStatusPendingQuestions:
    """Tests for pending_questions in /status response."""

    @pytest.mark.asyncio
    async def test_status_includes_pending_questions(self):
        """GET /status includes pending_questions list."""
        from nebulus_swarm.overlord.main import Overlord, PendingQuestion

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._paused = False
            overlord._pending_questions = {
                "m-1": PendingQuestion(
                    minion_id="m-1",
                    question_id="q-1",
                    issue_number=42,
                    repo="o/r",
                    question_text="Which endpoint?",
                    thread_ts="ts-1",
                ),
            }

            # Mock dependencies
            overlord.state = MagicMock()
            overlord.state.get_active_minions.return_value = []
            overlord.docker = MagicMock()
            overlord.docker.is_available.return_value = True
            overlord.docker.list_minions.return_value = []
            overlord.config = MagicMock()
            overlord.config.minions.max_concurrent = 3
            overlord.config.minions.timeout_minutes = 30

        request = MagicMock()
        response = await overlord._status_handler(request)
        body = json.loads(response.body)

        assert "pending_questions" in body
        assert len(body["pending_questions"]) == 1
        pq = body["pending_questions"][0]
        assert pq["minion_id"] == "m-1"
        assert pq["question_text"] == "Which endpoint?"
        assert pq["answered"] is False

    @pytest.mark.asyncio
    async def test_status_empty_pending_questions(self):
        """GET /status returns empty list when no pending questions."""
        from nebulus_swarm.overlord.main import Overlord

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._paused = False
            overlord._pending_questions = {}

            overlord.state = MagicMock()
            overlord.state.get_active_minions.return_value = []
            overlord.docker = MagicMock()
            overlord.docker.is_available.return_value = True
            overlord.docker.list_minions.return_value = []
            overlord.config = MagicMock()
            overlord.config.minions.max_concurrent = 3
            overlord.config.minions.timeout_minutes = 30

        request = MagicMock()
        response = await overlord._status_handler(request)
        body = json.loads(response.body)

        assert body["pending_questions"] == []
