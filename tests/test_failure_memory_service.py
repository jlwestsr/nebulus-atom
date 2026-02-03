"""Tests for failure memory models and service."""

import pytest

from nebulus_atom.models.failure_memory import (
    FailureContext,
    FailurePattern,
)
from nebulus_atom.services.failure_memory_service import (
    FailureMemoryService,
    FailureMemoryServiceManager,
)
from nebulus_atom.services.cognition_service import CognitionService


# ── Error Classification ──────────────────────────────────────────────


class TestErrorClassification:
    """Test error message classification into known types."""

    def test_file_not_found(self):
        result = FailureMemoryService._classify_error("FileNotFoundError: No such file")
        assert result == "file_not_found"

    def test_missing_module(self):
        result = FailureMemoryService._classify_error(
            "ModuleNotFoundError: No module named 'foo'"
        )
        assert result == "missing_module"

    def test_invalid_json(self):
        result = FailureMemoryService._classify_error(
            "json.decoder.JSONDecodeError: Expecting value"
        )
        assert result == "invalid_json"

    def test_syntax_error(self):
        result = FailureMemoryService._classify_error("SyntaxError: invalid syntax")
        assert result == "syntax_error"

    def test_permission_denied(self):
        result = FailureMemoryService._classify_error(
            "PermissionError: Permission denied"
        )
        assert result == "permission_denied"

    def test_timeout(self):
        result = FailureMemoryService._classify_error("TimeoutError: timed out")
        assert result == "timeout"

    def test_command_failed(self):
        result = FailureMemoryService._classify_error("non-zero exit code 1")
        assert result == "command_failed"

    def test_unknown_fallback(self):
        result = FailureMemoryService._classify_error("something completely different")
        assert result == "unknown"


# ── Arg Sanitization ─────────────────────────────────────────────────


class TestArgSanitization:
    """Test that argument sanitization keeps safe keys and strips sensitive ones."""

    def test_keeps_safe_keys(self):
        args = {"path": "/foo", "command": "ls", "query": "search", "api_key": "secret"}
        result = FailureMemoryService._sanitize_args(args)
        assert result == {"path": "/foo", "command": "ls", "query": "search"}

    def test_strips_sensitive_keys(self):
        args = {"password": "abc", "token": "xyz", "content": "big blob"}
        result = FailureMemoryService._sanitize_args(args)
        assert result == {}


# ── FailurePattern Model ─────────────────────────────────────────────


class TestFailurePatternModel:
    """Test confidence penalty calculations on FailurePattern."""

    def test_confidence_penalty_basic(self):
        """3 occurrences, 0 resolved → 3*0.03 = 0.09."""
        pattern = FailurePattern(
            tool_name="t", error_type="e", occurrence_count=3, resolved_count=0
        )
        assert abs(pattern.confidence_penalty - 0.09) < 1e-6

    def test_confidence_penalty_with_resolution_discount(self):
        """4 occurrences, 2 resolved → base min(0.12, 0.15)=0.12,
        resolution_rate=0.5, discount=0.25, penalty=0.12*0.75=0.09."""
        pattern = FailurePattern(
            tool_name="t", error_type="e", occurrence_count=4, resolved_count=2
        )
        assert abs(pattern.confidence_penalty - 0.09) < 1e-6

    def test_confidence_penalty_cap_at_020(self):
        """Large count → base caps at 0.15, with 0 resolved → 0.15, under 0.20 cap."""
        pattern = FailurePattern(
            tool_name="t", error_type="e", occurrence_count=100, resolved_count=0
        )
        assert pattern.confidence_penalty == 0.15

    def test_resolution_rate_zero_count(self):
        """Zero occurrences → resolution rate 0."""
        pattern = FailurePattern(
            tool_name="t", error_type="e", occurrence_count=0, resolved_count=0
        )
        assert pattern.resolution_rate == 0.0
        assert pattern.confidence_penalty == 0.0


# ── FailureContext Model ─────────────────────────────────────────────


class TestFailureContextModel:
    """Test total penalty aggregation on FailureContext."""

    def test_total_penalty_aggregation(self):
        """Sum of two patterns' penalties."""
        p1 = FailurePattern(tool_name="a", error_type="e1", occurrence_count=3)
        p2 = FailurePattern(tool_name="b", error_type="e2", occurrence_count=2)
        ctx = FailureContext(patterns=[p1, p2])
        expected = p1.confidence_penalty + p2.confidence_penalty
        assert abs(ctx.total_penalty - expected) < 1e-6

    def test_total_penalty_cap_at_025(self):
        """Many patterns should cap total at 0.25."""
        patterns = [
            FailurePattern(tool_name=f"t{i}", error_type="e", occurrence_count=100)
            for i in range(10)
        ]
        ctx = FailureContext(patterns=patterns)
        assert ctx.total_penalty == 0.25

    def test_empty_context(self):
        ctx = FailureContext()
        assert ctx.total_penalty == 0.0


# ── FailureMemoryService DB Operations ───────────────────────────────


class TestFailureMemoryServiceDB:
    """Test database operations of FailureMemoryService."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a service with a temp database."""
        db_path = str(tmp_path / "test_failures.db")
        return FailureMemoryService(db_path=db_path)

    def test_record_failure(self, service):
        record = service.record_failure(
            "s1", "read_file", "FileNotFoundError: No such file", {"path": "/x"}
        )
        assert record.tool_name == "read_file"
        assert record.error_type == "file_not_found"
        assert record.args_context == {"path": "/x"}
        assert not record.resolved

    def test_query_similar_failures(self, service):
        service.record_failure("s1", "read_file", "No such file")
        service.record_failure("s1", "read_file", "No such file")

        pattern = service.query_similar_failures("read_file", "file_not_found")
        assert pattern.occurrence_count == 2
        assert pattern.resolved_count == 0

    def test_query_no_matches(self, service):
        pattern = service.query_similar_failures("nonexistent", "unknown")
        assert pattern.occurrence_count == 0

    def test_mark_resolved(self, service):
        service.record_failure("s1", "read_file", "No such file")
        service.record_failure("s1", "read_file", "No such file")

        resolved = service.mark_resolved("read_file", "file_not_found")
        assert resolved

        pattern = service.query_similar_failures("read_file", "file_not_found")
        assert pattern.resolved_count == 1
        assert pattern.occurrence_count == 2

    def test_mark_resolved_no_match(self, service):
        resolved = service.mark_resolved("nonexistent", "unknown")
        assert not resolved

    def test_build_failure_context(self, service):
        service.record_failure("s1", "read_file", "No such file")
        service.record_failure("s1", "write_file", "Permission denied")

        ctx = service.build_failure_context(["read_file", "write_file"])
        assert len(ctx.patterns) == 2

    def test_build_failure_context_with_warnings(self, service):
        """3+ failures should generate a warning."""
        for _ in range(3):
            service.record_failure("s1", "read_file", "No such file")

        ctx = service.build_failure_context(["read_file"])
        assert len(ctx.warning_messages) == 1
        assert "read_file" in ctx.warning_messages[0]

    def test_build_failure_context_empty(self, service):
        ctx = service.build_failure_context(["read_file"])
        assert len(ctx.patterns) == 0
        assert ctx.total_penalty == 0.0

    def test_get_failure_summary_for_llm(self, service):
        service.record_failure("s1", "read_file", "No such file")
        ctx = service.build_failure_context(["read_file"])

        summary = service.get_failure_summary_for_llm(ctx)
        assert "[Failure Memory]" in summary
        assert "read_file" in summary
        assert "file_not_found" in summary

    def test_get_failure_summary_empty(self, service):
        ctx = FailureContext()
        summary = service.get_failure_summary_for_llm(ctx)
        assert summary == ""

    def test_error_message_truncated(self, service):
        long_msg = "x" * 1000
        record = service.record_failure("s1", "tool", long_msg)
        assert len(record.error_message) == 500

    def test_build_failure_context_all_tools(self, service):
        """build_failure_context(None) should aggregate all tools."""
        service.record_failure("s1", "read_file", "No such file")
        service.record_failure("s1", "write_file", "Permission denied")

        ctx = service.build_failure_context(None)
        assert len(ctx.patterns) == 2


# ── CognitionService Integration ─────────────────────────────────────


class TestCognitionIntegration:
    """Test that failure context properly adjusts cognition results."""

    @pytest.fixture
    def cognition(self):
        return CognitionService()

    def test_confidence_reduced_by_failure_context(self, cognition):
        """Failure context should reduce confidence."""
        baseline = cognition.analyze_task("list files")

        failure_ctx = FailureContext(
            patterns=[
                FailurePattern(
                    tool_name="list_dir",
                    error_type="permission_denied",
                    occurrence_count=5,
                )
            ]
        )
        with_failures = cognition.analyze_task(
            "list files", failure_context=failure_ctx
        )
        assert with_failures.confidence < baseline.confidence

    def test_failure_warnings_in_risks(self, cognition):
        """Failure warnings should appear in potential_risks."""
        failure_ctx = FailureContext(
            patterns=[],
            warning_messages=["Tool 'read_file' has failed 5 times"],
        )
        result = cognition.analyze_task("list files", failure_context=failure_ctx)
        assert any("read_file" in r for r in result.potential_risks)

    def test_no_failure_context_backward_compat(self, cognition):
        """Calling without failure_context should work unchanged."""
        result = cognition.analyze_task("list files")
        assert result.confidence > 0.8

    def test_empty_failure_context_no_effect(self, cognition):
        """Empty failure context should not change confidence."""
        baseline = cognition.analyze_task("list files")
        with_empty = cognition.analyze_task(
            "list files", failure_context=FailureContext()
        )
        assert abs(baseline.confidence - with_empty.confidence) < 1e-6


# ── FailureMemoryServiceManager ──────────────────────────────────────


class TestFailureMemoryServiceManager:
    """Test the singleton manager."""

    def test_returns_same_instance(self):
        manager = FailureMemoryServiceManager()
        s1 = manager.get_service("session1")
        s2 = manager.get_service("session2")
        assert s1 is s2

    def test_default_session(self):
        manager = FailureMemoryServiceManager()
        s = manager.get_service()
        assert s is not None
