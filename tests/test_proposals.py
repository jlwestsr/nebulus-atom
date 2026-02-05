"""Tests for the enhancement proposal system."""

from nebulus_swarm.overlord.proposals import (
    EnhancementProposal,
    ProposalStatus,
    ProposalStore,
    ProposalType,
)


class TestProposalTypes:
    def test_new_skill_type(self):
        assert ProposalType.NEW_SKILL.value == "new_skill"

    def test_statuses(self):
        assert ProposalStatus.PENDING.value == "pending"
        assert ProposalStatus.APPROVED.value == "approved"
        assert ProposalStatus.REJECTED.value == "rejected"
        assert ProposalStatus.IMPLEMENTED.value == "implemented"


class TestEnhancementProposal:
    def test_create_proposal(self):
        p = EnhancementProposal(
            type=ProposalType.NEW_SKILL,
            title="Add React testing skill",
            rationale="Minion failed React tests 3 times",
            proposed_action="Create a skill for React component testing",
        )
        assert p.id  # UUID auto-generated
        assert p.status == ProposalStatus.PENDING

    def test_is_actionable(self):
        p = EnhancementProposal(
            type=ProposalType.TOOL_FIX,
            title="Fix linting",
            rationale="Lint always fails",
            proposed_action="Update ruff config",
        )
        assert p.is_actionable  # pending
        p.status = ProposalStatus.APPROVED
        assert p.is_actionable  # approved but not implemented
        p.status = ProposalStatus.IMPLEMENTED
        assert not p.is_actionable


class TestProposalStore:
    def test_create_and_get(self, tmp_path):
        store = ProposalStore(db_path=str(tmp_path / "test.db"))
        p = EnhancementProposal(
            type=ProposalType.NEW_SKILL,
            title="Test proposal",
            rationale="Testing",
            proposed_action="Do something",
        )
        store.save(p)
        loaded = store.get(p.id)
        assert loaded is not None
        assert loaded.title == "Test proposal"

    def test_list_pending(self, tmp_path):
        store = ProposalStore(db_path=str(tmp_path / "test.db"))
        p1 = EnhancementProposal(
            type=ProposalType.NEW_SKILL,
            title="Pending",
            rationale="r",
            proposed_action="a",
        )
        p2 = EnhancementProposal(
            type=ProposalType.TOOL_FIX,
            title="Also pending",
            rationale="r",
            proposed_action="a",
        )
        store.save(p1)
        store.save(p2)
        pending = store.list_by_status(ProposalStatus.PENDING)
        assert len(pending) == 2

    def test_approve(self, tmp_path):
        store = ProposalStore(db_path=str(tmp_path / "test.db"))
        p = EnhancementProposal(
            type=ProposalType.CONFIG_CHANGE,
            title="Change config",
            rationale="r",
            proposed_action="a",
        )
        store.save(p)
        store.update_status(p.id, ProposalStatus.APPROVED)
        loaded = store.get(p.id)
        assert loaded.status == ProposalStatus.APPROVED

    def test_list_empty(self, tmp_path):
        store = ProposalStore(db_path=str(tmp_path / "test.db"))
        assert store.list_by_status(ProposalStatus.PENDING) == []

    def test_get_nonexistent_returns_none(self, tmp_path):
        store = ProposalStore(db_path=str(tmp_path / "test.db"))
        assert store.get("nonexistent-id") is None
