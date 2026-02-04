"""Tests for ErrorRecoveryService and ErrorRecoveryServiceManager."""

import pytest

from nebulus_atom.services.error_recovery_service import (
    ErrorRecoveryService,
    ErrorRecoveryServiceManager,
)


# ── Error Pattern Matching ───────────────────────────────────────────


class TestErrorPatternMatching:
    """Test each regex pattern triggers the correct recovery hint."""

    @pytest.fixture
    def service(self):
        return ErrorRecoveryService()

    def test_file_not_found(self, service):
        result = service.analyze_error("read_file", "No such file or directory")
        assert "does not exist" in result

    def test_missing_module(self, service):
        result = service.analyze_error("run_python", "No module named 'foo'")
        assert "module is missing" in result

    def test_invalid_json(self, service):
        result = service.analyze_error("parse", "Expecting value: line 1")
        assert "invalid JSON" in result

    def test_syntax_error(self, service):
        result = service.analyze_error("run_python", "invalid syntax")
        assert "syntax error" in result

    def test_not_a_directory(self, service):
        result = service.analyze_error("list_dir", "/foo is not a directory")
        assert "treated a file like a directory" in result

    def test_permission_denied(self, service):
        result = service.analyze_error("write_file", "Permission denied")
        assert "do not have permission" in result

    def test_command_failed(self, service):
        result = service.analyze_error("run_shell", "non-zero exit code 1")
        assert "command failed" in result.lower()

    def test_case_insensitive_matching(self, service):
        result = service.analyze_error("read_file", "FILE NOT FOUND")
        assert "does not exist" in result

    def test_unknown_error_gets_generic_hint(self, service):
        result = service.analyze_error("tool", "something completely random")
        assert "try a different approach" in result


# ── Output Format ────────────────────────────────────────────────────


class TestOutputFormat:
    """Verify the structure of the returned analysis string."""

    @pytest.fixture
    def service(self):
        return ErrorRecoveryService()

    def test_contains_tool_name(self, service):
        result = service.analyze_error("my_tool", "No such file")
        assert "my_tool" in result

    def test_contains_error_message(self, service):
        result = service.analyze_error("tool", "specific error text here")
        assert "specific error text here" in result

    def test_contains_recovery_hint_marker(self, service):
        result = service.analyze_error("tool", "No such file")
        assert "Recovery Hint" in result

    def test_contains_action_required_marker(self, service):
        result = service.analyze_error("tool", "No such file")
        assert "Action Required" in result

    def test_matched_hint_text_is_specific(self, service):
        """A matched pattern should produce a different hint than the generic fallback."""
        matched = service.analyze_error("tool", "No such file")
        # The matched hint should NOT contain the generic fallback text
        assert "try a different approach" not in matched


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Test boundary and degenerate inputs."""

    @pytest.fixture
    def service(self):
        return ErrorRecoveryService()

    def test_empty_error_message(self, service):
        result = service.analyze_error("tool", "")
        assert "Recovery Hint" in result
        assert "try a different approach" in result

    def test_empty_tool_name(self, service):
        result = service.analyze_error("", "No such file")
        assert "Recovery Hint" in result

    def test_none_args(self, service):
        result = service.analyze_error("tool", "No such file", args=None)
        assert "Recovery Hint" in result

    def test_multiline_error_message(self, service):
        msg = "Traceback (most recent call last):\n  File 'x.py'\nNo such file"
        result = service.analyze_error("tool", msg)
        assert "does not exist" in result

    def test_first_pattern_wins_on_multi_match(self, service):
        """An error matching both 'File not found' and 'Permission denied'
        should return the hint for 'File not found' (first in pattern list)."""
        msg = "No such file and Permission denied"
        result = service.analyze_error("tool", msg)
        assert "does not exist" in result
        assert "do not have permission" not in result


# ── Real-World Error Strings ─────────────────────────────────────────


class TestRealWorldErrors:
    """Test with realistic exception strings from Python and shell."""

    @pytest.fixture
    def service(self):
        return ErrorRecoveryService()

    def test_python_file_not_found_exception(self, service):
        msg = "[Errno 2] No such file or directory: '/foo/bar.txt'"
        result = service.analyze_error("read_file", msg)
        assert "does not exist" in result

    def test_python_json_decode_error(self, service):
        msg = "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)"
        result = service.analyze_error("parse_json", msg)
        assert "invalid JSON" in result

    def test_shell_exit_code(self, service):
        msg = "Command 'gcc main.c -o main' returned non-zero exit code 1"
        result = service.analyze_error("run_shell", msg)
        assert "command failed" in result.lower()

    def test_python_permission_error(self, service):
        msg = "[Errno 13] Permission denied: '/etc/shadow'"
        result = service.analyze_error("write_file", msg)
        assert "do not have permission" in result


# ── ErrorRecoveryServiceManager ──────────────────────────────────────


class TestErrorRecoveryServiceManager:
    """Test the singleton manager."""

    def test_same_instance_all_sessions(self):
        manager = ErrorRecoveryServiceManager()
        s1 = manager.get_service("session_a")
        s2 = manager.get_service("session_b")
        assert s1 is s2

    def test_default_session(self):
        manager = ErrorRecoveryServiceManager()
        s = manager.get_service()
        assert s is not None

    def test_service_is_error_recovery_service(self):
        manager = ErrorRecoveryServiceManager()
        s = manager.get_service()
        assert isinstance(s, ErrorRecoveryService)
