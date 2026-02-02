"""Minion main entry point - orchestrates the full lifecycle."""

import asyncio
import logging
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from nebulus_swarm.minion.github_client import GitHubClient, IssueDetails
from nebulus_swarm.minion.git_ops import GitOps
from nebulus_swarm.minion.reporter import Reporter

logger = logging.getLogger(__name__)

# Constants
WORKSPACE = Path("/workspace")
MAX_ISSUE_COMPLEXITY = 20  # Max estimated steps before bailing


@dataclass
class MinionConfig:
    """Configuration loaded from environment variables."""

    minion_id: str
    repo: str
    issue_number: int
    github_token: str
    overlord_callback_url: str
    nebulus_base_url: str
    nebulus_model: str
    nebulus_timeout: int
    nebulus_streaming: bool
    minion_timeout: int

    @classmethod
    def from_env(cls) -> "MinionConfig":
        """Load configuration from environment variables."""
        return cls(
            minion_id=os.environ.get("MINION_ID", "minion-unknown"),
            repo=os.environ.get("GITHUB_REPO", ""),
            issue_number=int(os.environ.get("GITHUB_ISSUE", "0")),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            overlord_callback_url=os.environ.get(
                "OVERLORD_CALLBACK_URL", "http://overlord:8080/minion/report"
            ),
            nebulus_base_url=os.environ.get(
                "NEBULUS_BASE_URL", "http://localhost:5000/v1"
            ),
            nebulus_model=os.environ.get("NEBULUS_MODEL", "qwen3-coder-30b"),
            nebulus_timeout=int(os.environ.get("NEBULUS_TIMEOUT", "600")),
            nebulus_streaming=os.environ.get("NEBULUS_STREAMING", "false").lower()
            == "true",
            minion_timeout=int(os.environ.get("MINION_TIMEOUT", "1800")),
        )

    def validate(self) -> list[str]:
        """Validate required configuration."""
        errors = []
        if not self.repo:
            errors.append("GITHUB_REPO is required")
        if not self.issue_number:
            errors.append("GITHUB_ISSUE is required")
        if not self.github_token:
            errors.append("GITHUB_TOKEN is required")
        return errors


class Minion:
    """Orchestrates the full Minion lifecycle."""

    def __init__(self, config: MinionConfig):
        """Initialize Minion with configuration.

        Args:
            config: Minion configuration.
        """
        self.config = config
        self._shutdown_requested = False

        # Initialize components
        self.github = GitHubClient(config.github_token)
        self.reporter = Reporter(
            minion_id=config.minion_id,
            issue_number=config.issue_number,
            callback_url=config.overlord_callback_url,
        )
        self.git: Optional[GitOps] = None
        self.issue: Optional[IssueDetails] = None

    def _signal_handler(self, sig: signal.Signals, frame) -> None:
        """Handle shutdown signals."""
        logger.warning(f"Received signal {sig}, requesting shutdown...")
        self._shutdown_requested = True

    async def run(self) -> int:
        """Run the full Minion lifecycle.

        Returns:
            Exit code (0 for success, non-zero for failure).
        """
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Set up timeout
        try:
            return await asyncio.wait_for(
                self._run_lifecycle(),
                timeout=self.config.minion_timeout,
            )
        except asyncio.TimeoutError:
            logger.error(f"Minion timed out after {self.config.minion_timeout}s")
            await self.reporter.error(
                "Minion timed out",
                error_type="timeout",
                details=f"Exceeded {self.config.minion_timeout}s limit",
            )
            return 1

    async def _run_lifecycle(self) -> int:
        """Execute the Minion lifecycle steps.

        Returns:
            Exit code.
        """
        try:
            # Start heartbeat reporting
            await self.reporter.start()

            # Step 1: Fetch issue details
            await self.reporter.progress("Fetching issue details")
            self.issue = self.github.get_issue(
                self.config.repo, self.config.issue_number
            )
            logger.info(f"Issue #{self.issue.number}: {self.issue.title}")

            if self._shutdown_requested:
                return 130

            # Step 2: Clone repository
            await self.reporter.progress("Cloning repository")
            clone_url = self.github.get_clone_url(self.config.repo)
            self.git = GitOps(WORKSPACE, self.config.repo)

            result = self.git.clone(clone_url)
            if not result.success:
                await self.reporter.error(
                    "Failed to clone repository",
                    error_type="git_error",
                    details=result.error,
                )
                return 1

            # Configure git user
            self.git.configure_user(
                f"Minion {self.config.minion_id}",
                "minion@nebulus.local",
            )

            if self._shutdown_requested:
                return 130

            # Step 3: Create branch
            branch_name = f"minion/issue-{self.config.issue_number}"
            await self.reporter.progress(f"Creating branch: {branch_name}")

            result = self.git.create_branch(branch_name)
            if not result.success:
                await self.reporter.error(
                    "Failed to create branch",
                    error_type="git_error",
                    details=result.error,
                )
                return 1

            if self._shutdown_requested:
                return 130

            # Step 4: Work on the issue
            await self.reporter.progress("Working on issue")
            work_result = await self._do_work()

            if not work_result:
                # Error already reported in _do_work
                return 1

            if self._shutdown_requested:
                return 130

            # Step 5: Commit changes
            await self.reporter.progress("Committing changes")
            self.git.stage_all()

            commit_message = self._generate_commit_message()
            result = self.git.commit(commit_message)

            if not result.success:
                if "nothing to commit" in result.error.lower():
                    await self.reporter.error(
                        "No changes to commit",
                        error_type="no_changes",
                        details="Work completed but no files were modified",
                    )
                else:
                    await self.reporter.error(
                        "Failed to commit",
                        error_type="git_error",
                        details=result.error,
                    )
                return 1

            if self._shutdown_requested:
                return 130

            # Step 6: Push branch
            await self.reporter.progress("Pushing branch")
            default_branch = self.github.get_default_branch(self.config.repo)
            result, rebased = self.git.push_with_retry(
                base_branch=default_branch,
            )

            if not result.success:
                await self.reporter.error(
                    "Failed to push branch",
                    error_type="git_error",
                    details=result.error,
                )
                return 1

            if rebased:
                logger.info("Branch was rebased before push")

            if self._shutdown_requested:
                return 130

            # Step 7: Create pull request
            await self.reporter.progress("Creating pull request")
            pr = await self._create_pull_request(branch_name, default_branch)

            if not pr:
                # Error already reported
                return 1

            # Step 8: Report completion
            await self.reporter.complete(
                message=f"Created PR #{pr.number}",
                pr_number=pr.number,
                pr_url=pr.html_url,
                branch=branch_name,
            )

            logger.info(f"Minion completed successfully: {pr.html_url}")
            return 0

        except Exception as e:
            logger.exception(f"Minion failed with exception: {e}")
            await self.reporter.error(
                f"Unexpected error: {e}",
                error_type="exception",
                details=str(e),
            )
            return 1

        finally:
            # Clean up
            await self.reporter.stop()
            self.github.close()

    async def _do_work(self) -> bool:
        """Execute the actual work on the issue.

        This is where the LLM agent does its magic.

        Returns:
            True if work completed successfully.
        """
        # TODO: Integrate with Nebulus Atom agent
        # For now, this is a stub that creates a simple placeholder file

        logger.info("Starting work on issue...")
        self.reporter.update_status("analyzing issue")

        # Create the issue prompt
        issue_prompt = self.issue.to_prompt()
        logger.debug(f"Issue prompt:\n{issue_prompt}")

        # STUB: In full implementation, this would:
        # 1. Initialize the Nebulus Atom agent with the issue context
        # 2. Let the agent analyze and implement the solution
        # 3. Agent would use tools to read/write files, run tests, etc.
        # 4. Return when agent signals completion

        # For MVP testing, create a simple placeholder
        workspace_path = self.git.repo_path

        # Create a placeholder file to demonstrate the workflow
        stub_file = workspace_path / "minion_work.md"
        stub_content = f"""# Minion Work Log

## Issue #{self.issue.number}: {self.issue.title}

**Status:** Work in progress (stub implementation)

**Minion:** {self.config.minion_id}

## Issue Description

{self.issue.body or "(No description)"}

## Work Notes

This file was created by the Minion as a placeholder.
Full LLM agent integration is pending.

---
*Generated by Nebulus Swarm Minion*
"""
        stub_file.write_text(stub_content)
        logger.info(f"Created stub work file: {stub_file}")

        self.reporter.update_status("work completed")
        return True

    def _generate_commit_message(self) -> str:
        """Generate a commit message for the work.

        Returns:
            Formatted commit message.
        """
        title = f"feat: implement #{self.config.issue_number}"
        if self.issue:
            # Truncate title if too long
            issue_title = self.issue.title[:50]
            if len(self.issue.title) > 50:
                issue_title += "..."
            title = f"feat: {issue_title}"

        body = f"""Implements #{self.config.issue_number}

Automated implementation by Nebulus Swarm Minion.

Minion-ID: {self.config.minion_id}
Co-Authored-By: Nebulus Minion <minion@nebulus.local>
"""
        return f"{title}\n\n{body}"

    async def _create_pull_request(
        self, branch_name: str, base_branch: str
    ) -> Optional[object]:
        """Create a pull request for the work.

        Args:
            branch_name: Head branch with changes.
            base_branch: Target branch.

        Returns:
            PRDetails or None on failure.
        """
        pr_title = f"[Minion] Implement #{self.config.issue_number}"
        if self.issue:
            pr_title = f"[Minion] {self.issue.title}"

        pr_body = f"""## Summary

Automated implementation for #{self.config.issue_number}.

## Changes

{self._get_changes_summary()}

## Testing

- [ ] Tests pass locally
- [ ] Manual review completed

---

*This PR was created automatically by Nebulus Swarm Minion `{self.config.minion_id}`*

Closes #{self.config.issue_number}
"""

        try:
            pr = self.github.create_pull_request(
                repo_name=self.config.repo,
                title=pr_title,
                body=pr_body,
                head_branch=branch_name,
                base_branch=base_branch,
                draft=False,  # Could make draft if tests fail
            )
            return pr
        except Exception as e:
            await self.reporter.error(
                "Failed to create PR",
                error_type="github_error",
                details=str(e),
            )
            return None

    def _get_changes_summary(self) -> str:
        """Get a summary of changes for PR body.

        Returns:
            Markdown-formatted changes summary.
        """
        if not self.git:
            return "(Changes not available)"

        changed_files = self.git.get_changed_files()
        if not changed_files:
            return "(No files changed)"

        lines = [f"- `{f}`" for f in changed_files[:10]]
        if len(changed_files) > 10:
            lines.append(f"- ... and {len(changed_files) - 10} more files")

        return "\n".join(lines)


async def main() -> int:
    """Main entry point."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Minion starting...")

    # Load configuration
    config = MinionConfig.from_env()

    # Validate
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Config error: {error}")
        return 1

    logger.info(
        f"Minion {config.minion_id} working on {config.repo}#{config.issue_number}"
    )

    # Run minion
    minion = Minion(config)
    return await minion.run()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
