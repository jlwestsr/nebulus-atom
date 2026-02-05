"""Small-model auditor for structural validation of worker output.

Validates worker output against schema, syntax, and safety constraints
before reaching the Evaluator. Optional — disabled by default.
"""

import ast
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditSeverity(Enum):
    """Severity of an audit issue."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class AuditIssue:
    """A single issue found during audit."""

    check: str
    severity: AuditSeverity
    message: str
    location: Optional[str] = None


@dataclass
class AuditResult:
    """Result of auditing worker output."""

    passed: bool
    issues: List[AuditIssue] = field(default_factory=list)
    confidence: float = 1.0  # 0.0-1.0, lower if heuristics uncertain
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == AuditSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == AuditSeverity.WARNING)


@dataclass
class AuditorConfig:
    """Configuration for the auditor."""

    enabled: bool = False
    model: Optional[str] = None  # If set, use LLM for additional checks
    strict: bool = False  # If True, warnings become errors
    llm_base_url: Optional[str] = None
    llm_timeout: int = 30

    @classmethod
    def from_env(cls) -> "AuditorConfig":
        """Load config from environment variables."""
        return cls(
            enabled=os.environ.get("ATOM_AUDITOR_ENABLED", "false").lower() == "true",
            model=os.environ.get("ATOM_AUDITOR_MODEL"),
            strict=os.environ.get("ATOM_AUDITOR_STRICT", "false").lower() == "true",
            llm_base_url=os.environ.get(
                "ATOM_LLM_BASE_URL", "http://localhost:5000/v1"
            ),
            llm_timeout=int(os.environ.get("ATOM_AUDITOR_TIMEOUT", "30")),
        )


class Auditor:
    """Validates worker output using heuristic and optional LLM checks.

    The auditor runs BEFORE the Evaluator. It performs structural validation:
    - JSON schema validation
    - Python syntax validation (AST parsing)
    - Safety pattern detection (dangerous operations)
    - Optional LLM-based semantic review

    When disabled (default), all validation is skipped.
    """

    # Patterns that indicate potentially dangerous operations
    SAFETY_PATTERNS = [
        (r"\bos\.system\s*\(", "os.system() call detected"),
        (r"\bsubprocess\.call\s*\(.*shell\s*=\s*True", "subprocess with shell=True"),
        (r"\beval\s*\(", "eval() call detected"),
        (r"\bexec\s*\(", "exec() call detected"),
        (r"\b__import__\s*\(", "dynamic import detected"),
        (r"rm\s+-rf\s+/", "dangerous rm command"),
    ]

    def __init__(self, config: Optional[AuditorConfig] = None):
        """Initialize auditor.

        Args:
            config: Auditor configuration. If None, loads from environment.
        """
        self.config = config or AuditorConfig.from_env()

    @property
    def enabled(self) -> bool:
        """Check if auditor is enabled."""
        return self.config.enabled

    def audit(
        self,
        content: str,
        content_type: str = "text",
        schema: Optional[Dict[str, Any]] = None,
    ) -> AuditResult:
        """Audit worker output.

        Args:
            content: The content to audit (code, JSON, text).
            content_type: Type of content ("python", "json", "text").
            schema: Optional JSON schema to validate against.

        Returns:
            AuditResult with pass/fail status and any issues found.
        """
        if not self.config.enabled:
            return AuditResult(passed=True, confidence=1.0)

        issues: List[AuditIssue] = []

        # Run heuristic checks based on content type
        if content_type == "python":
            issues.extend(self._check_python_syntax(content))
            issues.extend(self._check_safety_patterns(content))
        elif content_type == "json":
            issues.extend(self._check_json_syntax(content))
            if schema:
                issues.extend(self._check_json_schema(content, schema))
        else:
            issues.extend(self._check_safety_patterns(content))

        # Optional LLM check
        if self.config.model:
            llm_issues = self._run_llm_check(content, content_type)
            issues.extend(llm_issues)

        # Apply strict mode
        if self.config.strict:
            for issue in issues:
                if issue.severity == AuditSeverity.WARNING:
                    issue.severity = AuditSeverity.ERROR

        # Determine pass/fail
        has_errors = any(i.severity == AuditSeverity.ERROR for i in issues)
        confidence = 1.0 if not self.config.model else 0.8  # Lower confidence with LLM

        return AuditResult(
            passed=not has_errors,
            issues=issues,
            confidence=confidence,
        )

    def _check_python_syntax(self, code: str) -> List[AuditIssue]:
        """Check Python code for syntax errors."""
        issues = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            issues.append(
                AuditIssue(
                    check="python_syntax",
                    severity=AuditSeverity.ERROR,
                    message=f"Syntax error: {e.msg}",
                    location=f"line {e.lineno}" if e.lineno else None,
                )
            )
        return issues

    def _check_json_syntax(self, content: str) -> List[AuditIssue]:
        """Check JSON for syntax errors."""
        issues = []
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            issues.append(
                AuditIssue(
                    check="json_syntax",
                    severity=AuditSeverity.ERROR,
                    message=f"JSON syntax error: {e.msg}",
                    location=f"line {e.lineno}, col {e.colno}",
                )
            )
        return issues

    def _check_json_schema(
        self, content: str, schema: Dict[str, Any]
    ) -> List[AuditIssue]:
        """Validate JSON against a schema (basic validation)."""
        issues = []
        try:
            data = json.loads(content)
            # Basic type checking for required fields
            if "required" in schema:
                for field in schema["required"]:
                    if field not in data:
                        issues.append(
                            AuditIssue(
                                check="json_schema",
                                severity=AuditSeverity.ERROR,
                                message=f"Missing required field: {field}",
                            )
                        )
            # Type checking for properties
            if "properties" in schema:
                for prop, prop_schema in schema["properties"].items():
                    if prop in data and "type" in prop_schema:
                        expected_type = prop_schema["type"]
                        actual_type = type(data[prop]).__name__
                        type_map = {
                            "string": "str",
                            "integer": "int",
                            "number": ("int", "float"),
                            "boolean": "bool",
                            "array": "list",
                            "object": "dict",
                        }
                        expected = type_map.get(expected_type, expected_type)
                        if isinstance(expected, tuple):
                            if actual_type not in expected:
                                issues.append(
                                    AuditIssue(
                                        check="json_schema",
                                        severity=AuditSeverity.WARNING,
                                        message=f"Field '{prop}' has type {actual_type}, expected {expected_type}",
                                    )
                                )
                        elif actual_type != expected:
                            issues.append(
                                AuditIssue(
                                    check="json_schema",
                                    severity=AuditSeverity.WARNING,
                                    message=f"Field '{prop}' has type {actual_type}, expected {expected_type}",
                                )
                            )
        except json.JSONDecodeError:
            pass  # Already caught by syntax check
        return issues

    def _check_safety_patterns(self, content: str) -> List[AuditIssue]:
        """Check for dangerous patterns in content."""
        issues = []
        for pattern, message in self.SAFETY_PATTERNS:
            if re.search(pattern, content):
                issues.append(
                    AuditIssue(
                        check="safety_pattern",
                        severity=AuditSeverity.WARNING,
                        message=message,
                    )
                )
        return issues

    def _run_llm_check(self, content: str, content_type: str) -> List[AuditIssue]:
        """Run optional LLM-based semantic check."""
        issues = []
        if not self.config.model or not self.config.llm_base_url:
            return issues

        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=self.config.llm_base_url,
                api_key="not-needed",
                timeout=self.config.llm_timeout,
            )

            prompt = f"""Review this {content_type} content for issues:

{content[:2000]}  # Truncate for token limits

Report any:
1. Logic errors or bugs
2. Security vulnerabilities
3. Missing error handling
4. Code quality issues

Respond with JSON: {{"issues": [{{"severity": "warning|error", "message": "description"}}]}}
If no issues, respond: {{"issues": []}}"""

            response = client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )

            result_text = response.choices[0].message.content or "{}"
            # Try to parse JSON from response
            try:
                # Handle markdown code blocks
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0]
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0]

                result = json.loads(result_text.strip())
                for issue in result.get("issues", []):
                    severity = AuditSeverity.WARNING
                    if issue.get("severity", "").lower() == "error":
                        severity = AuditSeverity.ERROR
                    issues.append(
                        AuditIssue(
                            check="llm_review",
                            severity=severity,
                            message=issue.get("message", "LLM-detected issue"),
                        )
                    )
            except json.JSONDecodeError:
                logger.debug("Could not parse LLM response as JSON")

        except Exception as e:
            logger.warning(f"LLM audit check failed: {e}")

        return issues
