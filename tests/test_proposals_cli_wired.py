# tests/test_proposals_cli_wired.py
"""Tests for the wired proposals CLI commands."""

import pytest

pytest.importorskip("nebulus_swarm.overlord.proposals")

from nebulus_atom.commands.proposals import (
    approve_proposal,
    get_store,
    list_proposals,
    reject_proposal,
    show_proposal,
)
from nebulus_swarm.overlord.proposals import (
    EnhancementProposal,
    ProposalStatus,
    ProposalType,
)


class TestGetStore:
    def test_creates_store(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = get_store(db_path)
        assert store is not None
        assert store.db_path == db_path


class TestListProposals:
    def test_list_empty(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        result = list_proposals(db_path)
        assert "No pending proposals" in result

    def test_list_with_proposals(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = get_store(db_path)
        p1 = EnhancementProposal(
            type=ProposalType.NEW_SKILL,
            title="First proposal",
            rationale="Test",
            proposed_action="Do something",
        )
        p2 = EnhancementProposal(
            type=ProposalType.TOOL_FIX,
            title="Second proposal",
            rationale="Test",
            proposed_action="Fix something",
        )
        store.save(p1)
        store.save(p2)
        result = list_proposals(db_path)
        assert "First proposal" in result
        assert "Second proposal" in result


class TestShowProposal:
    def test_show_proposal(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = get_store(db_path)
        p = EnhancementProposal(
            type=ProposalType.CONFIG_CHANGE,
            title="Config change",
            rationale="Need to update config",
            proposed_action="Update config file",
        )
        store.save(p)
        result = show_proposal(p.id, db_path)
        assert "Config change" in result
        assert "Need to update config" in result
        assert "Update config file" in result

    def test_show_missing(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        result = show_proposal("missing-id", db_path)
        assert "not found" in result.lower() or "error" in result.lower()


class TestApproveProposal:
    def test_approve_proposal(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = get_store(db_path)
        p = EnhancementProposal(
            type=ProposalType.WORKFLOW_IMPROVEMENT,
            title="Improve workflow",
            rationale="Current workflow slow",
            proposed_action="Optimize steps",
        )
        store.save(p)
        result = approve_proposal(p.id, db_path)
        assert "approved" in result.lower()
        loaded = store.get(p.id)
        assert loaded.status == ProposalStatus.APPROVED

    def test_approve_missing(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        result = approve_proposal("missing-id", db_path)
        assert "not found" in result.lower() or "error" in result.lower()


class TestRejectProposal:
    def test_reject_proposal(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = get_store(db_path)
        p = EnhancementProposal(
            type=ProposalType.NEW_SKILL,
            title="New skill",
            rationale="Needed for testing",
            proposed_action="Create new skill",
        )
        store.save(p)
        result = reject_proposal(p.id, db_path)
        assert "rejected" in result.lower()
        loaded = store.get(p.id)
        assert loaded.status == ProposalStatus.REJECTED

    def test_reject_missing(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        result = reject_proposal("missing-id", db_path)
        assert "not found" in result.lower() or "error" in result.lower()
