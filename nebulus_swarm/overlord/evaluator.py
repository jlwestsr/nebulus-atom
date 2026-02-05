"""Supervisor evaluation layer for Minion output."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from nebulus_swarm.reviewer.checks import ChecksReport, CheckStatus
from nebulus_swarm.reviewer.pr_reviewer import ReviewDecision, ReviewResult

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


class Evaluator:
    """Evaluates Minion output after task completion."""

    def __init__(
        self,
        llm_base_url: str,
        llm_model: str,
        github_token: str,
        llm_api_key: str = "not-needed",
        llm_timeout: int = 120,
    ):
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.github_token = github_token
        self.llm_api_key = llm_api_key
        self.llm_timeout = llm_timeout

    def can_revise(self, revision_number: int) -> bool:
        """Check if another revision is allowed."""
        return revision_number < MAX_REVISIONS

    def evaluate(
        self,
        checks: ChecksReport,
        review: ReviewResult,
        repo: str,
        pr_number: int,
        revision_number: int = 0,
        issue_number: int = 0,
        branch: str = "",
    ) -> tuple[EvaluationResult, Optional[RevisionRequest]]:
        """Evaluate a Minion's work and determine if revision is needed.

        Args:
            checks: ChecksReport from automated checks.
            review: ReviewResult from LLM review.
            repo: Repository name (owner/repo).
            pr_number: Pull request number.
            revision_number: Current revision number (0 for first attempt).
            issue_number: GitHub issue number.
            branch: Branch name.

        Returns:
            Tuple of (EvaluationResult, Optional[RevisionRequest]).
            RevisionRequest is created if work needs revision and can_revise is True.
        """
        # Get the evaluation result
        result = self._score(checks, review, repo, pr_number, revision_number)

        # Determine if revision is needed and allowed
        revision_request = None
        if result.overall == CheckScore.NEEDS_REVISION and self.can_revise(
            revision_number
        ):
            revision_request = RevisionRequest(
                repo=repo,
                pr_number=pr_number,
                issue_number=issue_number,
                branch=branch,
                feedback=result.combined_feedback,
                revision_number=revision_number + 1,
            )

        return result, revision_request

    def _score(
        self,
        checks: ChecksReport,
        review: ReviewResult,
        repo: str,
        pr_number: int,
        revision_number: int = 0,
    ) -> EvaluationResult:
        """Score check results and LLM review into an EvaluationResult."""
        # Tests: any pytest failure -> NEEDS_REVISION
        test_score = CheckScore.PASS
        test_feedback = ""
        for r in checks.results:
            if r.name.lower() in ("pytest", "tests") and r.status == CheckStatus.FAILED:
                test_score = CheckScore.NEEDS_REVISION
                test_feedback = r.message
                break

        # Lint: any lint failure -> NEEDS_REVISION
        lint_score = CheckScore.PASS
        lint_feedback = ""
        for r in checks.results:
            if (
                r.name.lower() in ("ruff", "lint", "flake8")
                and r.status == CheckStatus.FAILED
            ):
                lint_score = CheckScore.NEEDS_REVISION
                lint_feedback = r.message
                break

        # Review: REQUEST_CHANGES -> NEEDS_REVISION, APPROVE/COMMENT -> PASS
        review_score = CheckScore.PASS
        review_feedback = ""
        if review.decision == ReviewDecision.REQUEST_CHANGES:
            review_score = CheckScore.NEEDS_REVISION
            review_feedback = review.summary
            if review.issues:
                review_feedback += "\n" + "\n".join(f"- {i}" for i in review.issues)

        return EvaluationResult(
            pr_number=pr_number,
            repo=repo,
            test_score=test_score,
            lint_score=lint_score,
            review_score=review_score,
            revision_number=revision_number,
            test_feedback=test_feedback,
            lint_feedback=lint_feedback,
            review_feedback=review_feedback,
        )
