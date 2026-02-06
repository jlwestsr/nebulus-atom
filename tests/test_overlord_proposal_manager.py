"""Tests for Overlord Proposal Manager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nebulus_swarm.overlord.action_scope import ActionScope
from nebulus_swarm.overlord.dispatch import DispatchPlan, DispatchResult, DispatchStep
from nebulus_swarm.overlord.proposal_manager import (
    Proposal,
    ProposalManager,
    ProposalState,
    ProposalStore,
    _format_proposal_message,
)


# --- Store Tests ---


class TestProposalStore:
    """Tests for SQLite-backed proposal storage."""

    def test_save_and_get(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        proposal = Proposal(
            id="abc123",
            task="merge core develop to main",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test reason",
            state=ProposalState.PENDING,
            created_at="2026-02-06T00:00:00+00:00",
        )
        store.save(proposal)
        got = store.get("abc123")
        assert got is not None
        assert got.id == "abc123"
        assert got.task == "merge core develop to main"
        assert got.scope_projects == ["core"]
        assert got.state == ProposalState.PENDING

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        assert store.get("nonexistent") is None

    def test_get_by_thread(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        proposal = Proposal(
            id="thread1",
            task="test",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            thread_ts="1234567890.123456",
            created_at="2026-02-06T00:00:00+00:00",
        )
        store.save(proposal)
        got = store.get_by_thread("1234567890.123456")
        assert got is not None
        assert got.id == "thread1"

    def test_get_by_thread_only_pending(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        proposal = Proposal(
            id="done1",
            task="test",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            thread_ts="999.999",
            created_at="2026-02-06T00:00:00+00:00",
        )
        store.save(proposal)
        store.update_state("done1", ProposalState.DENIED)
        assert store.get_by_thread("999.999") is None

    def test_list_pending(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        for i in range(3):
            p = Proposal(
                id=f"p{i}",
                task=f"task {i}",
                scope_projects=["core"],
                scope_impact="low",
                affects_remote=False,
                reason="test",
                state=ProposalState.PENDING,
                created_at=f"2026-02-0{i + 1}T00:00:00+00:00",
            )
            store.save(p)
        store.update_state("p1", ProposalState.APPROVED)
        pending = store.list_pending()
        assert len(pending) == 2
        assert pending[0].id == "p0"
        assert pending[1].id == "p2"

    def test_update_state(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        proposal = Proposal(
            id="upd1",
            task="test",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            created_at="2026-02-06T00:00:00+00:00",
        )
        store.save(proposal)
        store.update_state("upd1", ProposalState.COMPLETED, "done")
        got = store.get("upd1")
        assert got.state == ProposalState.COMPLETED
        assert got.resolved_at is not None
        assert got.result_summary == "done"

    def test_cleanup_expired(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        # Create an old proposal
        old = Proposal(
            id="old1",
            task="stale",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            created_at="2020-01-01T00:00:00+00:00",  # Very old
        )
        store.save(old)
        # Create a fresh proposal
        fresh = Proposal(
            id="fresh1",
            task="new",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            created_at="2099-01-01T00:00:00+00:00",  # Future
        )
        store.save(fresh)
        count = store.cleanup_expired(ttl_minutes=1)
        assert count == 1
        assert store.get("old1").state == ProposalState.EXPIRED
        assert store.get("fresh1").state == ProposalState.PENDING


# --- Lifecycle Tests ---


class TestProposalLifecycle:
    """Tests for the proposal lifecycle manager."""

    def _make_manager(self, tmp_path: Path) -> ProposalManager:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        return ProposalManager(store=store, dispatch=dispatch)

    @pytest.mark.asyncio
    async def test_propose_creates_proposal(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        scope = ActionScope(
            projects=["core"],
            branches=["develop", "main"],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        pid = await mgr.propose("merge core", scope, "test")
        assert pid is not None
        proposal = mgr.store.get(pid)
        assert proposal is not None
        assert proposal.state == ProposalState.PENDING
        assert proposal.task == "merge core"

    @pytest.mark.asyncio
    async def test_propose_with_slack_bot(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        mock_bot = MagicMock()
        mock_response = {"ts": "1234.5678"}
        mock_bot.app.client.chat_postMessage = AsyncMock(return_value=mock_response)
        mock_bot.channel_id = "C123"
        mgr.slack_bot = mock_bot

        scope = ActionScope(
            projects=["core"],
            branches=[],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        pid = await mgr.propose("test task", scope, "reason")
        proposal = mgr.store.get(pid)
        assert proposal.thread_ts == "1234.5678"
        mock_bot.app.client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_reply_approve(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        proposal = Proposal(
            id="reply1",
            task="test",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            thread_ts="thread.123",
            created_at="2026-02-06T00:00:00+00:00",
        )
        mgr.store.save(proposal)

        result = await mgr.handle_reply("thread.123", "approve")
        assert result is not None
        assert "approved" in result.lower()

    @pytest.mark.asyncio
    async def test_handle_reply_deny(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        proposal = Proposal(
            id="reply2",
            task="test",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            thread_ts="thread.456",
            created_at="2026-02-06T00:00:00+00:00",
        )
        mgr.store.save(proposal)

        result = await mgr.handle_reply("thread.456", "deny")
        assert "denied" in result.lower()
        assert mgr.store.get("reply2").state == ProposalState.DENIED

    @pytest.mark.asyncio
    async def test_handle_reply_unmatched(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        result = await mgr.handle_reply("unknown.thread", "approve")
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_reply_not_approval(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        proposal = Proposal(
            id="reply3",
            task="test",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            thread_ts="thread.789",
            created_at="2026-02-06T00:00:00+00:00",
        )
        mgr.store.save(proposal)

        result = await mgr.handle_reply("thread.789", "what is this?")
        assert result is None
        assert mgr.store.get("reply3").state == ProposalState.PENDING


# --- Execution Tests ---


class TestProposalExecution:
    """Tests for executing approved proposals."""

    @pytest.mark.asyncio
    async def test_execute_approved_success(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        dispatch.execute.return_value = DispatchResult(status="success")
        mgr = ProposalManager(store=store, dispatch=dispatch)

        scope = ActionScope(
            projects=["core"],
            branches=[],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        plan = DispatchPlan(
            task="test",
            steps=[DispatchStep(id="s1", action="test", project="core")],
            scope=scope,
            estimated_duration=10,
            requires_approval=True,
        )
        pid = await mgr.propose("test", scope, "reason", plan=plan)
        store.update_state(pid, ProposalState.APPROVED)

        result = await mgr.execute_approved(pid)
        assert result is not None
        assert result.status == "success"
        assert store.get(pid).state == ProposalState.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_approved_failure(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        dispatch.execute.return_value = DispatchResult(
            status="failed", reason="git error"
        )
        mgr = ProposalManager(store=store, dispatch=dispatch)

        scope = ActionScope(
            projects=["core"],
            branches=[],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="low",
        )
        plan = DispatchPlan(
            task="test",
            steps=[DispatchStep(id="s1", action="test", project="core")],
            scope=scope,
            estimated_duration=10,
            requires_approval=True,
        )
        pid = await mgr.propose("test", scope, "reason", plan=plan)
        store.update_state(pid, ProposalState.APPROVED)

        result = await mgr.execute_approved(pid)
        assert result.status == "failed"
        assert store.get(pid).state == ProposalState.FAILED

    @pytest.mark.asyncio
    async def test_execute_no_cached_plan(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        mgr = ProposalManager(store=store, dispatch=dispatch)

        result = await mgr.execute_approved("nonexistent")
        assert result is None


# --- Formatting Tests ---


class TestProposalFormatting:
    """Tests for proposal message formatting."""

    def test_format_proposal_message(self) -> None:
        proposal = Proposal(
            id="fmt1",
            task="Merge Core develop to main",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=True,
            reason="Routine release",
            state=ProposalState.PENDING,
            created_at="2026-02-06T00:00:00+00:00",
        )
        msg = _format_proposal_message(proposal)
        assert "Merge Core develop to main" in msg
        assert "core" in msg
        assert "affects remote" in msg
        assert "approve" in msg.lower()
        assert "deny" in msg.lower()

    def test_format_local_only(self) -> None:
        proposal = Proposal(
            id="fmt2",
            task="Clean branches",
            scope_projects=["prime"],
            scope_impact="medium",
            affects_remote=False,
            reason="Stale branches detected",
            state=ProposalState.PENDING,
            created_at="2026-02-06T00:00:00+00:00",
        )
        msg = _format_proposal_message(proposal)
        assert "local only" in msg

    def test_format_multi_project(self) -> None:
        proposal = Proposal(
            id="fmt3",
            task="Release core v1.0",
            scope_projects=["core", "prime", "edge"],
            scope_impact="high",
            affects_remote=True,
            reason="Version bump",
            state=ProposalState.PENDING,
            created_at="2026-02-06T00:00:00+00:00",
        )
        msg = _format_proposal_message(proposal)
        assert "core, prime, edge" in msg


# --- Expiry Tests ---


class TestProposalExpiry:
    """Tests for proposal expiry and cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        mgr = ProposalManager(store=store, dispatch=dispatch)

        # Add old proposal
        old = Proposal(
            id="exp1",
            task="old",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            created_at="2020-01-01T00:00:00+00:00",
        )
        store.save(old)

        count = await mgr.cleanup_expired(ttl_minutes=1)
        assert count == 1
        assert store.get("exp1").state == ProposalState.EXPIRED

    @pytest.mark.asyncio
    async def test_cleanup_skips_fresh(self, tmp_path: Path) -> None:
        store = ProposalStore(str(tmp_path / "proposals.db"))
        dispatch = MagicMock()
        mgr = ProposalManager(store=store, dispatch=dispatch)

        fresh = Proposal(
            id="fresh1",
            task="new",
            scope_projects=["core"],
            scope_impact="low",
            affects_remote=False,
            reason="test",
            state=ProposalState.PENDING,
            created_at="2099-01-01T00:00:00+00:00",
        )
        store.save(fresh)

        count = await mgr.cleanup_expired(ttl_minutes=30)
        assert count == 0
        assert store.get("fresh1").state == ProposalState.PENDING


# --- Proposal Dataclass Tests ---


class TestProposalDataclass:
    """Tests for the Proposal dataclass."""

    def test_is_pending(self) -> None:
        p = Proposal(
            id="x",
            task="t",
            scope_projects=[],
            scope_impact="low",
            affects_remote=False,
            reason="r",
            state=ProposalState.PENDING,
        )
        assert p.is_pending is True

    def test_not_pending_when_approved(self) -> None:
        p = Proposal(
            id="x",
            task="t",
            scope_projects=[],
            scope_impact="low",
            affects_remote=False,
            reason="r",
            state=ProposalState.APPROVED,
        )
        assert p.is_pending is False
