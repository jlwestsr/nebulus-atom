"""PR Reviewer service for examining Minion-created pull requests."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from github import Auth, Github
from github.GithubException import GithubException

logger = logging.getLogger(__name__)


class ReviewDecision(Enum):
    """Review decision types."""

    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


@dataclass
class FileChange:
    """A changed file in a PR."""

    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    patch: Optional[str] = None  # The diff patch

    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions


@dataclass
class PRDetails:
    """Details about a pull request for review."""

    repo: str
    number: int
    title: str
    body: str
    author: str
    base_branch: str
    head_branch: str
    created_at: datetime
    files: List[FileChange] = field(default_factory=list)
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    linked_issue: Optional[int] = None

    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions

    def get_diff_summary(self) -> str:
        """Get a summary of changes for LLM context."""
        lines = [
            f"# PR #{self.number}: {self.title}",
            "",
            f"**Author:** {self.author}",
            f"**Branch:** {self.head_branch} → {self.base_branch}",
            f"**Changes:** +{self.additions} -{self.deletions} across {len(self.files)} files",
            "",
        ]

        if self.body:
            lines.extend(["## Description", f"{self.body}", ""])

        lines.append("## Changed Files")
        for f in self.files:
            lines.append(
                f"- `{f.filename}` ({f.status}): +{f.additions} -{f.deletions}"
            )

        return "\n".join(lines)

    def get_full_diff(self, max_lines: int = 500) -> str:
        """Get the full diff content, truncated if too large."""
        lines = []
        total_lines = 0

        for f in self.files:
            if f.patch:
                patch_lines = f.patch.split("\n")
                if total_lines + len(patch_lines) > max_lines:
                    remaining = max_lines - total_lines
                    if remaining > 10:
                        lines.append(f"\n### {f.filename}\n```diff")
                        lines.extend(patch_lines[:remaining])
                        lines.append("```")
                        lines.append(
                            f"... (truncated, {len(patch_lines) - remaining} more lines)"
                        )
                    break
                else:
                    lines.append(f"\n### {f.filename}\n```diff")
                    lines.extend(patch_lines)
                    lines.append("```")
                    total_lines += len(patch_lines)

        if total_lines >= max_lines:
            lines.append(f"\n*Diff truncated at {max_lines} lines*")

        return "\n".join(lines)


@dataclass
class InlineComment:
    """An inline comment on a specific line of code."""

    path: str
    line: int
    body: str
    side: str = "RIGHT"  # LEFT for deletions, RIGHT for additions


@dataclass
class ReviewResult:
    """Result of a PR review."""

    decision: ReviewDecision
    summary: str
    inline_comments: List[InlineComment] = field(default_factory=list)
    checks_passed: bool = True
    confidence: float = 0.0  # 0.0 to 1.0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    @property
    def can_auto_merge(self) -> bool:
        """Check if PR is safe for auto-merge."""
        return (
            self.decision == ReviewDecision.APPROVE
            and self.checks_passed
            and self.confidence >= 0.8
            and len(self.issues) == 0
        )


class PRReviewer:
    """Service for reviewing pull requests."""

    def __init__(self, token: str):
        """Initialize PR reviewer.

        Args:
            token: GitHub personal access token.
        """
        self.token = token
        auth = Auth.Token(token)
        self._client = Github(auth=auth)

    def get_pr_details(self, repo_name: str, pr_number: int) -> PRDetails:
        """Fetch details about a pull request.

        Args:
            repo_name: Repository in owner/name format.
            pr_number: Pull request number.

        Returns:
            PRDetails with full PR information.

        Raises:
            GithubException: If PR cannot be fetched.
        """
        logger.info(f"Fetching PR details for {repo_name}#{pr_number}")

        repo = self._client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        # Get file changes
        files = []
        for f in pr.get_files():
            files.append(
                FileChange(
                    filename=f.filename,
                    status=f.status,
                    additions=f.additions,
                    deletions=f.deletions,
                    patch=f.patch,
                )
            )

        # Try to find linked issue from PR body
        linked_issue = self._extract_linked_issue(pr.body or "")

        return PRDetails(
            repo=repo_name,
            number=pr_number,
            title=pr.title,
            body=pr.body or "",
            author=pr.user.login,
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            created_at=pr.created_at,
            files=files,
            commits=pr.commits,
            additions=pr.additions,
            deletions=pr.deletions,
            linked_issue=linked_issue,
        )

    def _extract_linked_issue(self, body: str) -> Optional[int]:
        """Extract linked issue number from PR body.

        Looks for patterns like:
        - Closes #123
        - Fixes #123
        - Resolves #123
        """
        import re

        patterns = [
            r"(?:closes?|fixes?|resolves?)\s+#(\d+)",
            r"#(\d+)",  # Fallback: any issue reference
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return None

    def get_pr_checks_status(self, repo_name: str, pr_number: int) -> Dict[str, str]:
        """Get status of CI checks on a PR.

        Args:
            repo_name: Repository in owner/name format.
            pr_number: Pull request number.

        Returns:
            Dict mapping check name to status (success, failure, pending).
        """
        repo = self._client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        # Get the latest commit
        commits = list(pr.get_commits())
        if not commits:
            return {}

        latest_commit = commits[-1]
        statuses = {}

        # Get combined status
        combined = latest_commit.get_combined_status()
        for status in combined.statuses:
            statuses[status.context] = status.state

        # Also check check runs (GitHub Actions)
        try:
            check_runs = latest_commit.get_check_runs()
            for run in check_runs:
                if run.conclusion:
                    statuses[run.name] = run.conclusion
                else:
                    statuses[run.name] = "pending"
        except GithubException:
            pass  # Check runs API might not be available

        return statuses

    def post_review(
        self,
        repo_name: str,
        pr_number: int,
        result: ReviewResult,
    ) -> bool:
        """Post a review to a pull request.

        Args:
            repo_name: Repository in owner/name format.
            pr_number: Pull request number.
            result: Review result to post.

        Returns:
            True if review was posted successfully.
        """
        try:
            repo = self._client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)

            # Build review body
            body_parts = [f"## AI Review Summary\n\n{result.summary}"]

            if result.issues:
                body_parts.append("\n### Issues Found")
                for issue in result.issues:
                    body_parts.append(f"- {issue}")

            if result.suggestions:
                body_parts.append("\n### Suggestions")
                for suggestion in result.suggestions:
                    body_parts.append(f"- {suggestion}")

            body_parts.append(
                f"\n---\n*Confidence: {result.confidence:.0%} | "
                f"Auto-merge eligible: {'Yes' if result.can_auto_merge else 'No'}*"
            )

            body = "\n".join(body_parts)

            # Create the review
            # Note: GitHub API requires comments to be on valid diff positions
            # For simplicity, we'll add inline comments as part of the body for now
            if result.inline_comments:
                body += "\n\n### Inline Comments\n"
                for comment in result.inline_comments:
                    body += f"\n**{comment.path}:{comment.line}**\n{comment.body}\n"

            pr.create_review(
                body=body,
                event=result.decision.value,
            )

            logger.info(
                f"Posted {result.decision.value} review to {repo_name}#{pr_number}"
            )
            return True

        except GithubException as e:
            logger.error(f"Failed to post review to {repo_name}#{pr_number}: {e}")
            return False

    def merge_pr(
        self,
        repo_name: str,
        pr_number: int,
        merge_method: str = "squash",
    ) -> bool:
        """Merge a pull request.

        Args:
            repo_name: Repository in owner/name format.
            pr_number: Pull request number.
            merge_method: Merge method (merge, squash, rebase).

        Returns:
            True if merge was successful.
        """
        try:
            repo = self._client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)

            if not pr.mergeable:
                logger.warning(f"PR {repo_name}#{pr_number} is not mergeable")
                return False

            pr.merge(merge_method=merge_method)
            logger.info(f"Merged PR {repo_name}#{pr_number} using {merge_method}")
            return True

        except GithubException as e:
            logger.error(f"Failed to merge {repo_name}#{pr_number}: {e}")
            return False

    def close(self) -> None:
        """Close the GitHub client."""
        self._client.close()
