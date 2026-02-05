"""Minion main entry point - orchestrates the full lifecycle."""

import asyncio
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nebulus_swarm.minion.agent import (
    AgentResult,
    AgentStatus,
    LLMConfig,
    MinionAgent,
    ToolExecutor,
    ToolResult,
    MINION_TOOLS,
)
from nebulus_swarm.minion.agent.prompt_builder import IssueContext, build_system_prompt
from nebulus_swarm.minion.github_client import GitHubClient, IssueDetails
from nebulus_swarm.minion.git_ops import GitOps
from nebulus_swarm.minion.reporter import Reporter
from nebulus_swarm.overlord.scope import ScopeConfig
from nebulus_swarm.reviewer.workflow import ReviewConfig, ReviewWorkflow, WorkflowResult

logger = logging.getLogger(__name__)

# Constants
WORKSPACE = Path("/workspace")
MAX_ISSUE_COMPLEXITY = 20  # Max estimated steps before bailing
MAX_QUESTIONS = 3  # Max clarifying questions per Minion run
QUESTION_TIMEOUT = 600  # 10 minutes to wait for human answer


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
    scope: ScopeConfig = field(default_factory=ScopeConfig.unrestricted)

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
            scope=ScopeConfig.from_json(os.environ.get("MINION_SCOPE", "")),
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

            if self._shutdown_requested:
                return 130

            # Step 8: Review pull request
            await self.reporter.progress("Running automated review")
            review_result = await self._review_pr(pr.number)

            # Build completion message with review summary if available
            completion_message = f"Created PR #{pr.number}"
            review_summary = None
            if review_result and not review_result.error:
                review_summary = review_result.summary
                completion_message = (
                    f"Created PR #{pr.number} | Review: "
                    f"{review_result.llm_result.decision.value} "
                    f"({review_result.llm_result.confidence:.0%} confidence)"
                )

            # Step 9: Report completion
            await self.reporter.complete(
                message=completion_message,
                pr_number=pr.number,
                pr_url=pr.html_url,
                branch=branch_name,
                review_summary=review_summary,
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
        """Execute the actual work on the issue using the MinionAgent.

        Returns:
            True if work completed successfully.
        """
        logger.info("Starting work on issue...")
        self.reporter.update_status("analyzing issue")

        # Build issue context for prompt
        issue_context = IssueContext(
            repo=self.config.repo,
            number=self.issue.number,
            title=self.issue.title,
            body=self.issue.body or "",
            labels=self.issue.labels,
            author=self.issue.author,
        )

        # Build system prompt
        system_prompt = build_system_prompt(issue_context)

        # Configure LLM client
        llm_config = LLMConfig(
            base_url=self.config.nebulus_base_url,
            model=self.config.nebulus_model,
            timeout=self.config.nebulus_timeout,
        )

        # Create tool executor scoped to workspace
        workspace_path = self.git.repo_path
        tool_executor = ToolExecutor(workspace=workspace_path)

        # Create executor wrapper
        def execute_tool(name: str, arguments: dict) -> ToolResult:
            return tool_executor.execute(name, arguments)

        # Create and run the agent
        agent = MinionAgent(
            llm_config=llm_config,
            system_prompt=system_prompt,
            tools=MINION_TOOLS,
            tool_executor=execute_tool,
        )

        self.reporter.update_status("working")
        logger.info("Running MinionAgent...")

        # Question loop: agent runs, may ask questions, gets answers, resumes
        questions_asked = 0

        while True:
            result: AgentResult = agent.run()

            logger.info(f"Agent finished: {result.status.value} - {result.summary}")
            logger.info(f"Turns used: {result.turns_used}")

            if result.status == AgentStatus.COMPLETED:
                self.reporter.update_status("work completed")
                if result.files_changed:
                    logger.info(f"Files changed: {result.files_changed}")
                return True

            elif result.status == AgentStatus.BLOCKED and result.question:
                questions_asked += 1

                if questions_asked > MAX_QUESTIONS:
                    logger.info(
                        f"Max questions ({MAX_QUESTIONS}) reached, "
                        "continuing with best judgment"
                    )
                    agent.inject_message(
                        "No more questions available. "
                        "Use your best judgment to proceed."
                    )
                    continue

                # Send question to Overlord via Reporter
                question_id = f"q-{self.config.minion_id}-{questions_asked}"
                logger.info(
                    f"Agent asked question {questions_asked}/{MAX_QUESTIONS}: "
                    f"{result.question}"
                )
                self.reporter.update_status("waiting for answer")

                sent = await self.reporter.question(
                    result.question,
                    result.blocker_type or "unknown",
                    question_id,
                )

                if not sent:
                    logger.warning(
                        "Failed to send question to Overlord, "
                        "continuing with best judgment"
                    )
                    agent.inject_message(
                        "Could not reach the team for an answer. "
                        "Use your best judgment to proceed."
                    )
                    continue

                # Poll for answer with timeout
                answer = await self.reporter.poll_answer(
                    question_id, timeout=QUESTION_TIMEOUT
                )

                if answer:
                    logger.info(f"Received answer for {question_id}")
                    agent.inject_message(f"Human response: {answer}")
                else:
                    logger.info(
                        f"No answer received for {question_id}, "
                        "continuing with best judgment"
                    )
                    agent.inject_message(
                        "No response received within 10 minutes. "
                        "Use your best judgment to proceed."
                    )

                self.reporter.update_status("working")
                # Loop continues - agent.run() resumes with injected context

            elif result.status == AgentStatus.BLOCKED:
                # Blocked without a question - terminal failure
                await self.reporter.error(
                    result.summary,
                    error_type="blocked",
                    details=f"Blocker type: {result.blocker_type}",
                )
                return False

            elif result.status == AgentStatus.TURN_LIMIT:
                await self.reporter.error(
                    result.summary,
                    error_type="turn_limit",
                    details=f"Used {result.turns_used} turns",
                )
                return False

            else:  # ERROR
                await self.reporter.error(
                    result.summary,
                    error_type="agent_error",
                    details=result.error or "Unknown error",
                )
                return False

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

    async def _review_pr(self, pr_number: int) -> Optional[WorkflowResult]:
        """Run PR review after creation.

        Reviews the PR using the automated review workflow and posts
        results as a comment. Review failures do not block PR creation.

        Args:
            pr_number: The PR number to review.

        Returns:
            WorkflowResult if review succeeded, None on failure.
        """
        logger.info(f"Running automated review for PR #{pr_number}")

        try:
            config = ReviewConfig(
                github_token=self.config.github_token,
                llm_base_url=self.config.nebulus_base_url,
                llm_model=self.config.nebulus_model,
                llm_timeout=self.config.nebulus_timeout,
                auto_merge_enabled=False,  # Never auto-merge
                run_local_checks=True,
            )

            workflow = ReviewWorkflow(config)

            # Run review (synchronous method, run in thread to not block)
            repo_path = str(self.git.repo_path) if self.git else None
            result = await asyncio.to_thread(
                workflow.review_pr,
                self.config.repo,
                pr_number,
                post_review=True,
                auto_merge=False,
                repo_path=repo_path,
            )

            if result.error:
                logger.warning(f"PR review completed with error: {result.error}")
            else:
                logger.info(f"PR review complete: {result.summary}")

            # Clean up
            workflow.close()

            return result

        except Exception as e:
            # Review failures should not block PR creation
            logger.warning(f"PR review failed (non-blocking): {e}")
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
