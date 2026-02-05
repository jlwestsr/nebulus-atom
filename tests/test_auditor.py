"""Tests for the small-model auditor."""

from nebulus_swarm.overlord.auditor import (
    Auditor,
    AuditorConfig,
    AuditIssue,
    AuditResult,
    AuditSeverity,
)


class TestAuditorConfig:
    def test_default_disabled(self):
        config = AuditorConfig()
        assert config.enabled is False
        assert config.strict is False
        assert config.model is None

    def test_from_env_disabled(self, monkeypatch):
        monkeypatch.delenv("ATOM_AUDITOR_ENABLED", raising=False)
        config = AuditorConfig.from_env()
        assert config.enabled is False

    def test_from_env_enabled(self, monkeypatch):
        monkeypatch.setenv("ATOM_AUDITOR_ENABLED", "true")
        monkeypatch.setenv("ATOM_AUDITOR_MODEL", "small-model")
        monkeypatch.setenv("ATOM_AUDITOR_STRICT", "true")
        config = AuditorConfig.from_env()
        assert config.enabled is True
        assert config.model == "small-model"
        assert config.strict is True


class TestAuditResult:
    def test_passed_result(self):
        result = AuditResult(passed=True)
        assert result.passed is True
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_failed_result_with_issues(self):
        result = AuditResult(
            passed=False,
            issues=[
                AuditIssue(check="test", severity=AuditSeverity.ERROR, message="error"),
                AuditIssue(
                    check="test", severity=AuditSeverity.WARNING, message="warn"
                ),
                AuditIssue(
                    check="test", severity=AuditSeverity.WARNING, message="warn2"
                ),
            ],
        )
        assert result.error_count == 1
        assert result.warning_count == 2


class TestAuditorDisabled:
    def test_disabled_always_passes(self):
        config = AuditorConfig(enabled=False)
        auditor = Auditor(config)
        result = auditor.audit("invalid python {{{{", content_type="python")
        assert result.passed is True
        assert result.issues == []

    def test_enabled_property(self):
        auditor = Auditor(AuditorConfig(enabled=False))
        assert auditor.enabled is False
        auditor = Auditor(AuditorConfig(enabled=True))
        assert auditor.enabled is True


class TestPythonSyntaxCheck:
    def test_valid_python_passes(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        result = auditor.audit("def foo():\n    return 42", content_type="python")
        assert result.passed is True

    def test_invalid_python_fails(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        result = auditor.audit("def foo(\n    return", content_type="python")
        assert result.passed is False
        assert result.error_count == 1
        assert "syntax" in result.issues[0].message.lower()


class TestJSONSyntaxCheck:
    def test_valid_json_passes(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        result = auditor.audit('{"key": "value"}', content_type="json")
        assert result.passed is True

    def test_invalid_json_fails(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        result = auditor.audit('{"key": }', content_type="json")
        assert result.passed is False
        assert result.error_count == 1


class TestJSONSchemaCheck:
    def test_missing_required_field(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        schema = {"required": ["name", "age"]}
        result = auditor.audit('{"name": "test"}', content_type="json", schema=schema)
        assert result.passed is False
        assert any("age" in i.message for i in result.issues)

    def test_all_required_fields_present(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        schema = {"required": ["name"]}
        result = auditor.audit('{"name": "test"}', content_type="json", schema=schema)
        assert result.passed is True

    def test_type_mismatch_warning(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        schema = {"properties": {"age": {"type": "integer"}}}
        result = auditor.audit('{"age": "twenty"}', content_type="json", schema=schema)
        assert result.warning_count >= 1


class TestSafetyPatterns:
    def test_os_system_detected(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        result = auditor.audit('os.system("ls")', content_type="python")
        assert result.warning_count >= 1
        assert any("os.system" in i.message for i in result.issues)

    def test_dangerous_pattern_detected(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        dangerous_code = "result = ev" + "al(user_input)"
        result = auditor.audit(dangerous_code, content_type="python")
        assert result.warning_count >= 1

    def test_safe_code_no_warnings(self):
        config = AuditorConfig(enabled=True)
        auditor = Auditor(config)
        result = auditor.audit(
            "def add(a, b):\n    return a + b", content_type="python"
        )
        assert result.warning_count == 0


class TestStrictMode:
    def test_strict_promotes_warnings_to_errors(self):
        config = AuditorConfig(enabled=True, strict=True)
        auditor = Auditor(config)
        dangerous_code = "ev" + 'al("1+1")'
        result = auditor.audit(dangerous_code, content_type="python")
        assert result.passed is False
        assert result.error_count >= 1

    def test_non_strict_warnings_pass(self):
        config = AuditorConfig(enabled=True, strict=False)
        auditor = Auditor(config)
        dangerous_code = "ev" + 'al("1+1")'
        result = auditor.audit(dangerous_code, content_type="python")
        assert result.passed is True
        assert result.warning_count >= 1


class TestLLMCheck:
    def test_llm_check_skipped_when_no_model(self):
        config = AuditorConfig(enabled=True, model=None)
        auditor = Auditor(config)
        result = auditor.audit("print('hello')", content_type="python")
        assert result.confidence == 1.0

    def test_llm_check_lowers_confidence(self):
        config = AuditorConfig(enabled=True, model="test-model")
        auditor = Auditor(config)
        result = auditor.audit("print('hello')", content_type="python")
        assert result.confidence <= 1.0
