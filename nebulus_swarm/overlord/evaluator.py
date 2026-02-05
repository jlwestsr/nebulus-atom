"""Supervisor evaluation layer for Minion output."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

MAX_REVISIONS = 2


class CheckScore(Enum):
    """Score for a single evaluation check."""

    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVISION = "needs_revision"


@dataclass
class EvaluationResult:
    """Result of evaluating a Minion's work."""

    pr_number: int
    repo: str
    test_score: CheckScore
    lint_score: CheckScore
    review_score: CheckScore
    revision_number: int = 0
    test_feedback: str = ""
    lint_feedback: str = ""
    review_feedback: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def overall(self) -> CheckScore:
        """Compute overall score from individual checks."""
        scores = [self.test_score, self.lint_score, self.review_score]
        if any(s == CheckScore.FAIL for s in scores):
            return CheckScore.FAIL
        if any(s == CheckScore.NEEDS_REVISION for s in scores):
            return CheckScore.NEEDS_REVISION
        return CheckScore.PASS

    @property
    def combined_feedback(self) -> str:
        """Combine all feedback into a single string."""
        parts = []
        if self.test_feedback:
            parts.append(f"Tests: {self.test_feedback}")
        if self.lint_feedback:
            parts.append(f"Lint: {self.lint_feedback}")
        if self.review_feedback:
            parts.append(f"Review: {self.review_feedback}")
        return "\n".join(parts)


@dataclass
class RevisionRequest:
    """Request for a Minion to revise its work."""

    repo: str
    pr_number: int
    issue_number: int
    branch: str
    feedback: str
    revision_number: int
