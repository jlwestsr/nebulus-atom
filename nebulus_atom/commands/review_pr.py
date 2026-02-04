"""Standalone PR review command for developer use."""

import os
import re
import subprocess
import sys
from typing import Optional

from nebulus_swarm.reviewer.checks import CheckStatus
from nebulus_swarm.reviewer.workflow import ReviewConfig, WorkflowResult


def detect_repo_from_git() -> Optional[str]:
    """Detect the GitHub repo from the current directory's git remote.

    Parses the 'origin' remote URL and extracts owner/repo.
    Supports SSH and HTTPS GitHub URLs.

    Returns:
        Repository in 'owner/repo' format, or None if detection fails.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        url = result.stdout.strip()

        # SSH: git@github.com:owner/repo.git
        ssh_match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
        if ssh_match:
            return ssh_match.group(1)

        # HTTPS: https://github.com/owner/repo.git
        https_match = re.match(r"https://github\.com/(.+?)(?:\.git)?$", url)
        if https_match:
            return https_match.group(1)

        return None

    except Exception:
        return None


def load_review_config() -> ReviewConfig:
    """Load review configuration from environment variables.

    Requires GITHUB_TOKEN. Uses NEBULUS_BASE_URL and NEBULUS_MODEL
    with sensible defaults.

    Returns:
        ReviewConfig populated from environment.

    Raises:
        SystemExit: If GITHUB_TOKEN is not set.
    """
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is required.")
        print("Set it in your .env file or export it in your shell.")
        sys.exit(1)

    return ReviewConfig(
        github_token=github_token,
        llm_base_url=os.environ.get("NEBULUS_BASE_URL", "http://localhost:5000/v1"),
        llm_model=os.environ.get(
            "NEBULUS_MODEL", "Meta-Llama-3.1-8B-Instruct-exl2-8_0"
        ),
        llm_timeout=int(os.environ.get("NEBULUS_TIMEOUT", "120")),
        auto_merge_enabled=False,
        run_local_checks=True,
    )


def format_review_output(result: WorkflowResult) -> str:
    """Format the review result as plain text for terminal display.

    Args:
        result: Complete workflow result.

    Returns:
        Formatted string with review details.
    """
    lines = []

    # Header
    pr = result.pr_details
    lines.append(f"PR #{pr.number}: {pr.title}")
    lines.append(f"Author: {pr.author} | {pr.head_branch} -> {pr.base_branch}")
    lines.append(
        f"Changes: +{pr.additions} -{pr.deletions} across {len(pr.files)} files"
    )
    lines.append("")

    # Error
    if result.error:
        lines.append(f"Error: {result.error}")
        lines.append("")

    # Decision
    llm = result.llm_result
    lines.append(f"Decision: {llm.decision.value}")
    lines.append(f"Confidence: {llm.confidence:.0%}")
    lines.append("")

    # Summary
    lines.append("Summary")
    lines.append(llm.summary)
    lines.append("")

    # Issues
    if llm.issues:
        lines.append("Issues")
        for issue in llm.issues:
            lines.append(f"  - {issue}")
        lines.append("")

    # Suggestions
    if llm.suggestions:
        lines.append("Suggestions")
        for suggestion in llm.suggestions:
            lines.append(f"  - {suggestion}")
        lines.append("")

    # Checks
    if result.checks_report and result.checks_report.results:
        lines.append("Checks")
        status_indicator = {
            CheckStatus.PASSED: "PASS",
            CheckStatus.FAILED: "FAIL",
            CheckStatus.WARNING: "WARN",
            CheckStatus.SKIPPED: "SKIP",
        }
        for check in result.checks_report.results:
            indicator = status_indicator.get(check.status, "????")
            lines.append(f"  [{indicator}] {check.name}: {check.message}")
            for file_issue in check.file_issues[:3]:
                lines.append(f"         {file_issue}")
        lines.append("")

    return "\n".join(lines)


def run_review(
    pr_number: int,
    repo: Optional[str] = None,
    run_checks: bool = True,
) -> WorkflowResult:
    """Execute the review workflow.

    Args:
        pr_number: Pull request number.
        repo: Repository in owner/name format. Auto-detected if None.
        run_checks: Whether to run local checks.

    Returns:
        WorkflowResult with review details.
    """
    from nebulus_swarm.reviewer.workflow import ReviewWorkflow

    if repo is None:
        repo = detect_repo_from_git()
        if repo is None:
            print("Error: Could not detect repository from git remote.")
            print("Use --repo owner/name to specify it explicitly.")
            sys.exit(1)

    config = load_review_config()
    config.run_local_checks = run_checks

    workflow = ReviewWorkflow(config)
    try:
        repo_path = os.getcwd() if run_checks else None
        return workflow.review_pr(
            repo=repo,
            pr_number=pr_number,
            post_review=False,
            auto_merge=False,
            repo_path=repo_path,
        )
    finally:
        workflow.close()
