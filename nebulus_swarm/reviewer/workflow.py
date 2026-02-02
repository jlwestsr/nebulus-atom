"""Automated PR review workflow orchestration."""

import logging
from dataclasses import dataclass
from typing import Optional

from nebulus_swarm.reviewer.checks import CheckRunner, ChecksReport
from nebulus_swarm.reviewer.llm_review import LLMReviewer, create_review_summary
from nebulus_swarm.reviewer.pr_reviewer import (
    PRDetails,
    PRReviewer,
    ReviewDecision,
    ReviewResult,
)

logger = logging.getLogger(__name__)


@dataclass
class ReviewConfig:
    """Configuration for PR review workflow."""

    github_token: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str = "not-needed"
    llm_timeout: int = 120
    max_diff_lines: int = 500
    auto_merge_enabled: bool = False
    merge_method: str = "squash"
    run_local_checks: bool = True
    min_confidence_for_approve: float = 0.8


@dataclass
class WorkflowResult:
    """Result of a complete review workflow."""

    pr_details: PRDetails
    llm_result: ReviewResult
    checks_report: Optional[ChecksReport] = None
    review_posted: bool = False
    merged: bool = False
    error: Optional[str] = None

    @property
    def summary(self) -> str:
        """Get a summary of the workflow result."""
        status = []
        status.append(f"PR: {self.pr_details.repo}#{self.pr_details.number}")
        status.append(f"Decision: {self.llm_result.decision.value}")
        status.append(f"Confidence: {self.llm_result.confidence:.0%}")

        if self.checks_report:
            status.append(
                f"Checks: {self.checks_report.passed_count} passed, "
                f"{self.checks_report.failed_count} failed"
            )

        if self.review_posted:
            status.append("Review posted: Yes")

        if self.merged:
            status.append("Merged: Yes")

        if self.error:
            status.append(f"Error: {self.error}")

        return " | ".join(status)


class ReviewWorkflow:
    """Orchestrates the complete PR review process."""

    def __init__(self, config: ReviewConfig):
        """Initialize review workflow.

        Args:
            config: Workflow configuration.
        """
        self.config = config
        self._pr_reviewer: Optional[PRReviewer] = None
        self._llm_reviewer: Optional[LLMReviewer] = None

    @property
    def pr_reviewer(self) -> PRReviewer:
        """Get or create PR reviewer instance."""
        if self._pr_reviewer is None:
            self._pr_reviewer = PRReviewer(self.config.github_token)
        return self._pr_reviewer

    @property
    def llm_reviewer(self) -> LLMReviewer:
        """Get or create LLM reviewer instance."""
        if self._llm_reviewer is None:
            self._llm_reviewer = LLMReviewer(
                base_url=self.config.llm_base_url,
                model=self.config.llm_model,
                api_key=self.config.llm_api_key,
                timeout=self.config.llm_timeout,
            )
        return self._llm_reviewer

    def review_pr(
        self,
        repo: str,
        pr_number: int,
        post_review: bool = True,
        auto_merge: bool = False,
        repo_path: Optional[str] = None,
    ) -> WorkflowResult:
        """Run complete review workflow on a PR.

        Args:
            repo: Repository in owner/name format.
            pr_number: Pull request number.
            post_review: Whether to post review to GitHub.
            auto_merge: Whether to auto-merge if eligible.
            repo_path: Local repo path for running checks (optional).

        Returns:
            WorkflowResult with complete review information.
        """
        logger.info(f"Starting review workflow for {repo}#{pr_number}")

        try:
            # Step 1: Fetch PR details
            logger.info("Fetching PR details...")
            pr_details = self.pr_reviewer.get_pr_details(repo, pr_number)

            # Step 2: Run local checks (if enabled and repo path provided)
            checks_report = None
            if self.config.run_local_checks and repo_path:
                logger.info("Running local checks...")
                checks_report = self._run_checks(pr_details, repo_path)

            # Step 3: Get LLM review
            logger.info("Getting LLM review...")
            llm_result = self.llm_reviewer.review_pr(
                pr_details, max_diff_lines=self.config.max_diff_lines
            )

            # Merge checks results into LLM result
            if checks_report:
                llm_result.checks_passed = checks_report.all_passed

            # Step 4: Post review to GitHub
            review_posted = False
            if post_review:
                logger.info("Posting review to GitHub...")
                checks_summary = checks_report.get_summary() if checks_report else None
                review_posted = self._post_review(
                    repo, pr_number, pr_details, llm_result, checks_summary
                )

            # Step 5: Auto-merge if eligible
            merged = False
            auto_merge_enabled = auto_merge and self.config.auto_merge_enabled
            if auto_merge_enabled and llm_result.can_auto_merge:
                logger.info("Attempting auto-merge...")
                merged = self.pr_reviewer.merge_pr(
                    repo, pr_number, merge_method=self.config.merge_method
                )

            result = WorkflowResult(
                pr_details=pr_details,
                llm_result=llm_result,
                checks_report=checks_report,
                review_posted=review_posted,
                merged=merged,
            )

            logger.info(f"Review workflow complete: {result.summary}")
            return result

        except Exception as e:
            logger.error(f"Review workflow failed: {e}")
            # Return partial result with error
            return WorkflowResult(
                pr_details=PRDetails(
                    repo=repo,
                    number=pr_number,
                    title="",
                    body="",
                    author="",
                    base_branch="",
                    head_branch="",
                    created_at=None,
                ),
                llm_result=ReviewResult(
                    decision=ReviewDecision.COMMENT,
                    summary=f"Review workflow failed: {e}",
                    confidence=0.0,
                    issues=[str(e)],
                ),
                error=str(e),
            )

    def _run_checks(self, pr_details: PRDetails, repo_path: str) -> ChecksReport:
        """Run automated checks on changed files.

        Args:
            pr_details: PR details with changed files.
            repo_path: Path to local repository.

        Returns:
            ChecksReport with all check results.
        """
        runner = CheckRunner(repo_path)
        changed_files = [f.filename for f in pr_details.files]
        return runner.run_all_checks(changed_files)

    def _post_review(
        self,
        repo: str,
        pr_number: int,
        pr_details: PRDetails,
        llm_result: ReviewResult,
        checks_summary: Optional[str] = None,
    ) -> bool:
        """Post review to GitHub.

        Args:
            repo: Repository name.
            pr_number: PR number.
            pr_details: PR details.
            llm_result: LLM review result.
            checks_summary: Optional checks summary.

        Returns:
            True if review was posted successfully.
        """
        # Create complete review summary
        full_summary = create_review_summary(pr_details, llm_result, checks_summary)

        # Update result summary with full content
        full_result = ReviewResult(
            decision=llm_result.decision,
            summary=full_summary,
            inline_comments=llm_result.inline_comments,
            checks_passed=llm_result.checks_passed,
            confidence=llm_result.confidence,
            issues=llm_result.issues,
            suggestions=llm_result.suggestions,
        )

        return self.pr_reviewer.post_review(repo, pr_number, full_result)

    def review_from_webhook(
        self,
        repo: str,
        pr_number: int,
        action: str,
    ) -> Optional[WorkflowResult]:
        """Handle PR review triggered by webhook.

        Args:
            repo: Repository in owner/name format.
            pr_number: Pull request number.
            action: Webhook action (opened, synchronize, etc.).

        Returns:
            WorkflowResult if review was performed, None otherwise.
        """
        # Only review on specific actions
        reviewable_actions = {"opened", "synchronize", "reopened"}
        if action not in reviewable_actions:
            logger.debug(f"Skipping review for action: {action}")
            return None

        return self.review_pr(
            repo=repo,
            pr_number=pr_number,
            post_review=True,
            auto_merge=self.config.auto_merge_enabled,
        )

    def close(self) -> None:
        """Clean up resources."""
        if self._pr_reviewer:
            self._pr_reviewer.close()
