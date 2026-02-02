"""Git operations for Minion workspace management."""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class GitResult:
    """Result of a git operation."""

    success: bool
    output: str
    error: str = ""
    return_code: int = 0


class GitOps:
    """Handles git operations in the Minion workspace."""

    def __init__(self, workspace: Path, repo_name: str):
        """Initialize git operations.

        Args:
            workspace: Path to workspace directory.
            repo_name: Repository name (owner/repo format).
        """
        self.workspace = workspace
        self.repo_name = repo_name
        self.repo_path = workspace / repo_name.split("/")[-1]

    def _run_git(
        self,
        args: List[str],
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
    ) -> GitResult:
        """Run a git command.

        Args:
            args: Git command arguments.
            cwd: Working directory (default: repo_path).
            env: Environment variables.

        Returns:
            GitResult with output and status.
        """
        cmd = ["git"] + args
        work_dir = cwd or self.repo_path

        # Merge environment
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        logger.debug(f"Running: git {' '.join(args)} in {work_dir}")

        try:
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=120,
                env=run_env,
            )

            return GitResult(
                success=result.returncode == 0,
                output=result.stdout.strip(),
                error=result.stderr.strip(),
                return_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return GitResult(
                success=False,
                output="",
                error="Git command timed out",
                return_code=-1,
            )
        except Exception as e:
            return GitResult(
                success=False,
                output="",
                error=str(e),
                return_code=-1,
            )

    def clone(self, clone_url: str) -> GitResult:
        """Clone a repository.

        Args:
            clone_url: URL to clone from (with embedded token).

        Returns:
            GitResult indicating success/failure.
        """
        logger.info(f"Cloning {self.repo_name} to {self.workspace}")

        # Clone to workspace directory
        result = self._run_git(
            ["clone", "--depth", "100", clone_url, str(self.repo_path)],
            cwd=self.workspace,
        )

        if result.success:
            logger.info(f"Cloned successfully to {self.repo_path}")
        else:
            logger.error(f"Clone failed: {result.error}")

        return result

    def create_branch(self, branch_name: str) -> GitResult:
        """Create and checkout a new branch.

        Args:
            branch_name: Name for the new branch.

        Returns:
            GitResult indicating success/failure.
        """
        logger.info(f"Creating branch: {branch_name}")
        return self._run_git(["checkout", "-b", branch_name])

    def checkout(self, branch_name: str) -> GitResult:
        """Checkout an existing branch.

        Args:
            branch_name: Branch to checkout.

        Returns:
            GitResult indicating success/failure.
        """
        return self._run_git(["checkout", branch_name])

    def get_current_branch(self) -> str:
        """Get the current branch name.

        Returns:
            Current branch name or empty string on error.
        """
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.output if result.success else ""

    def stage_all(self) -> GitResult:
        """Stage all changes.

        Returns:
            GitResult indicating success/failure.
        """
        return self._run_git(["add", "-A"])

    def stage_files(self, files: List[str]) -> GitResult:
        """Stage specific files.

        Args:
            files: List of file paths to stage.

        Returns:
            GitResult indicating success/failure.
        """
        return self._run_git(["add"] + files)

    def commit(self, message: str, author: Optional[str] = None) -> GitResult:
        """Create a commit.

        Args:
            message: Commit message.
            author: Optional author string (Name <email>).

        Returns:
            GitResult indicating success/failure.
        """
        args = ["commit", "-m", message]
        if author:
            args.extend(["--author", author])

        logger.info(f"Committing: {message[:50]}...")
        return self._run_git(args)

    def push(self, remote: str = "origin", branch: Optional[str] = None) -> GitResult:
        """Push to remote.

        Args:
            remote: Remote name (default: origin).
            branch: Branch to push (default: current branch).

        Returns:
            GitResult indicating success/failure.
        """
        branch = branch or self.get_current_branch()
        logger.info(f"Pushing {branch} to {remote}")
        return self._run_git(["push", "-u", remote, branch])

    def pull(self, remote: str = "origin", branch: str = "main") -> GitResult:
        """Pull from remote.

        Args:
            remote: Remote name.
            branch: Branch to pull.

        Returns:
            GitResult indicating success/failure.
        """
        return self._run_git(["pull", remote, branch])

    def rebase(self, branch: str = "main") -> GitResult:
        """Rebase current branch onto another.

        Args:
            branch: Branch to rebase onto.

        Returns:
            GitResult indicating success/failure.
        """
        logger.info(f"Rebasing onto {branch}")
        return self._run_git(["rebase", branch])

    def abort_rebase(self) -> GitResult:
        """Abort an in-progress rebase.

        Returns:
            GitResult indicating success/failure.
        """
        return self._run_git(["rebase", "--abort"])

    def fetch(self, remote: str = "origin") -> GitResult:
        """Fetch from remote.

        Args:
            remote: Remote name.

        Returns:
            GitResult indicating success/failure.
        """
        return self._run_git(["fetch", remote])

    def push_with_retry(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        base_branch: str = "main",
        max_retries: int = 2,
    ) -> Tuple[GitResult, bool]:
        """Push with automatic rebase retry on rejection.

        Args:
            remote: Remote name.
            branch: Branch to push.
            base_branch: Branch to rebase onto if needed.
            max_retries: Maximum retry attempts.

        Returns:
            Tuple of (GitResult, rebased: bool).
        """
        branch = branch or self.get_current_branch()
        rebased = False

        for attempt in range(max_retries + 1):
            result = self.push(remote, branch)

            if result.success:
                return result, rebased

            # Check if rejection due to non-fast-forward
            if "rejected" in result.error or "non-fast-forward" in result.error:
                logger.warning(
                    f"Push rejected, attempting rebase (attempt {attempt + 1})"
                )

                # Fetch latest
                self.fetch(remote)

                # Try to rebase
                rebase_result = self.rebase(f"{remote}/{base_branch}")
                if not rebase_result.success:
                    self.abort_rebase()
                    logger.error("Rebase failed, aborting")
                    return result, False

                rebased = True
            else:
                # Some other error, don't retry
                return result, rebased

        return result, rebased

    def get_diff_stats(self) -> Optional[str]:
        """Get summary of changes.

        Returns:
            Diff stats string or None on error.
        """
        result = self._run_git(["diff", "--stat", "HEAD~1"])
        return result.output if result.success else None

    def get_changed_files(self) -> List[str]:
        """Get list of changed files.

        Returns:
            List of changed file paths.
        """
        result = self._run_git(["diff", "--name-only", "HEAD~1"])
        if result.success and result.output:
            return result.output.split("\n")
        return []

    def configure_user(self, name: str, email: str) -> None:
        """Configure git user for commits.

        Args:
            name: User name.
            email: User email.
        """
        self._run_git(["config", "user.name", name])
        self._run_git(["config", "user.email", email])
        logger.debug(f"Configured git user: {name} <{email}>")
