# nebulus_atom/commands/proposals.py
"""CLI commands for managing enhancement proposals."""

from pathlib import Path
from typing import List, Optional

from nebulus_swarm.overlord.proposals import (
    EnhancementProposal,
    ProposalStatus,
    ProposalStore,
)


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


def get_store(db_path: Optional[str] = None) -> ProposalStore:
    """Create a ProposalStore with the given or default path."""
    if db_path is None:
        home = Path.home()
        atom_dir = home / ".atom"
        atom_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(atom_dir / "proposals.db")
    return ProposalStore(db_path)


def list_proposals(db_path: Optional[str] = None) -> str:
    """List all pending proposals."""
    store = get_store(db_path)
    proposals = store.list_by_status(ProposalStatus.PENDING)
    return format_proposal_list(proposals)


def show_proposal(proposal_id: str, db_path: Optional[str] = None) -> str:
    """Show detailed information about a specific proposal."""
    store = get_store(db_path)
    proposal = store.get(proposal_id)
    if proposal is None:
        return f"Error: Proposal with ID '{proposal_id}' not found."
    return format_proposal_detail(proposal)


def approve_proposal(proposal_id: str, db_path: Optional[str] = None) -> str:
    """Approve a proposal."""
    store = get_store(db_path)
    proposal = store.get(proposal_id)
    if proposal is None:
        return f"Error: Proposal with ID '{proposal_id}' not found."
    store.update_status(proposal_id, ProposalStatus.APPROVED)
    return f"Proposal '{proposal.title}' has been approved."


def reject_proposal(proposal_id: str, db_path: Optional[str] = None) -> str:
    """Reject a proposal."""
    store = get_store(db_path)
    proposal = store.get(proposal_id)
    if proposal is None:
        return f"Error: Proposal with ID '{proposal_id}' not found."
    store.update_status(proposal_id, ProposalStatus.REJECTED)
    return f"Proposal '{proposal.title}' has been rejected."
