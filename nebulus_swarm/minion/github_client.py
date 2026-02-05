"""GitHub API client for Minion operations."""

import logging
from dataclasses import dataclass
from typing import List, Optional

from github import Auth, Github
from github.GithubException import GithubException
from github.Repository import Repository

logger = logging.getLogger(__name__)


@dataclass
class IssueDetails:
    """Parsed GitHub issue information."""

    number: int
    title: str
    body: str
    labels: List[str]
    comments: List[str]
    author: str
    state: str

    def to_prompt(self) -> str:
        """Format issue as a prompt for the LLM."""
        lines = [
            f"# Issue #{self.number}: {self.title}",
            "",
            "## Description",
            self.body or "(No description provided)",
            "",
        ]

        if self.comments:
            lines.append("## Comments")
            for i, comment in enumerate(self.comments, 1):
                lines.append(f"### Comment {i}")
                lines.append(comment)
                lines.append("")

        if self.labels:
            lines.append(f"## Labels: {', '.join(self.labels)}")

        return "\n".join(lines)


@dataclass
class PRDetails:
    """Created pull request information."""

    number: int
    url: str
    html_url: str
    title: str
    branch: str


class GitHubClient:
    """Client for GitHub API operations."""

    def __init__(self, token: str):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token or app token.
        """
        self.token = token
        auth = Auth.Token(token)
        self._client = Github(auth=auth)

    def get_repo(self, repo_name: str) -> Repository:
        """Get a repository by name.

        Args:
            repo_name: Repository in 'owner/name' format.

        Returns:
            Repository object.
        """
        return self._client.get_repo(repo_name)

    def get_issue(self, repo_name: str, issue_number: int) -> IssueDetails:
        """Fetch issue details including comments.

        Args:
            repo_name: Repository in 'owner/name' format.
            issue_number: Issue number.

        Returns:
            IssueDetails with all relevant information.
        """
        logger.info(f"Fetching issue {repo_name}#{issue_number}")

        repo = self.get_repo(repo_name)
        issue = repo.get_issue(issue_number)

        # Get comments
        comments = []
        for comment in issue.get_comments():
            comments.append(comment.body)

        return IssueDetails(
            number=issue.number,
            title=issue.title,
            body=issue.body or "",
            labels=[label.name for label in issue.labels],
            comments=comments,
            author=issue.user.login,
            state=issue.state,
        )

    def create_pull_request(
        self,
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        draft: bool = False,
    ) -> PRDetails:
        """Create a pull request.

        Args:
            repo_name: Repository in 'owner/name' format.
            title: PR title.
            body: PR description.
            head_branch: Branch with changes.
            base_branch: Target branch (default: main).
            draft: Whether to create as draft PR.

        Returns:
            PRDetails with created PR information.
        """
        logger.info(f"Creating PR: {head_branch} -> {base_branch}")

        repo = self.get_repo(repo_name)

        try:
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch,
                draft=draft,
            )

            logger.info(f"Created PR #{pr.number}: {pr.html_url}")

            return PRDetails(
                number=pr.number,
                url=pr.url,
                html_url=pr.html_url,
                title=pr.title,
                branch=head_branch,
            )
        except GithubException as e:
            logger.error(f"Failed to create PR: {e}")
            raise

    def update_issue_labels(
        self,
        repo_name: str,
        issue_number: int,
        add_labels: Optional[List[str]] = None,
        remove_labels: Optional[List[str]] = None,
    ) -> None:
        """Update labels on an issue.

        Args:
            repo_name: Repository in 'owner/name' format.
            issue_number: Issue number.
            add_labels: Labels to add.
            remove_labels: Labels to remove.
        """
        repo = self.get_repo(repo_name)
        issue = repo.get_issue(issue_number)

        if add_labels:
            for label in add_labels:
                try:
                    issue.add_to_labels(label)
                    logger.debug(f"Added label '{label}' to #{issue_number}")
                except GithubException:
                    logger.warning(f"Label '{label}' may not exist")

        if remove_labels:
            for label in remove_labels:
                try:
                    issue.remove_from_labels(label)
                    logger.debug(f"Removed label '{label}' from #{issue_number}")
                except GithubException:
                    pass  # Label wasn't present

    def add_issue_comment(self, repo_name: str, issue_number: int, body: str) -> None:
        """Add a comment to an issue.

        Args:
            repo_name: Repository in 'owner/name' format.
            issue_number: Issue number.
            body: Comment text.
        """
        repo = self.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        issue.create_comment(body)
        logger.debug(f"Added comment to #{issue_number}")

    def get_default_branch(self, repo_name: str) -> str:
        """Get the default branch name for a repository.

        Args:
            repo_name: Repository in 'owner/name' format.

        Returns:
            Default branch name (e.g., 'main' or 'master').
        """
        repo = self.get_repo(repo_name)
        return repo.default_branch

    def get_clone_url(self, repo_name: str) -> str:
        """Get the HTTPS clone URL for a repository.

        Args:
            repo_name: Repository in 'owner/name' format.

        Returns:
            Clone URL with token embedded.
        """
        repo = self.get_repo(repo_name)
        # Embed token in URL for authenticated clone
        return repo.clone_url.replace(
            "https://", f"https://x-access-token:{self.token}@"
        )

    def close(self) -> None:
        """Close the GitHub client connection."""
        self._client.close()
