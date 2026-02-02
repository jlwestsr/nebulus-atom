"""Automated checks runner for PR review."""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """Status of an automated check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    """Result of a single check."""

    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None
    file_issues: List[str] = field(default_factory=list)


@dataclass
class ChecksReport:
    """Complete report of all automated checks."""

    results: List[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """Check if all checks passed (warnings allowed)."""
        return all(
            r.status in (CheckStatus.PASSED, CheckStatus.WARNING, CheckStatus.SKIPPED)
            for r in self.results
        )

    @property
    def has_failures(self) -> bool:
        """Check if any checks failed."""
        return any(r.status == CheckStatus.FAILED for r in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.PASSED)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.FAILED)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.WARNING)

    def get_summary(self) -> str:
        """Get a summary of all checks."""
        lines = ["## Automated Checks Report", ""]

        status_emoji = {
            CheckStatus.PASSED: "✅",
            CheckStatus.FAILED: "❌",
            CheckStatus.WARNING: "⚠️",
            CheckStatus.SKIPPED: "⏭️",
        }

        for result in self.results:
            emoji = status_emoji.get(result.status, "❓")
            lines.append(f"- {emoji} **{result.name}**: {result.message}")

            if result.file_issues:
                for issue in result.file_issues[:5]:  # Limit to 5 issues
                    lines.append(f"  - {issue}")
                if len(result.file_issues) > 5:
                    lines.append(f"  - ... and {len(result.file_issues) - 5} more")

        lines.append("")
        lines.append(
            f"**Summary:** {self.passed_count} passed, "
            f"{self.failed_count} failed, {self.warning_count} warnings"
        )

        return "\n".join(lines)


class CheckRunner:
    """Runs automated checks on a repository."""

    # Security patterns to flag
    SECURITY_PATTERNS = [
        (r"eval\s*\(", "Use of eval() is dangerous"),
        (r"exec\s*\(", "Use of exec() is dangerous"),
        (r"subprocess\.call\s*\([^)]*shell\s*=\s*True", "shell=True is risky"),
        (r"os\.system\s*\(", "os.system() is dangerous, use subprocess"),
        (r"pickle\.loads?\s*\(", "pickle can execute arbitrary code"),
        (r"__import__\s*\(", "Dynamic imports can be dangerous"),
        (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password detected"),
        (r"api_key\s*=\s*['\"][^'\"]+['\"]", "Hardcoded API key detected"),
        (r"secret\s*=\s*['\"][^'\"]+['\"]", "Hardcoded secret detected"),
        (r"BEGIN\s+(RSA|DSA|EC)\s+PRIVATE\s+KEY", "Private key in code"),
    ]

    def __init__(self, repo_path: str):
        """Initialize check runner.

        Args:
            repo_path: Path to the repository root.
        """
        self.repo_path = Path(repo_path)

    def run_all_checks(self, changed_files: List[str]) -> ChecksReport:
        """Run all automated checks.

        Args:
            changed_files: List of changed file paths.

        Returns:
            ChecksReport with all results.
        """
        report = ChecksReport()

        # Filter to Python files
        python_files = [f for f in changed_files if f.endswith(".py")]

        # Run checks
        report.results.append(self.check_pytest())
        report.results.append(self.check_ruff(python_files))
        report.results.append(self.check_security_patterns(python_files))
        report.results.append(self.check_complexity(python_files))
        report.results.append(self.check_file_sizes(changed_files))

        return report

    def check_pytest(self) -> CheckResult:
        """Run pytest and check for failures."""
        try:
            # Use subprocess.run with list args (no shell injection)
            result = subprocess.run(
                ["python3", "-m", "pytest", "--tb=no", "-q"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                # Parse passed count from output
                match = re.search(r"(\d+) passed", result.stdout)
                passed = match.group(1) if match else "all"
                return CheckResult(
                    name="Tests (pytest)",
                    status=CheckStatus.PASSED,
                    message=f"{passed} tests passed",
                )
            elif result.returncode == 5:
                # No tests collected
                return CheckResult(
                    name="Tests (pytest)",
                    status=CheckStatus.SKIPPED,
                    message="No tests found",
                )
            else:
                # Parse failure info
                failed_match = re.search(r"(\d+) failed", result.stdout)
                failed = failed_match.group(1) if failed_match else "some"
                return CheckResult(
                    name="Tests (pytest)",
                    status=CheckStatus.FAILED,
                    message=f"{failed} tests failed",
                    details=result.stdout[-500:] if result.stdout else None,
                )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name="Tests (pytest)",
                status=CheckStatus.FAILED,
                message="Tests timed out (>5 minutes)",
            )
        except FileNotFoundError:
            return CheckResult(
                name="Tests (pytest)",
                status=CheckStatus.SKIPPED,
                message="pytest not available",
            )
        except Exception as e:
            return CheckResult(
                name="Tests (pytest)",
                status=CheckStatus.FAILED,
                message=f"Error running tests: {e}",
            )

    def check_ruff(self, python_files: List[str]) -> CheckResult:
        """Run ruff linter on changed files."""
        if not python_files:
            return CheckResult(
                name="Linting (ruff)",
                status=CheckStatus.SKIPPED,
                message="No Python files changed",
            )

        try:
            # Use subprocess.run with list args (no shell injection)
            result = subprocess.run(
                ["ruff", "check", "--output-format=text"] + python_files,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return CheckResult(
                    name="Linting (ruff)",
                    status=CheckStatus.PASSED,
                    message="No linting issues",
                )
            else:
                # Parse issues
                issues = []
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        issues.append(line.strip())

                return CheckResult(
                    name="Linting (ruff)",
                    status=CheckStatus.WARNING,
                    message=f"{len(issues)} linting issues",
                    file_issues=issues[:10],
                )

        except FileNotFoundError:
            return CheckResult(
                name="Linting (ruff)",
                status=CheckStatus.SKIPPED,
                message="ruff not available",
            )
        except Exception as e:
            return CheckResult(
                name="Linting (ruff)",
                status=CheckStatus.FAILED,
                message=f"Error running ruff: {e}",
            )

    def check_security_patterns(self, python_files: List[str]) -> CheckResult:
        """Check for security anti-patterns."""
        if not python_files:
            return CheckResult(
                name="Security Patterns",
                status=CheckStatus.SKIPPED,
                message="No Python files changed",
            )

        issues = []

        for filepath in python_files:
            full_path = self.repo_path / filepath
            if not full_path.exists():
                continue

            try:
                content = full_path.read_text()
                for pattern, description in self.SECURITY_PATTERNS:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Find line number
                        line_num = content[: match.start()].count("\n") + 1
                        issues.append(f"{filepath}:{line_num}: {description}")
            except Exception as e:
                logger.warning(f"Error checking {filepath}: {e}")

        if not issues:
            return CheckResult(
                name="Security Patterns",
                status=CheckStatus.PASSED,
                message="No security issues detected",
            )
        else:
            return CheckResult(
                name="Security Patterns",
                status=CheckStatus.WARNING,
                message=f"{len(issues)} potential security issues",
                file_issues=issues,
            )

    def check_complexity(self, python_files: List[str]) -> CheckResult:
        """Check code complexity using radon (if available)."""
        if not python_files:
            return CheckResult(
                name="Complexity",
                status=CheckStatus.SKIPPED,
                message="No Python files changed",
            )

        try:
            # Use subprocess.run with list args (no shell injection)
            result = subprocess.run(
                ["radon", "cc", "-s", "-a"] + python_files,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return CheckResult(
                    name="Complexity",
                    status=CheckStatus.SKIPPED,
                    message="Complexity check failed",
                )

            # Parse average complexity
            match = re.search(
                r"Average complexity:\s*([A-F])\s*\((\d+\.\d+)\)", result.stdout
            )
            if match:
                grade, score = match.groups()
                if grade in ("A", "B"):
                    return CheckResult(
                        name="Complexity",
                        status=CheckStatus.PASSED,
                        message=f"Average complexity: {grade} ({score})",
                    )
                elif grade == "C":
                    return CheckResult(
                        name="Complexity",
                        status=CheckStatus.WARNING,
                        message=f"Moderate complexity: {grade} ({score})",
                    )
                else:
                    return CheckResult(
                        name="Complexity",
                        status=CheckStatus.WARNING,
                        message=f"High complexity: {grade} ({score})",
                    )

            return CheckResult(
                name="Complexity",
                status=CheckStatus.PASSED,
                message="Complexity within limits",
            )

        except FileNotFoundError:
            return CheckResult(
                name="Complexity",
                status=CheckStatus.SKIPPED,
                message="radon not available",
            )
        except Exception as e:
            return CheckResult(
                name="Complexity",
                status=CheckStatus.SKIPPED,
                message=f"Could not check complexity: {e}",
            )

    def check_file_sizes(self, changed_files: List[str]) -> CheckResult:
        """Check for overly large files."""
        MAX_FILE_SIZE = 500 * 1024  # 500 KB
        MAX_LINE_COUNT = 1000

        issues = []

        for filepath in changed_files:
            full_path = self.repo_path / filepath
            if not full_path.exists():
                continue

            try:
                # Check file size
                size = full_path.stat().st_size
                if size > MAX_FILE_SIZE:
                    issues.append(
                        f"{filepath}: {size // 1024}KB (>{MAX_FILE_SIZE // 1024}KB limit)"
                    )
                    continue

                # Check line count for text files
                if filepath.endswith((".py", ".js", ".ts", ".tsx", ".jsx")):
                    content = full_path.read_text()
                    line_count = content.count("\n")
                    if line_count > MAX_LINE_COUNT:
                        issues.append(
                            f"{filepath}: {line_count} lines (>{MAX_LINE_COUNT} limit)"
                        )

            except Exception as e:
                logger.warning(f"Error checking {filepath}: {e}")

        if not issues:
            return CheckResult(
                name="File Sizes",
                status=CheckStatus.PASSED,
                message="All files within size limits",
            )
        else:
            return CheckResult(
                name="File Sizes",
                status=CheckStatus.WARNING,
                message=f"{len(issues)} large files",
                file_issues=issues,
            )
