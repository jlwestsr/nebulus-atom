# nebulus_atom/commands/proposals.py
"""CLI commands for managing enhancement proposals."""

from typing import List

from nebulus_swarm.overlord.proposals import EnhancementProposal


def format_proposal_list(proposals: List[EnhancementProposal]) -> str:
    """Format a list of proposals for terminal display."""
    if not proposals:
        return "No pending proposals."

    lines = []
    for p in proposals:
        lines.append(f"  [{p.type.value}] {p.title}")
        lines.append(f"    ID: {p.id[:8]}...  Status: {p.status.value}")
        lines.append("")
    return "\n".join(lines)


def format_proposal_detail(proposal: EnhancementProposal) -> str:
    """Format a single proposal with full detail."""
    lines = [
        f"Proposal: {proposal.title}",
        f"Type: {proposal.type.value}",
        f"Status: {proposal.status.value}",
        f"Impact: {proposal.estimated_impact}  Risk: {proposal.risk}",
        "",
        "Rationale:",
        f"  {proposal.rationale}",
        "",
        "Proposed Action:",
        f"  {proposal.proposed_action}",
    ]
    if proposal.related_issues:
        lines.append("")
        lines.append(
            f"Related Issues: {', '.join(f'#{i}' for i in proposal.related_issues)}"
        )
    return "\n".join(lines)
