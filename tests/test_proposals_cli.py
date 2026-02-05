# tests/test_proposals_cli.py
"""Tests for the proposals CLI commands."""

from nebulus_atom.commands.proposals import format_proposal_list, format_proposal_detail
from nebulus_swarm.overlord.proposals import (
    EnhancementProposal,
    ProposalType,
)


class TestFormatProposalList:
    def test_empty_list(self):
        output = format_proposal_list([])
        assert "No pending proposals" in output

    def test_formats_proposals(self):
        proposals = [
            EnhancementProposal(
                type=ProposalType.NEW_SKILL,
                title="Add React skill",
                rationale="Failures",
                proposed_action="Create skill",
            ),
        ]
        output = format_proposal_list(proposals)
        assert "Add React skill" in output
        assert "new_skill" in output


class TestFormatProposalDetail:
    def test_shows_all_fields(self):
        p = EnhancementProposal(
            type=ProposalType.TOOL_FIX,
            title="Fix linter",
            rationale="Ruff config wrong",
            proposed_action="Update .ruff.toml",
            estimated_impact="Low",
            risk="Low",
        )
        output = format_proposal_detail(p)
        assert "Fix linter" in output
        assert "Ruff config wrong" in output
        assert "Update .ruff.toml" in output
