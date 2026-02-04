"""Tests for nebulus_swarm.reviewer — PR review pipeline.

Covers: checks.py, pr_reviewer.py, llm_review.py, workflow.py
"""

import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai")

from nebulus_swarm.reviewer.checks import (
    CheckResult,
    CheckRunner,
    ChecksReport,
    CheckStatus,
)
from nebulus_swarm.reviewer.llm_review import LLMReviewer, create_review_summary
from nebulus_swarm.reviewer.pr_reviewer import (
    FileChange,
    InlineComment,
    PRDetails,
    PRReviewer,
    ReviewDecision,
    ReviewResult,
)
from nebulus_swarm.reviewer.workflow import (
    ReviewConfig,
    ReviewWorkflow,
    WorkflowResult,
)


# ---------------------------------------------------------------------------
# checks.py — CheckStatus, CheckResult, ChecksReport
# ---------------------------------------------------------------------------


class TestCheckStatus:
    def test_enum_values(self):
        assert CheckStatus.PASSED.value == "passed"
        assert CheckStatus.FAILED.value == "failed"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.SKIPPED.value == "skipped"


class TestCheckResult:
    def test_defaults(self):
        r = CheckResult(name="foo", status=CheckStatus.PASSED, message="ok")
        assert r.name == "foo"
        assert r.details is None
        assert r.file_issues == []

    def test_with_details(self):
        r = CheckResult(
            name="lint",
            status=CheckStatus.WARNING,
            message="2 issues",
            details="extra info",
            file_issues=["a.py:1", "b.py:2"],
        )
        assert r.details == "extra info"
        assert len(r.file_issues) == 2


class TestChecksReport:
    def _make_report(self, statuses):
        report = ChecksReport()
        for i, s in enumerate(statuses):
            report.results.append(
                CheckResult(name=f"check-{i}", status=s, message="msg")
            )
        return report

    def test_all_passed_when_all_pass(self):
        report = self._make_report([CheckStatus.PASSED, CheckStatus.PASSED])
        assert report.all_passed is True
        assert report.has_failures is False

    def test_all_passed_allows_warnings_and_skips(self):
        report = self._make_report(
            [CheckStatus.PASSED, CheckStatus.WARNING, CheckStatus.SKIPPED]
        )
        assert report.all_passed is True

    def test_has_failures(self):
        report = self._make_report([CheckStatus.PASSED, CheckStatus.FAILED])
        assert report.all_passed is False
        assert report.has_failures is True

    def test_counts(self):
        report = self._make_report(
            [
                CheckStatus.PASSED,
                CheckStatus.PASSED,
                CheckStatus.FAILED,
                CheckStatus.WARNING,
            ]
        )
        assert report.passed_count == 2
        assert report.failed_count == 1
        assert report.warning_count == 1

    def test_empty_report(self):
        report = ChecksReport()
        assert report.all_passed is True
        assert report.has_failures is False
        assert report.passed_count == 0

    def test_get_summary_format(self):
        report = self._make_report([CheckStatus.PASSED, CheckStatus.FAILED])
        summary = report.get_summary()
        assert "## Automated Checks Report" in summary
        assert "check-0" in summary
        assert "check-1" in summary
        assert "1 passed" in summary
        assert "1 failed" in summary

    def test_get_summary_truncates_file_issues(self):
        report = ChecksReport()
        report.results.append(
            CheckResult(
                name="lint",
                status=CheckStatus.WARNING,
                message="many issues",
                file_issues=[f"issue-{i}" for i in range(10)],
            )
        )
        summary = report.get_summary()
        assert "issue-4" in summary
        assert "and 5 more" in summary


# ---------------------------------------------------------------------------
# checks.py — CheckRunner
# ---------------------------------------------------------------------------


class TestCheckRunnerPytest:
    def test_pytest_pass(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="42 passed in 1.0s", stderr=""
        )
        with patch("subprocess.run", return_value=completed):
            runner = CheckRunner("/fake/repo")
            result = runner.check_pytest()
        assert result.status == CheckStatus.PASSED
        assert "42" in result.message

    def test_pytest_no_tests(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=5, stdout="no tests ran", stderr=""
        )
        with patch("subprocess.run", return_value=completed):
            runner = CheckRunner("/fake/repo")
            result = runner.check_pytest()
        assert result.status == CheckStatus.SKIPPED

    def test_pytest_failure(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="3 failed, 10 passed", stderr=""
        )
        with patch("subprocess.run", return_value=completed):
            runner = CheckRunner("/fake/repo")
            result = runner.check_pytest()
        assert result.status == CheckStatus.FAILED
        assert "3" in result.message

    def test_pytest_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 300)):
            runner = CheckRunner("/fake/repo")
            result = runner.check_pytest()
        assert result.status == CheckStatus.FAILED
        assert "timed out" in result.message

    def test_pytest_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            runner = CheckRunner("/fake/repo")
            result = runner.check_pytest()
        assert result.status == CheckStatus.SKIPPED


class TestCheckRunnerRuff:
    def test_ruff_clean(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        with patch("subprocess.run", return_value=completed):
            runner = CheckRunner("/fake/repo")
            result = runner.check_ruff(["a.py"])
        assert result.status == CheckStatus.PASSED

    def test_ruff_warnings(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="a.py:1:1: E501 line too long\na.py:2:1: F401 unused",
            stderr="",
        )
        with patch("subprocess.run", return_value=completed):
            runner = CheckRunner("/fake/repo")
            result = runner.check_ruff(["a.py"])
        assert result.status == CheckStatus.WARNING
        assert "2" in result.message

    def test_ruff_no_python_files(self):
        runner = CheckRunner("/fake/repo")
        result = runner.check_ruff([])
        assert result.status == CheckStatus.SKIPPED

    def test_ruff_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            runner = CheckRunner("/fake/repo")
            result = runner.check_ruff(["a.py"])
        assert result.status == CheckStatus.SKIPPED


class TestCheckRunnerSecurity:
    def test_clean_file(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "clean.py").write_text("x = 1\n")
            runner = CheckRunner(td)
            result = runner.check_security_patterns(["clean.py"])
        assert result.status == CheckStatus.PASSED

    def test_detects_dangerous_eval(self):
        """Detects use of the dangerous eval() function in code under review."""
        with tempfile.TemporaryDirectory() as td:
            # This test intentionally writes code containing a security
            # anti-pattern to verify the checker flags it correctly
            Path(td, "bad.py").write_text("result = eval(user_input)\n")
            runner = CheckRunner(td)
            result = runner.check_security_patterns(["bad.py"])
        assert result.status == CheckStatus.WARNING
        assert len(result.file_issues) >= 1

    def test_detects_hardcoded_password(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "creds.py").write_text('password = "hunter2"\n')
            runner = CheckRunner(td)
            result = runner.check_security_patterns(["creds.py"])
        assert result.status == CheckStatus.WARNING

    def test_no_python_files(self):
        runner = CheckRunner("/fake/repo")
        result = runner.check_security_patterns([])
        assert result.status == CheckStatus.SKIPPED

    def test_missing_file_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            runner = CheckRunner(td)
            result = runner.check_security_patterns(["nonexistent.py"])
        assert result.status == CheckStatus.PASSED  # No issues found


class TestCheckRunnerComplexity:
    def test_low_complexity(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Average complexity: A (2.50)",
            stderr="",
        )
        with patch("subprocess.run", return_value=completed):
            runner = CheckRunner("/fake/repo")
            result = runner.check_complexity(["a.py"])
        assert result.status == CheckStatus.PASSED
        assert "A" in result.message

    def test_moderate_complexity(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Average complexity: C (15.00)",
            stderr="",
        )
        with patch("subprocess.run", return_value=completed):
            runner = CheckRunner("/fake/repo")
            result = runner.check_complexity(["a.py"])
        assert result.status == CheckStatus.WARNING

    def test_no_files(self):
        runner = CheckRunner("/fake/repo")
        result = runner.check_complexity([])
        assert result.status == CheckStatus.SKIPPED

    def test_radon_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            runner = CheckRunner("/fake/repo")
            result = runner.check_complexity(["a.py"])
        assert result.status == CheckStatus.SKIPPED


class TestCheckRunnerFileSizes:
    def test_small_files_pass(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "small.py").write_text("x = 1\n")
            runner = CheckRunner(td)
            result = runner.check_file_sizes(["small.py"])
        assert result.status == CheckStatus.PASSED

    def test_large_file_warning(self):
        with tempfile.TemporaryDirectory() as td:
            # 600KB file
            Path(td, "big.txt").write_text("x" * (600 * 1024))
            runner = CheckRunner(td)
            result = runner.check_file_sizes(["big.txt"])
        assert result.status == CheckStatus.WARNING

    def test_long_python_file_warning(self):
        with tempfile.TemporaryDirectory() as td:
            lines = "\n".join([f"line_{i} = {i}" for i in range(1200)])
            Path(td, "long.py").write_text(lines)
            runner = CheckRunner(td)
            result = runner.check_file_sizes(["long.py"])
        assert result.status == CheckStatus.WARNING
        assert "1200" in result.file_issues[0] or "lines" in result.file_issues[0]


class TestCheckRunnerRunAll:
    def test_run_all_checks_returns_report(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "app.py").write_text("x = 1\n")
            runner = CheckRunner(td)
            with (
                patch.object(runner, "check_pytest") as mock_pytest,
                patch.object(runner, "check_ruff") as mock_ruff,
                patch.object(runner, "check_skill_changes") as mock_skill,
            ):
                mock_pytest.return_value = CheckResult(
                    name="Tests", status=CheckStatus.PASSED, message="ok"
                )
                mock_ruff.return_value = CheckResult(
                    name="Lint", status=CheckStatus.PASSED, message="ok"
                )
                mock_skill.return_value = CheckResult(
                    name="Skills", status=CheckStatus.SKIPPED, message="none"
                )
                report = runner.run_all_checks(["app.py", "readme.md"])

        assert isinstance(report, ChecksReport)
        # pytest, ruff, security, complexity, sizes, skills
        assert len(report.results) == 6

    def test_filters_python_files_for_ruff(self):
        with tempfile.TemporaryDirectory() as td:
            runner = CheckRunner(td)
            with (
                patch.object(runner, "check_pytest") as mock_pt,
                patch.object(runner, "check_ruff") as mock_ruff,
                patch.object(runner, "check_security_patterns") as mock_sec,
                patch.object(runner, "check_complexity") as mock_cx,
                patch.object(runner, "check_file_sizes") as mock_fs,
                patch.object(runner, "check_skill_changes") as mock_sk,
            ):
                for m in [mock_pt, mock_ruff, mock_sec, mock_cx, mock_fs, mock_sk]:
                    m.return_value = CheckResult(
                        name="x", status=CheckStatus.PASSED, message="ok"
                    )
                runner.run_all_checks(["app.py", "readme.md", "data.json"])

            # ruff, security, complexity called with only python files
            mock_ruff.assert_called_once_with(["app.py"])


# ---------------------------------------------------------------------------
# pr_reviewer.py — dataclasses
# ---------------------------------------------------------------------------


class TestFileChange:
    def test_total_changes(self):
        fc = FileChange(filename="a.py", status="modified", additions=10, deletions=3)
        assert fc.total_changes == 13

    def test_optional_patch(self):
        fc = FileChange(filename="b.py", status="added", additions=5, deletions=0)
        assert fc.patch is None


class TestPRDetails:
    def _make_pr(self, **kwargs):
        defaults = dict(
            repo="owner/repo",
            number=42,
            title="Add feature",
            body="Description here",
            author="dev",
            base_branch="main",
            head_branch="feat/thing",
            created_at=datetime(2026, 2, 4),
            files=[
                FileChange("a.py", "modified", 10, 2, patch="+new\n-old"),
                FileChange("b.py", "added", 5, 0, patch="+added"),
            ],
            commits=3,
            additions=15,
            deletions=2,
        )
        defaults.update(kwargs)
        return PRDetails(**defaults)

    def test_total_changes(self):
        pr = self._make_pr()
        assert pr.total_changes == 17

    def test_get_diff_summary_contains_metadata(self):
        pr = self._make_pr()
        summary = pr.get_diff_summary()
        assert "PR #42" in summary
        assert "Add feature" in summary
        assert "dev" in summary
        assert "feat/thing" in summary
        assert "a.py" in summary

    def test_get_diff_summary_without_body(self):
        pr = self._make_pr(body="")
        summary = pr.get_diff_summary()
        assert "Description" not in summary

    def test_get_full_diff(self):
        pr = self._make_pr()
        diff = pr.get_full_diff(max_lines=100)
        assert "a.py" in diff
        assert "+new" in diff

    def test_get_full_diff_truncation(self):
        long_patch = "\n".join([f"+line{i}" for i in range(600)])
        pr = self._make_pr(
            files=[FileChange("big.py", "modified", 600, 0, patch=long_patch)]
        )
        diff = pr.get_full_diff(max_lines=50)
        assert "truncated" in diff.lower()


class TestReviewDecision:
    def test_enum_values(self):
        assert ReviewDecision.APPROVE.value == "APPROVE"
        assert ReviewDecision.REQUEST_CHANGES.value == "REQUEST_CHANGES"
        assert ReviewDecision.COMMENT.value == "COMMENT"


class TestInlineComment:
    def test_defaults(self):
        c = InlineComment(path="a.py", line=10, body="Fix this")
        assert c.side == "RIGHT"


class TestReviewResult:
    def test_can_auto_merge_when_eligible(self):
        r = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="Looks good",
            checks_passed=True,
            confidence=0.9,
            issues=[],
        )
        assert r.can_auto_merge is True

    def test_cannot_auto_merge_low_confidence(self):
        r = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="ok",
            checks_passed=True,
            confidence=0.5,
        )
        assert r.can_auto_merge is False

    def test_cannot_auto_merge_with_issues(self):
        r = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="ok",
            checks_passed=True,
            confidence=0.9,
            issues=["bug found"],
        )
        assert r.can_auto_merge is False

    def test_cannot_auto_merge_checks_failed(self):
        r = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="ok",
            checks_passed=False,
            confidence=0.9,
        )
        assert r.can_auto_merge is False

    def test_cannot_auto_merge_request_changes(self):
        r = ReviewResult(
            decision=ReviewDecision.REQUEST_CHANGES,
            summary="needs work",
            checks_passed=True,
            confidence=0.9,
        )
        assert r.can_auto_merge is False


# ---------------------------------------------------------------------------
# pr_reviewer.py — PRReviewer._extract_linked_issue
# ---------------------------------------------------------------------------


class TestExtractLinkedIssue:
    def _extract(self, body):
        reviewer = PRReviewer.__new__(PRReviewer)
        return reviewer._extract_linked_issue(body)

    def test_closes_pattern(self):
        assert self._extract("Closes #42") == 42

    def test_fixes_pattern(self):
        assert self._extract("fixes #7") == 7

    def test_resolves_pattern(self):
        assert self._extract("Resolves #100") == 100

    def test_fallback_hash_reference(self):
        assert self._extract("Related to #55") == 55

    def test_no_issue(self):
        assert self._extract("No issue reference here") is None

    def test_empty_body(self):
        assert self._extract("") is None


# ---------------------------------------------------------------------------
# llm_review.py — LLMReviewer parsing
# ---------------------------------------------------------------------------


class TestLLMReviewerParsing:
    def _make_reviewer(self):
        with patch("nebulus_swarm.reviewer.llm_review.OpenAI"):
            reviewer = LLMReviewer(
                base_url="http://localhost:5000/v1", model="test-model"
            )
        return reviewer

    def test_parse_valid_json(self):
        reviewer = self._make_reviewer()
        content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.85,
                "summary": "Code looks good",
                "issues": [],
                "suggestions": ["Add docstring"],
                "inline_comments": [
                    {"path": "a.py", "line": 10, "body": "Nice refactor"}
                ],
            }
        )
        result = reviewer._parse_review_response(content)
        assert result.decision == ReviewDecision.APPROVE
        assert result.confidence == 0.85
        assert result.summary == "Code looks good"
        assert len(result.suggestions) == 1
        assert len(result.inline_comments) == 1
        assert result.inline_comments[0].path == "a.py"

    def test_parse_request_changes(self):
        reviewer = self._make_reviewer()
        content = json.dumps(
            {
                "decision": "REQUEST_CHANGES",
                "confidence": 0.7,
                "summary": "Has bugs",
                "issues": ["Off-by-one"],
            }
        )
        result = reviewer._parse_review_response(content)
        assert result.decision == ReviewDecision.REQUEST_CHANGES
        assert "Off-by-one" in result.issues

    def test_parse_json_embedded_in_text(self):
        reviewer = self._make_reviewer()
        content = (
            "Here is my review:\n"
            '{"decision": "COMMENT", "confidence": 0.6, "summary": "Needs work"}\n'
            "End."
        )
        result = reviewer._parse_review_response(content)
        assert result.decision == ReviewDecision.COMMENT
        assert result.confidence == 0.6

    def test_parse_no_json(self):
        reviewer = self._make_reviewer()
        result = reviewer._parse_review_response("Just some text with no JSON")
        assert result.decision == ReviewDecision.COMMENT
        assert result.confidence == 0.0

    def test_parse_invalid_json(self):
        reviewer = self._make_reviewer()
        result = reviewer._parse_review_response("{not valid json at all}")
        assert result.decision == ReviewDecision.COMMENT
        assert result.confidence == 0.0

    def test_parse_unknown_decision_defaults_to_comment(self):
        reviewer = self._make_reviewer()
        content = json.dumps(
            {"decision": "UNKNOWN", "confidence": 0.5, "summary": "hmm"}
        )
        result = reviewer._parse_review_response(content)
        assert result.decision == ReviewDecision.COMMENT

    def test_parse_missing_fields_use_defaults(self):
        reviewer = self._make_reviewer()
        content = json.dumps({})
        result = reviewer._parse_review_response(content)
        assert result.decision == ReviewDecision.COMMENT
        assert result.summary == "Review completed"
        assert result.confidence == 0.5

    def test_parse_inline_comment_missing_body_skipped(self):
        reviewer = self._make_reviewer()
        content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.9,
                "summary": "ok",
                "inline_comments": [
                    {"path": "a.py", "line": 1},  # missing body
                    {"path": "b.py", "line": 2, "body": "real comment"},
                ],
            }
        )
        result = reviewer._parse_review_response(content)
        assert len(result.inline_comments) == 1
        assert result.inline_comments[0].path == "b.py"


class TestLLMReviewerBuildPrompt:
    def _make_reviewer(self):
        with patch("nebulus_swarm.reviewer.llm_review.OpenAI"):
            return LLMReviewer(base_url="http://localhost:5000/v1", model="test-model")

    def test_prompt_includes_pr_info(self):
        reviewer = self._make_reviewer()
        pr = PRDetails(
            repo="owner/repo",
            number=1,
            title="Fix bug",
            body="Fixed it",
            author="dev",
            base_branch="main",
            head_branch="fix/bug",
            created_at=datetime(2026, 1, 1),
            files=[FileChange("a.py", "modified", 5, 2, patch="+fix\n-bug")],
        )
        prompt = reviewer._build_review_prompt(pr, max_lines=500)
        assert "Pull Request Review Request" in prompt
        assert "Fix bug" in prompt
        assert "+fix" in prompt


class TestLLMReviewerReviewPR:
    def test_review_pr_success(self):
        with patch("nebulus_swarm.reviewer.llm_review.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps(
                {
                    "decision": "APPROVE",
                    "confidence": 0.9,
                    "summary": "LGTM",
                    "issues": [],
                    "suggestions": [],
                }
            )
            mock_client.chat.completions.create.return_value = mock_response

            reviewer = LLMReviewer(
                base_url="http://localhost:5000/v1", model="test-model"
            )
            pr = PRDetails(
                repo="owner/repo",
                number=1,
                title="PR",
                body="",
                author="dev",
                base_branch="main",
                head_branch="feat/x",
                created_at=datetime(2026, 1, 1),
            )
            result = reviewer.review_pr(pr)

        assert result.decision == ReviewDecision.APPROVE
        assert result.confidence == 0.9

    def test_review_pr_llm_error(self):
        with patch("nebulus_swarm.reviewer.llm_review.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("LLM down")

            reviewer = LLMReviewer(
                base_url="http://localhost:5000/v1", model="test-model"
            )
            pr = PRDetails(
                repo="owner/repo",
                number=1,
                title="PR",
                body="",
                author="dev",
                base_branch="main",
                head_branch="feat/x",
                created_at=datetime(2026, 1, 1),
            )
            result = reviewer.review_pr(pr)

        assert result.decision == ReviewDecision.COMMENT
        assert result.confidence == 0.0
        assert "LLM down" in result.issues[0]


class TestAnalyzeSpecificFile:
    def test_analyze_success(self):
        with patch("nebulus_swarm.reviewer.llm_review.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Looks clean."
            mock_client.chat.completions.create.return_value = mock_response

            reviewer = LLMReviewer(
                base_url="http://localhost:5000/v1", model="test-model"
            )
            result = reviewer.analyze_specific_file("app.py", "x = 1", "security")

        assert result == "Looks clean."

    def test_analyze_error(self):
        with patch("nebulus_swarm.reviewer.llm_review.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("timeout")

            reviewer = LLMReviewer(
                base_url="http://localhost:5000/v1", model="test-model"
            )
            result = reviewer.analyze_specific_file("app.py", "x = 1")

        assert "failed" in result.lower()


# ---------------------------------------------------------------------------
# llm_review.py — create_review_summary
# ---------------------------------------------------------------------------


class TestCreateReviewSummary:
    def _make_pr(self):
        return PRDetails(
            repo="owner/repo",
            number=10,
            title="Add widget",
            body="",
            author="dev",
            base_branch="main",
            head_branch="feat/widget",
            created_at=datetime(2026, 1, 1),
        )

    def test_basic_summary(self):
        result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="All good",
            confidence=0.9,
        )
        summary = create_review_summary(self._make_pr(), result)
        assert "owner/repo#10" in summary
        assert "APPROVE" in summary
        assert "90%" in summary
        assert "All good" in summary

    def test_summary_with_issues_and_suggestions(self):
        result = ReviewResult(
            decision=ReviewDecision.REQUEST_CHANGES,
            summary="Needs work",
            confidence=0.6,
            issues=["Bug on line 5"],
            suggestions=["Add tests"],
        )
        summary = create_review_summary(self._make_pr(), result)
        assert "Bug on line 5" in summary
        assert "Add tests" in summary
        assert "## Issues" in summary
        assert "## Suggestions" in summary

    def test_summary_with_checks(self):
        result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="ok",
            confidence=0.9,
        )
        summary = create_review_summary(
            self._make_pr(), result, checks_summary="All checks passed"
        )
        assert "All checks passed" in summary

    def test_summary_auto_merge_eligible(self):
        result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="Perfect",
            checks_passed=True,
            confidence=0.95,
            issues=[],
        )
        summary = create_review_summary(self._make_pr(), result)
        assert "auto-merge" in summary.lower()

    def test_summary_not_auto_merge(self):
        result = ReviewResult(
            decision=ReviewDecision.COMMENT,
            summary="Meh",
            confidence=0.5,
        )
        summary = create_review_summary(self._make_pr(), result)
        assert "auto-merge" not in summary.lower()


# ---------------------------------------------------------------------------
# workflow.py — ReviewConfig, WorkflowResult
# ---------------------------------------------------------------------------


class TestReviewConfig:
    def test_defaults(self):
        cfg = ReviewConfig(
            github_token="tok",
            llm_base_url="http://localhost:5000/v1",
            llm_model="test",
        )
        assert cfg.auto_merge_enabled is False
        assert cfg.run_local_checks is True
        assert cfg.max_diff_lines == 500
        assert cfg.min_confidence_for_approve == 0.8
        assert cfg.merge_method == "squash"
        assert cfg.llm_timeout == 120


class TestWorkflowResult:
    def test_summary_format(self):
        wr = WorkflowResult(
            pr_details=PRDetails(
                repo="owner/repo",
                number=5,
                title="t",
                body="",
                author="a",
                base_branch="main",
                head_branch="feat/x",
                created_at=datetime(2026, 1, 1),
            ),
            llm_result=ReviewResult(
                decision=ReviewDecision.APPROVE,
                summary="ok",
                confidence=0.85,
            ),
            review_posted=True,
        )
        s = wr.summary
        assert "owner/repo#5" in s
        assert "APPROVE" in s
        assert "85%" in s
        assert "Review posted: Yes" in s

    def test_summary_with_checks(self):
        report = ChecksReport()
        report.results.append(
            CheckResult(name="t", status=CheckStatus.PASSED, message="ok")
        )
        report.results.append(
            CheckResult(name="l", status=CheckStatus.FAILED, message="fail")
        )
        wr = WorkflowResult(
            pr_details=PRDetails(
                repo="r",
                number=1,
                title="",
                body="",
                author="",
                base_branch="",
                head_branch="",
                created_at=None,
            ),
            llm_result=ReviewResult(
                decision=ReviewDecision.COMMENT, summary="s", confidence=0.5
            ),
            checks_report=report,
        )
        s = wr.summary
        assert "1 passed" in s
        assert "1 failed" in s

    def test_summary_with_error(self):
        wr = WorkflowResult(
            pr_details=PRDetails(
                repo="r",
                number=1,
                title="",
                body="",
                author="",
                base_branch="",
                head_branch="",
                created_at=None,
            ),
            llm_result=ReviewResult(
                decision=ReviewDecision.COMMENT, summary="s", confidence=0.0
            ),
            error="Network timeout",
        )
        assert "Network timeout" in wr.summary


# ---------------------------------------------------------------------------
# workflow.py — ReviewWorkflow
# ---------------------------------------------------------------------------


class TestReviewWorkflow:
    def _make_workflow(self):
        cfg = ReviewConfig(
            github_token="fake-token",
            llm_base_url="http://localhost:5000/v1",
            llm_model="test-model",
        )
        return ReviewWorkflow(cfg)

    def _mock_pr_details(self):
        return PRDetails(
            repo="owner/repo",
            number=1,
            title="Feature",
            body="Adds feature",
            author="dev",
            base_branch="main",
            head_branch="feat/x",
            created_at=datetime(2026, 1, 1),
            files=[FileChange("a.py", "modified", 10, 2, patch="+new")],
            additions=10,
            deletions=2,
        )

    def test_review_pr_full_pipeline(self):
        wf = self._make_workflow()
        pr_details = self._mock_pr_details()
        llm_result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="LGTM",
            confidence=0.9,
        )

        wf._pr_reviewer = MagicMock()
        wf._llm_reviewer = MagicMock()
        wf._pr_reviewer.get_pr_details.return_value = pr_details
        wf._pr_reviewer.post_review.return_value = True
        wf._llm_reviewer.review_pr.return_value = llm_result

        result = wf.review_pr("owner/repo", 1, post_review=True)

        assert result.pr_details == pr_details
        assert result.llm_result.decision == ReviewDecision.APPROVE
        assert result.review_posted is True
        assert result.error is None

    def test_review_pr_without_posting(self):
        wf = self._make_workflow()
        pr_details = self._mock_pr_details()
        llm_result = ReviewResult(
            decision=ReviewDecision.COMMENT,
            summary="ok",
            confidence=0.7,
        )

        wf._pr_reviewer = MagicMock()
        wf._llm_reviewer = MagicMock()
        wf._pr_reviewer.get_pr_details.return_value = pr_details
        wf._llm_reviewer.review_pr.return_value = llm_result

        result = wf.review_pr("owner/repo", 1, post_review=False)
        assert result.review_posted is False
        wf._pr_reviewer.post_review.assert_not_called()

    def test_review_pr_with_local_checks(self):
        wf = self._make_workflow()
        pr_details = self._mock_pr_details()
        llm_result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="ok",
            confidence=0.9,
        )

        wf._pr_reviewer = MagicMock()
        wf._llm_reviewer = MagicMock()
        wf._pr_reviewer.get_pr_details.return_value = pr_details
        wf._pr_reviewer.post_review.return_value = True
        wf._llm_reviewer.review_pr.return_value = llm_result

        with tempfile.TemporaryDirectory() as td:
            checks_report = ChecksReport()
            checks_report.results.append(
                CheckResult(name="Tests", status=CheckStatus.PASSED, message="ok")
            )
            with patch.object(wf, "_run_checks", return_value=checks_report):
                result = wf.review_pr("owner/repo", 1, repo_path=td)

        assert result.checks_report is not None
        assert result.llm_result.checks_passed is True

    def test_review_pr_checks_failure_propagated(self):
        wf = self._make_workflow()
        pr_details = self._mock_pr_details()
        llm_result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="ok",
            confidence=0.9,
        )

        wf._pr_reviewer = MagicMock()
        wf._llm_reviewer = MagicMock()
        wf._pr_reviewer.get_pr_details.return_value = pr_details
        wf._pr_reviewer.post_review.return_value = True
        wf._llm_reviewer.review_pr.return_value = llm_result

        checks_report = ChecksReport()
        checks_report.results.append(
            CheckResult(name="Tests", status=CheckStatus.FAILED, message="3 failed")
        )
        with patch.object(wf, "_run_checks", return_value=checks_report):
            result = wf.review_pr("owner/repo", 1, repo_path="/fake")

        assert result.llm_result.checks_passed is False

    def test_review_pr_error_returns_partial_result(self):
        wf = self._make_workflow()
        wf._pr_reviewer = MagicMock()
        wf._pr_reviewer.get_pr_details.side_effect = Exception("API down")

        result = wf.review_pr("owner/repo", 1)
        assert result.error == "API down"
        assert result.llm_result.confidence == 0.0

    def test_review_pr_auto_merge_disabled(self):
        wf = self._make_workflow()
        wf.config.auto_merge_enabled = False
        pr_details = self._mock_pr_details()
        llm_result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="ok",
            checks_passed=True,
            confidence=0.95,
        )

        wf._pr_reviewer = MagicMock()
        wf._llm_reviewer = MagicMock()
        wf._pr_reviewer.get_pr_details.return_value = pr_details
        wf._pr_reviewer.post_review.return_value = True
        wf._llm_reviewer.review_pr.return_value = llm_result

        result = wf.review_pr("owner/repo", 1, auto_merge=True)
        assert result.merged is False
        wf._pr_reviewer.merge_pr.assert_not_called()

    def test_review_pr_auto_merge_enabled(self):
        wf = self._make_workflow()
        wf.config.auto_merge_enabled = True
        pr_details = self._mock_pr_details()
        llm_result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="ok",
            checks_passed=True,
            confidence=0.95,
            issues=[],
        )

        wf._pr_reviewer = MagicMock()
        wf._llm_reviewer = MagicMock()
        wf._pr_reviewer.get_pr_details.return_value = pr_details
        wf._pr_reviewer.post_review.return_value = True
        wf._pr_reviewer.merge_pr.return_value = True
        wf._llm_reviewer.review_pr.return_value = llm_result

        result = wf.review_pr("owner/repo", 1, auto_merge=True)
        assert result.merged is True
        wf._pr_reviewer.merge_pr.assert_called_once()


class TestReviewFromWebhook:
    def _make_workflow(self):
        cfg = ReviewConfig(
            github_token="tok",
            llm_base_url="http://localhost:5000/v1",
            llm_model="test",
        )
        return ReviewWorkflow(cfg)

    def test_skips_non_reviewable_actions(self):
        wf = self._make_workflow()
        assert wf.review_from_webhook("r", 1, "closed") is None
        assert wf.review_from_webhook("r", 1, "labeled") is None
        assert wf.review_from_webhook("r", 1, "assigned") is None

    def test_reviews_opened_prs(self):
        wf = self._make_workflow()
        with patch.object(wf, "review_pr") as mock_review:
            mock_review.return_value = MagicMock()
            result = wf.review_from_webhook("owner/repo", 5, "opened")
        mock_review.assert_called_once()
        assert result is not None

    def test_reviews_synchronize(self):
        wf = self._make_workflow()
        with patch.object(wf, "review_pr") as mock_review:
            mock_review.return_value = MagicMock()
            wf.review_from_webhook("owner/repo", 5, "synchronize")
        mock_review.assert_called_once()

    def test_reviews_reopened(self):
        wf = self._make_workflow()
        with patch.object(wf, "review_pr") as mock_review:
            mock_review.return_value = MagicMock()
            wf.review_from_webhook("owner/repo", 5, "reopened")
        mock_review.assert_called_once()


class TestWorkflowClose:
    def test_close_cleans_up(self):
        cfg = ReviewConfig(
            github_token="tok",
            llm_base_url="http://localhost:5000/v1",
            llm_model="test",
        )
        wf = ReviewWorkflow(cfg)
        mock_pr = MagicMock()
        wf._pr_reviewer = mock_pr
        wf.close()
        mock_pr.close.assert_called_once()

    def test_close_without_reviewer(self):
        cfg = ReviewConfig(
            github_token="tok",
            llm_base_url="http://localhost:5000/v1",
            llm_model="test",
        )
        wf = ReviewWorkflow(cfg)
        wf.close()  # should not raise
