"""Tests for the supervisor evaluation layer."""

from nebulus_swarm.overlord.evaluator import (
    CheckScore,
    EvaluationResult,
    RevisionRequest,
)


class TestCheckScore:
    def test_pass_value(self):
        assert CheckScore.PASS.value == "pass"

    def test_fail_value(self):
        assert CheckScore.FAIL.value == "fail"

    def test_needs_revision_value(self):
        assert CheckScore.NEEDS_REVISION.value == "needs_revision"


class TestEvaluationResult:
    def test_overall_pass_when_all_pass(self):
        result = EvaluationResult(
            pr_number=1,
            repo="owner/repo",
            test_score=CheckScore.PASS,
            lint_score=CheckScore.PASS,
            review_score=CheckScore.PASS,
        )
        assert result.overall == CheckScore.PASS

    def test_overall_needs_revision_when_any_needs_revision(self):
        result = EvaluationResult(
            pr_number=1,
            repo="owner/repo",
            test_score=CheckScore.PASS,
            lint_score=CheckScore.NEEDS_REVISION,
            review_score=CheckScore.PASS,
        )
        assert result.overall == CheckScore.NEEDS_REVISION

    def test_overall_fail_when_any_fail(self):
        result = EvaluationResult(
            pr_number=1,
            repo="owner/repo",
            test_score=CheckScore.FAIL,
            lint_score=CheckScore.PASS,
            review_score=CheckScore.NEEDS_REVISION,
        )
        assert result.overall == CheckScore.FAIL

    def test_fail_beats_needs_revision(self):
        result = EvaluationResult(
            pr_number=1,
            repo="owner/repo",
            test_score=CheckScore.NEEDS_REVISION,
            lint_score=CheckScore.FAIL,
            review_score=CheckScore.NEEDS_REVISION,
        )
        assert result.overall == CheckScore.FAIL

    def test_default_revision_number_is_zero(self):
        result = EvaluationResult(
            pr_number=1,
            repo="owner/repo",
            test_score=CheckScore.PASS,
            lint_score=CheckScore.PASS,
            review_score=CheckScore.PASS,
        )
        assert result.revision_number == 0

    def test_feedback_aggregation(self):
        result = EvaluationResult(
            pr_number=1,
            repo="owner/repo",
            test_score=CheckScore.FAIL,
            lint_score=CheckScore.PASS,
            review_score=CheckScore.PASS,
            test_feedback="3 tests failed",
            lint_feedback="",
            review_feedback="",
        )
        combined = result.combined_feedback
        assert "3 tests failed" in combined


class TestRevisionRequest:
    def test_has_required_fields(self):
        req = RevisionRequest(
            repo="owner/repo",
            pr_number=42,
            issue_number=10,
            branch="minion/issue-10",
            feedback="Tests failed: test_foo, test_bar",
            revision_number=1,
        )
        assert req.repo == "owner/repo"
        assert req.revision_number == 1
