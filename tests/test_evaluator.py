"""Tests for the supervisor evaluation layer."""

import pytest

# Guard against missing optional dependencies
pytest.importorskip("openai")
pytest.importorskip("github")


from nebulus_swarm.overlord.evaluator import (
    CheckScore,
    EvaluationResult,
    Evaluator,
    RevisionRequest,
    MAX_REVISIONS,
)
from nebulus_swarm.reviewer.checks import CheckResult, ChecksReport, CheckStatus
from nebulus_swarm.reviewer.pr_reviewer import ReviewDecision, ReviewResult


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


class TestEvaluator:
    def _make_evaluator(self):
        return Evaluator(
            llm_base_url="http://localhost:5000/v1",
            llm_model="test-model",
            github_token="ghp_test",
        )

    def test_all_pass(self):
        ev = self._make_evaluator()
        checks = ChecksReport(
            results=[
                CheckResult(
                    name="pytest", status=CheckStatus.PASSED, message="10 passed"
                ),
                CheckResult(name="ruff", status=CheckStatus.PASSED, message="clean"),
            ]
        )
        review = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="Looks good",
            confidence=0.9,
        )
        result = ev._score(checks, review, repo="o/r", pr_number=1)
        assert result.overall == CheckScore.PASS

    def test_test_failure_means_needs_revision(self):
        ev = self._make_evaluator()
        checks = ChecksReport(
            results=[
                CheckResult(
                    name="pytest", status=CheckStatus.FAILED, message="2 failed"
                ),
                CheckResult(name="ruff", status=CheckStatus.PASSED, message="clean"),
            ]
        )
        review = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="Looks good",
            confidence=0.9,
        )
        result = ev._score(checks, review, repo="o/r", pr_number=1)
        assert result.test_score == CheckScore.NEEDS_REVISION
        assert "2 failed" in result.test_feedback

    def test_request_changes_means_needs_revision(self):
        ev = self._make_evaluator()
        checks = ChecksReport(
            results=[
                CheckResult(name="pytest", status=CheckStatus.PASSED, message="ok"),
            ]
        )
        review = ReviewResult(
            decision=ReviewDecision.REQUEST_CHANGES,
            summary="Has bugs",
            confidence=0.8,
            issues=["Off by one error"],
        )
        result = ev._score(checks, review, repo="o/r", pr_number=1)
        assert result.review_score == CheckScore.NEEDS_REVISION

    def test_low_confidence_review_means_pass(self):
        ev = self._make_evaluator()
        checks = ChecksReport(results=[])
        review = ReviewResult(
            decision=ReviewDecision.COMMENT,
            summary="Minor suggestions",
            confidence=0.6,
        )
        result = ev._score(checks, review, repo="o/r", pr_number=1)
        assert result.review_score == CheckScore.PASS

    def test_can_revise_under_max(self):
        ev = self._make_evaluator()
        assert ev.can_revise(revision_number=0) is True
        assert ev.can_revise(revision_number=1) is True

    def test_cannot_revise_at_max(self):
        ev = self._make_evaluator()
        assert ev.can_revise(revision_number=MAX_REVISIONS) is False


class TestEvaluationStorage:
    def test_store_and_retrieve_evaluation(self, tmp_path):
        from nebulus_swarm.overlord.state import OverlordState

        state = OverlordState(db_path=str(tmp_path / "test.db"))
        result = EvaluationResult(
            pr_number=42,
            repo="owner/repo",
            test_score=CheckScore.PASS,
            lint_score=CheckScore.PASS,
            review_score=CheckScore.NEEDS_REVISION,
            revision_number=1,
            review_feedback="Needs error handling",
        )
        state.save_evaluation(result)
        history = state.get_evaluations(repo="owner/repo", pr_number=42)
        assert len(history) == 1
        assert history[0]["review_score"] == "needs_revision"
