"""GitHub issue queue scanner for Overlord."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from github import Auth, Github
from github.GithubException import GithubException, RateLimitExceededException

logger = logging.getLogger(__name__)

# Rate limit safety margin (don't operate if below this)
RATE_LIMIT_THRESHOLD = 100
# Minimum requests needed for a queue sweep
REQUESTS_PER_SWEEP = 10


@dataclass
class QueuedIssue:
    """An issue ready for work."""

    repo: str
    number: int
    title: str
    labels: List[str]
    created_at: datetime
    priority: int = 0  # Higher = more urgent
    body: str = ""

    def __str__(self) -> str:
        return f"{self.repo}#{self.number}: {self.title}"


class GitHubQueue:
    """Scans GitHub repositories for issues ready to work on."""

    def __init__(
        self,
        token: str,
        watched_repos: List[str],
        work_label: str = "nebulus-ready",
        in_progress_label: str = "in-progress",
        high_priority_label: str = "high-priority",
    ):
        """Initialize GitHub queue scanner.

        Args:
            token: GitHub personal access token.
            watched_repos: List of repos to watch (owner/name format).
            work_label: Label indicating issue is ready for work.
            in_progress_label: Label for issues being worked on.
            high_priority_label: Label for high-priority issues.
        """
        self.token = token
        self.watched_repos = watched_repos
        self.work_label = work_label
        self.in_progress_label = in_progress_label
        self.high_priority_label = high_priority_label

        auth = Auth.Token(token)
        self._client = Github(auth=auth)

    def scan_queue(self) -> List[QueuedIssue]:
        """Scan all watched repos for issues ready to work on.

        Returns:
            List of QueuedIssue objects, sorted by priority then date.
        """
        all_issues: List[QueuedIssue] = []

        for repo_name in self.watched_repos:
            try:
                issues = self._scan_repo(repo_name)
                all_issues.extend(issues)
            except RateLimitExceededException:
                logger.warning("GitHub rate limit exceeded, stopping scan")
                break
            except GithubException as e:
                logger.error(f"Error scanning {repo_name}: {e}")
                continue

        # Sort by priority (descending) then by created date (ascending)
        all_issues.sort(key=lambda i: (-i.priority, i.created_at))

        return all_issues

    def _scan_repo(self, repo_name: str) -> List[QueuedIssue]:
        """Scan a single repo for ready issues.

        Args:
            repo_name: Repository in owner/name format.

        Returns:
            List of QueuedIssue objects from this repo.
        """
        logger.debug(f"Scanning {repo_name} for {self.work_label} issues")

        try:
            repo = self._client.get_repo(repo_name)

            # Get issues with the work label that aren't in progress
            issues = repo.get_issues(
                state="open",
                labels=[self.work_label],
            )

            queued = []
            for issue in issues:
                # Skip if already in progress
                label_names = [label.name for label in issue.labels]
                if self.in_progress_label in label_names:
                    continue

                # Skip pull requests (GitHub API returns PRs as issues)
                if issue.pull_request is not None:
                    continue

                # Determine priority
                priority = 1 if self.high_priority_label in label_names else 0

                queued.append(
                    QueuedIssue(
                        repo=repo_name,
                        number=issue.number,
                        title=issue.title,
                        labels=label_names,
                        created_at=issue.created_at,
                        priority=priority,
                        body=issue.body or "",
                    )
                )

            logger.info(f"Found {len(queued)} ready issues in {repo_name}")
            return queued

        except GithubException as e:
            logger.error(f"Failed to scan {repo_name}: {e}")
            raise

    def get_issue_details(self, repo_name: str, issue_number: int) -> Optional[dict]:
        """Fetch basic issue details for routing decisions.

        Args:
            repo_name: Repository in owner/name format.
            issue_number: Issue number.

        Returns:
            Dict with title, body, and labels, or None on error.
        """
        try:
            repo = self._client.get_repo(repo_name)
            issue = repo.get_issue(issue_number)
            return {
                "title": issue.title,
                "body": issue.body or "",
                "labels": [label.name for label in issue.labels],
            }
        except GithubException as e:
            logger.error(f"Failed to fetch {repo_name}#{issue_number}: {e}")
            return None

    def get_next_issue(self) -> Optional[QueuedIssue]:
        """Get the next highest-priority issue to work on.

        Returns:
            QueuedIssue or None if queue is empty.
        """
        queue = self.scan_queue()
        return queue[0] if queue else None

    def mark_in_progress(self, repo_name: str, issue_number: int) -> bool:
        """Mark an issue as in-progress.

        Args:
            repo_name: Repository in owner/name format.
            issue_number: Issue number.

        Returns:
            True if successful.
        """
        try:
            repo = self._client.get_repo(repo_name)
            issue = repo.get_issue(issue_number)

            # Add in-progress label
            issue.add_to_labels(self.in_progress_label)

            # Remove ready label
            try:
                issue.remove_from_labels(self.work_label)
            except GithubException:
                pass  # Label might not be present

            logger.info(f"Marked {repo_name}#{issue_number} as in-progress")
            return True

        except GithubException as e:
            logger.error(f"Failed to mark {repo_name}#{issue_number} in-progress: {e}")
            return False

    def mark_in_review(self, repo_name: str, issue_number: int, pr_number: int) -> bool:
        """Mark an issue as in-review (PR created).

        Args:
            repo_name: Repository in owner/name format.
            issue_number: Issue number.
            pr_number: Associated PR number.

        Returns:
            True if successful.
        """
        try:
            repo = self._client.get_repo(repo_name)
            issue = repo.get_issue(issue_number)

            # Remove in-progress label
            try:
                issue.remove_from_labels(self.in_progress_label)
            except GithubException:
                pass

            # Add in-review label
            try:
                issue.add_to_labels("in-review")
            except GithubException:
                # Label might not exist
                logger.warning(
                    f"Could not add 'in-review' label to {repo_name}#{issue_number}"
                )

            # Add comment linking to PR
            issue.create_comment(
                f"🤖 Minion created PR #{pr_number} to address this issue.\n\n"
                f"Please review the changes."
            )

            logger.info(
                f"Marked {repo_name}#{issue_number} as in-review (PR #{pr_number})"
            )
            return True

        except GithubException as e:
            logger.error(f"Failed to mark {repo_name}#{issue_number} in-review: {e}")
            return False

    def mark_failed(self, repo_name: str, issue_number: int, error: str) -> bool:
        """Mark an issue as needing attention after failure.

        Args:
            repo_name: Repository in owner/name format.
            issue_number: Issue number.
            error: Error message.

        Returns:
            True if successful.
        """
        try:
            repo = self._client.get_repo(repo_name)
            issue = repo.get_issue(issue_number)

            # Remove in-progress label
            try:
                issue.remove_from_labels(self.in_progress_label)
            except GithubException:
                pass

            # Add needs-attention label
            try:
                issue.add_to_labels("needs-attention")
            except GithubException:
                logger.warning(
                    f"Could not add 'needs-attention' label to {repo_name}#{issue_number}"
                )

            # Re-add ready label so it can be retried
            try:
                issue.add_to_labels(self.work_label)
            except GithubException:
                pass

            # Add comment explaining failure
            issue.create_comment(
                f"🤖 Minion failed to complete this issue.\n\n"
                f"**Error:** {error}\n\n"
                f"The issue has been re-added to the queue. "
                f"Please check if the issue description needs clarification."
            )

            logger.info(f"Marked {repo_name}#{issue_number} as needs-attention")
            return True

        except GithubException as e:
            logger.error(f"Failed to mark {repo_name}#{issue_number} as failed: {e}")
            return False

    def get_rate_limit(self) -> dict:
        """Get current GitHub API rate limit status.

        Returns:
            Dict with rate limit information.
        """
        rate = self._client.get_rate_limit()
        reset_at = rate.core.reset
        seconds_until_reset = max(
            0, (reset_at - datetime.now(timezone.utc)).total_seconds()
        )

        return {
            "remaining": rate.core.remaining,
            "limit": rate.core.limit,
            "reset_at": reset_at.isoformat(),
            "seconds_until_reset": int(seconds_until_reset),
            "is_rate_limited": rate.core.remaining < RATE_LIMIT_THRESHOLD,
        }

    def is_rate_limited(self) -> bool:
        """Check if we're currently rate limited.

        Returns:
            True if remaining requests are below threshold.
        """
        try:
            rate = self._client.get_rate_limit()
            if rate.core.remaining < RATE_LIMIT_THRESHOLD:
                logger.warning(
                    f"GitHub API rate limited: {rate.core.remaining} remaining, "
                    f"resets at {rate.core.reset.isoformat()}"
                )
                return True
            return False
        except GithubException as e:
            logger.error(f"Failed to check rate limit: {e}")
            return True  # Assume rate limited on error

    def can_perform_sweep(self) -> bool:
        """Check if we have enough quota for a queue sweep.

        Returns:
            True if we have enough requests remaining.
        """
        try:
            rate = self._client.get_rate_limit()
            # Need at least threshold + requests per sweep
            needed = RATE_LIMIT_THRESHOLD + REQUESTS_PER_SWEEP * len(self.watched_repos)
            if rate.core.remaining < needed:
                logger.info(
                    f"Insufficient quota for sweep: {rate.core.remaining} < {needed}"
                )
                return False
            return True
        except GithubException as e:
            logger.error(f"Failed to check quota: {e}")
            return False

    def wait_for_rate_limit(self, max_wait: int = 300) -> bool:
        """Wait for rate limit to reset if currently limited.

        Args:
            max_wait: Maximum seconds to wait.

        Returns:
            True if rate limit reset (or not limited), False if max_wait exceeded.
        """
        try:
            rate = self._client.get_rate_limit()
            if rate.core.remaining >= RATE_LIMIT_THRESHOLD:
                return True

            reset_at = rate.core.reset
            wait_seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()

            if wait_seconds <= 0:
                return True

            if wait_seconds > max_wait:
                logger.warning(
                    f"Rate limit reset in {wait_seconds:.0f}s, exceeds max wait of {max_wait}s"
                )
                return False

            logger.info(f"Waiting {wait_seconds:.0f}s for rate limit reset...")
            time.sleep(wait_seconds + 1)  # Add 1s buffer
            return True

        except GithubException as e:
            logger.error(f"Failed to wait for rate limit: {e}")
            return False

    def close(self) -> None:
        """Close the GitHub client."""
        self._client.close()
