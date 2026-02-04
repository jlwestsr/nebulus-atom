"""Tests for the review-pr CLI command."""

import subprocess
from unittest.mock import patch

import pytest

pytest.importorskip("openai")

from nebulus_atom.commands.review_pr import (
    detect_repo_from_git,
    load_review_config,
    format_review_output,
)
from nebulus_swarm.reviewer.checks import CheckResult, ChecksReport, CheckStatus
from nebulus_swarm.reviewer.pr_reviewer import (
    FileChange,
    PRDetails,
    ReviewDecision,
    ReviewResult,
)
from nebulus_swarm.reviewer.workflow import WorkflowResult


# ---------------------------------------------------------------------------
# detect_repo_from_git
# ---------------------------------------------------------------------------


class TestDetectRepoFromGit:
    def test_detects_ssh_remote(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="git@github.com:owner/repo.git\n", stderr=""
        )
        with patch("subprocess.run", return_value=completed):
            assert detect_repo_from_git() == "owner/repo"

    def test_detects_https_remote(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://github.com/owner/repo.git\n",
            stderr="",
        )
        with patch("subprocess.run", return_value=completed):
            assert detect_repo_from_git() == "owner/repo"

    def test_detects_https_without_dotgit(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://github.com/owner/repo\n",
            stderr="",
        )
        with patch("subprocess.run", return_value=completed):
            assert detect_repo_from_git() == "owner/repo"

    def test_returns_none_on_failure(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="not a git repo"
        )
        with patch("subprocess.run", return_value=completed):
            assert detect_repo_from_git() is None

    def test_returns_none_on_non_github(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://gitlab.com/owner/repo.git\n",
            stderr="",
        )
        with patch("subprocess.run", return_value=completed):
            assert detect_repo_from_git() is None


# ---------------------------------------------------------------------------
# load_review_config
# ---------------------------------------------------------------------------


class TestLoadReviewConfig:
    def test_loads_from_env(self):
        env = {
            "GITHUB_TOKEN": "ghp_test123",
            "NEBULUS_BASE_URL": "http://localhost:8080/v1",
            "NEBULUS_MODEL": "qwen3-30b",
        }
        with patch.dict("os.environ", env, clear=False):
            cfg = load_review_config()
        assert cfg.github_token == "ghp_test123"
        assert cfg.llm_base_url == "http://localhost:8080/v1"
        assert cfg.llm_model == "qwen3-30b"
        assert cfg.auto_merge_enabled is False

    def test_raises_without_github_token(self):
        env = {
            "NEBULUS_BASE_URL": "http://localhost:8080/v1",
            "NEBULUS_MODEL": "qwen3-30b",
        }
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(SystemExit):
                load_review_config()

    def test_uses_default_llm_settings(self):
        env = {"GITHUB_TOKEN": "ghp_test123"}
        with patch.dict("os.environ", env, clear=True):
            cfg = load_review_config()
        assert cfg.llm_base_url == "http://localhost:5000/v1"
        assert cfg.llm_model == "Meta-Llama-3.1-8B-Instruct-exl2-8_0"


# ---------------------------------------------------------------------------
# format_review_output
# ---------------------------------------------------------------------------


class TestFormatReviewOutput:
    def _make_workflow_result(self, **kwargs):
        defaults = dict(
            pr_details=PRDetails(
                repo="owner/repo",
                number=42,
                title="Add feature X",
                body="This PR adds X",
                author="dev",
                base_branch="main",
                head_branch="feat/x",
                created_at=None,
                files=[FileChange("a.py", "modified", 10, 2)],
                additions=10,
                deletions=2,
            ),
            llm_result=ReviewResult(
                decision=ReviewDecision.APPROVE,
                summary="Code looks good",
                confidence=0.85,
                issues=[],
                suggestions=["Add docstring"],
            ),
        )
        defaults.update(kwargs)
        return WorkflowResult(**defaults)

    def test_contains_pr_title(self):
        result = self._make_workflow_result()
        output = format_review_output(result)
        assert "Add feature X" in output

    def test_contains_decision(self):
        result = self._make_workflow_result()
        output = format_review_output(result)
        assert "APPROVE" in output

    def test_contains_confidence(self):
        result = self._make_workflow_result()
        output = format_review_output(result)
        assert "85%" in output

    def test_contains_summary(self):
        result = self._make_workflow_result()
        output = format_review_output(result)
        assert "Code looks good" in output

    def test_contains_suggestions(self):
        result = self._make_workflow_result()
        output = format_review_output(result)
        assert "Add docstring" in output

    def test_contains_issues_when_present(self):
        result = self._make_workflow_result(
            llm_result=ReviewResult(
                decision=ReviewDecision.REQUEST_CHANGES,
                summary="Needs fixes",
                confidence=0.7,
                issues=["Off-by-one error on line 15"],
            ),
        )
        output = format_review_output(result)
        assert "Off-by-one error" in output

    def test_contains_checks_when_present(self):
        checks = ChecksReport()
        checks.results.append(
            CheckResult(name="Tests", status=CheckStatus.PASSED, message="42 passed")
        )
        checks.results.append(
            CheckResult(
                name="Linting", status=CheckStatus.WARNING, message="2 warnings"
            )
        )
        result = self._make_workflow_result(checks_report=checks)
        output = format_review_output(result)
        assert "42 passed" in output
        assert "2 warnings" in output

    def test_contains_error_when_present(self):
        result = self._make_workflow_result(error="LLM unreachable")
        output = format_review_output(result)
        assert "LLM unreachable" in output

    def test_no_checks_section_when_none(self):
        result = self._make_workflow_result(checks_report=None)
        output = format_review_output(result)
        assert "Checks" not in output or "skipped" in output.lower()
