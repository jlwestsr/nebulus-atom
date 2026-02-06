"""Certification packages for compliance review.

Bundles proposals with their supporting evidence (tests, audits, evaluations)
into a single reviewable package for human approval.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Summary of test execution results."""

    __test__ = False  # Prevent pytest from collecting this dataclass

    total: int
    passed: int
    failed: int
    skipped: int = 0
    duration_seconds: float = 0.0

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate as a percentage."""
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100


@dataclass
class ImpactAnalysis:
    """Analysis of the proposal's potential impact."""

    files_affected: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    estimated_risk: str = "low"  # low, medium, high
    affected_components: List[str] = field(default_factory=list)
    notes: str = ""

    @property
    def churn(self) -> int:
        """Total lines changed."""
        return self.lines_added + self.lines_removed


@dataclass
class CertificationPackage:
    """A complete package for human review and approval.

    Contains the proposal plus all supporting evidence needed
    for an informed approval decision.
    """

    proposal_id: str
    proposal_title: str
    proposal_type: str
    proposal_rationale: str
    proposal_action: str

    # Supporting evidence
    diff_summary: str = ""
    test_results: Optional[TestResult] = None
    auditor_score: Optional[float] = None  # 0.0-1.0 confidence
    auditor_issues: List[str] = field(default_factory=list)
    evaluator_score: str = ""  # pass/fail/needs_revision
    evaluator_feedback: str = ""
    impact_analysis: Optional[ImpactAnalysis] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"  # pending, approved, rejected
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        d = {
            "proposal_id": self.proposal_id,
            "proposal_title": self.proposal_title,
            "proposal_type": self.proposal_type,
            "proposal_rationale": self.proposal_rationale,
            "proposal_action": self.proposal_action,
            "diff_summary": self.diff_summary,
            "test_results": asdict(self.test_results) if self.test_results else None,
            "auditor_score": self.auditor_score,
            "auditor_issues": self.auditor_issues,
            "evaluator_score": self.evaluator_score,
            "evaluator_feedback": self.evaluator_feedback,
            "impact_analysis": (
                asdict(self.impact_analysis) if self.impact_analysis else None
            ),
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CertificationPackage":
        """Create from dictionary."""
        test_results = None
        if d.get("test_results"):
            test_results = TestResult(**d["test_results"])

        impact = None
        if d.get("impact_analysis"):
            impact = ImpactAnalysis(**d["impact_analysis"])

        return cls(
            proposal_id=d["proposal_id"],
            proposal_title=d["proposal_title"],
            proposal_type=d["proposal_type"],
            proposal_rationale=d["proposal_rationale"],
            proposal_action=d["proposal_action"],
            diff_summary=d.get("diff_summary", ""),
            test_results=test_results,
            auditor_score=d.get("auditor_score"),
            auditor_issues=d.get("auditor_issues", []),
            evaluator_score=d.get("evaluator_score", ""),
            evaluator_feedback=d.get("evaluator_feedback", ""),
            impact_analysis=impact,
            created_at=datetime.fromisoformat(d["created_at"]),
            status=d.get("status", "pending"),
            reviewed_by=d.get("reviewed_by"),
            reviewed_at=(
                datetime.fromisoformat(d["reviewed_at"])
                if d.get("reviewed_at")
                else None
            ),
        )

    def to_json(self, indent: int = 2) -> str:
        """Export as JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def format_summary(self) -> str:
        """Format a human-readable summary."""
        lines = [
            "=== Certification Package ===",
            f"Proposal: {self.proposal_title}",
            f"Type: {self.proposal_type}",
            f"Status: {self.status}",
            "",
            "Rationale:",
            f"  {self.proposal_rationale}",
            "",
            "Proposed Action:",
            f"  {self.proposal_action}",
        ]

        if self.diff_summary:
            lines.extend(["", "Diff Summary:", f"  {self.diff_summary}"])

        if self.test_results:
            tr = self.test_results
            lines.extend(
                [
                    "",
                    "Test Results:",
                    f"  {tr.passed}/{tr.total} passed ({tr.pass_rate:.1f}%)",
                    f"  Duration: {tr.duration_seconds:.1f}s",
                ]
            )

        if self.auditor_score is not None:
            lines.extend(
                [
                    "",
                    "Auditor Assessment:",
                    f"  Confidence: {self.auditor_score * 100:.0f}%",
                ]
            )
            if self.auditor_issues:
                lines.append(f"  Issues: {len(self.auditor_issues)}")
                for issue in self.auditor_issues[:3]:  # Show first 3
                    lines.append(f"    - {issue}")

        if self.evaluator_score:
            lines.extend(
                [
                    "",
                    "Evaluator Assessment:",
                    f"  Result: {self.evaluator_score}",
                ]
            )
            if self.evaluator_feedback:
                lines.append(f"  Feedback: {self.evaluator_feedback[:100]}...")

        if self.impact_analysis:
            ia = self.impact_analysis
            lines.extend(
                [
                    "",
                    "Impact Analysis:",
                    f"  Files: {ia.files_affected}, Lines: +{ia.lines_added}/-{ia.lines_removed}",
                    f"  Risk: {ia.estimated_risk}",
                ]
            )

        return "\n".join(lines)


class CertificationBuilder:
    """Assembles certification packages from proposal and evidence."""

    def __init__(self):
        """Initialize the builder."""
        self._proposal_id: Optional[str] = None
        self._proposal_title: str = ""
        self._proposal_type: str = ""
        self._proposal_rationale: str = ""
        self._proposal_action: str = ""
        self._diff_summary: str = ""
        self._test_results: Optional[TestResult] = None
        self._auditor_score: Optional[float] = None
        self._auditor_issues: List[str] = []
        self._evaluator_score: str = ""
        self._evaluator_feedback: str = ""
        self._impact_analysis: Optional[ImpactAnalysis] = None

    def from_proposal(self, proposal: "EnhancementProposal") -> "CertificationBuilder":
        """Set proposal details from an EnhancementProposal.

        Args:
            proposal: The enhancement proposal to certify.

        Returns:
            self for chaining.
        """
        self._proposal_id = proposal.id
        self._proposal_title = proposal.title
        self._proposal_type = proposal.type.value
        self._proposal_rationale = proposal.rationale
        self._proposal_action = proposal.proposed_action
        return self

    def with_diff(self, diff_summary: str) -> "CertificationBuilder":
        """Add diff summary.

        Args:
            diff_summary: Summary of code changes.

        Returns:
            self for chaining.
        """
        self._diff_summary = diff_summary
        return self

    def with_test_results(
        self,
        total: int,
        passed: int,
        failed: int,
        skipped: int = 0,
        duration: float = 0.0,
    ) -> "CertificationBuilder":
        """Add test execution results.

        Returns:
            self for chaining.
        """
        self._test_results = TestResult(
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_seconds=duration,
        )
        return self

    def with_audit_result(self, audit_result: "AuditResult") -> "CertificationBuilder":
        """Add auditor assessment from AuditResult.

        Args:
            audit_result: Result from the Auditor.

        Returns:
            self for chaining.
        """
        self._auditor_score = audit_result.confidence
        self._auditor_issues = [
            f"{i.severity.value}: {i.message}" for i in audit_result.issues
        ]
        return self

    def with_evaluation(
        self, eval_result: "EvaluationResult"
    ) -> "CertificationBuilder":
        """Add evaluator assessment from EvaluationResult.

        Args:
            eval_result: Result from the Evaluator.

        Returns:
            self for chaining.
        """
        self._evaluator_score = eval_result.overall.value
        self._evaluator_feedback = eval_result.combined_feedback
        return self

    def with_impact(
        self,
        files_affected: int = 0,
        lines_added: int = 0,
        lines_removed: int = 0,
        risk: str = "low",
        components: Optional[List[str]] = None,
        notes: str = "",
    ) -> "CertificationBuilder":
        """Add impact analysis.

        Returns:
            self for chaining.
        """
        self._impact_analysis = ImpactAnalysis(
            files_affected=files_affected,
            lines_added=lines_added,
            lines_removed=lines_removed,
            estimated_risk=risk,
            affected_components=components or [],
            notes=notes,
        )
        return self

    def build(self) -> CertificationPackage:
        """Build the certification package.

        Returns:
            Complete CertificationPackage.

        Raises:
            ValueError: If required fields are missing.
        """
        if not self._proposal_id:
            raise ValueError("Proposal is required. Call from_proposal() first.")

        return CertificationPackage(
            proposal_id=self._proposal_id,
            proposal_title=self._proposal_title,
            proposal_type=self._proposal_type,
            proposal_rationale=self._proposal_rationale,
            proposal_action=self._proposal_action,
            diff_summary=self._diff_summary,
            test_results=self._test_results,
            auditor_score=self._auditor_score,
            auditor_issues=self._auditor_issues,
            evaluator_score=self._evaluator_score,
            evaluator_feedback=self._evaluator_feedback,
            impact_analysis=self._impact_analysis,
        )


# Type hints for imports (avoid circular)
if TYPE_CHECKING:
    from nebulus_swarm.overlord.auditor import AuditResult
    from nebulus_swarm.overlord.evaluator import EvaluationResult
    from nebulus_swarm.overlord.proposals import EnhancementProposal
