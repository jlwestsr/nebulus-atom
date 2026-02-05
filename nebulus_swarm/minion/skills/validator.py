"""Skill validator for security and schema validation."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from nebulus_swarm.minion.skills.schema import Skill

logger = logging.getLogger(__name__)


# Forbidden patterns in skill instructions
FORBIDDEN_PATTERNS = [
    # Destructive commands
    (r"rm\s+-rf", "Destructive rm -rf command"),
    (r"rm\s+-r\s+/", "Recursive delete from root"),
    # Remote code execution
    (r"curl.*\|\s*(?:ba)?sh", "Piping curl to shell"),
    (r"wget.*\|\s*(?:ba)?sh", "Piping wget to shell"),
    # System files
    (r"/etc/passwd", "Access to /etc/passwd"),
    (r"/etc/shadow", "Access to /etc/shadow"),
    (r"~/.ssh", "Access to SSH directory"),
    (r"\.ssh/", "Access to SSH directory"),
    # Token/credential exfiltration
    (r"GITHUB_TOKEN", "Reference to GITHUB_TOKEN"),
    (r"API_KEY", "Reference to API_KEY"),
    (r"SECRET", "Reference to SECRET"),
    (r"PASSWORD", "Reference to PASSWORD"),
    # Network exfiltration
    (r"curl\s+.*\$", "Curl with variable (potential exfiltration)"),
    (r"wget\s+.*\$", "Wget with variable (potential exfiltration)"),
    # Privilege escalation
    (r"sudo\s+", "Use of sudo"),
    (r"chmod\s+777", "Setting world-writable permissions"),
    (r"chown\s+root", "Changing ownership to root"),
]


@dataclass
class ValidationResult:
    """Result of skill validation."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    security_flags: List[str] = field(default_factory=list)

    @property
    def has_security_issues(self) -> bool:
        """Check if there are security issues."""
        return len(self.security_flags) > 0

    def add_error(self, message: str) -> None:
        """Add an error."""
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning."""
        self.warnings.append(message)

    def add_security_flag(self, message: str) -> None:
        """Add a security flag."""
        self.security_flags.append(message)
        self.valid = False


class SkillValidator:
    """Validates skills for security and schema compliance."""

    # Maximum instruction length
    MAX_INSTRUCTION_LENGTH = 5000

    # Required fields
    REQUIRED_FIELDS = ["name", "description", "instructions"]

    def __init__(self, forbidden_patterns: Optional[List[tuple]] = None):
        """Initialize validator.

        Args:
            forbidden_patterns: Optional custom forbidden patterns.
        """
        self.forbidden_patterns = forbidden_patterns or FORBIDDEN_PATTERNS
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), desc)
            for pattern, desc in self.forbidden_patterns
        ]

    def validate_file(self, path: Path) -> ValidationResult:
        """Validate a skill file.

        Args:
            path: Path to skill YAML file.

        Returns:
            ValidationResult with any issues found.
        """
        result = ValidationResult(valid=True)

        # Check file exists
        if not path.exists():
            result.add_error(f"File not found: {path}")
            return result

        # Parse YAML
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.add_error(f"Invalid YAML: {e}")
            return result

        if not data or not isinstance(data, dict):
            result.add_error("File is empty or not a valid skill definition")
            return result

        # Validate schema
        self._validate_schema(data, result)

        # Validate security
        if "instructions" in data:
            self._validate_security(data["instructions"], result)

        return result

    def validate_skill(self, skill: Skill) -> ValidationResult:
        """Validate a Skill object.

        Args:
            skill: Skill to validate.

        Returns:
            ValidationResult with any issues found.
        """
        result = ValidationResult(valid=True)

        # Validate required fields
        if not skill.name:
            result.add_error("Skill name is required")
        if not skill.description:
            result.add_error("Skill description is required")
        if not skill.instructions:
            result.add_error("Skill instructions are required")

        # Validate instruction length
        if len(skill.instructions) > self.MAX_INSTRUCTION_LENGTH:
            result.add_warning(
                f"Instructions exceed {self.MAX_INSTRUCTION_LENGTH} characters"
            )

        # Validate triggers
        if not skill.triggers.keywords and not skill.triggers.labels:
            result.add_warning("Skill has no triggers (keywords or labels)")

        # Validate security
        self._validate_security(skill.instructions, result)

        return result

    def _validate_schema(self, data: dict, result: ValidationResult) -> None:
        """Validate skill schema.

        Args:
            data: Skill data dictionary.
            result: ValidationResult to update.
        """
        # Check required fields
        for field_name in self.REQUIRED_FIELDS:
            if field_name not in data or not data[field_name]:
                result.add_error(f"Required field missing: {field_name}")

        # Validate name format
        if "name" in data:
            name = data["name"]
            if not re.match(r"^[a-z][a-z0-9-]*$", name):
                result.add_error(
                    f"Invalid skill name format: {name} "
                    "(must be lowercase, start with letter, only contain a-z, 0-9, -)"
                )

        # Validate version format
        if "version" in data:
            version = data["version"]
            if not re.match(r"^\d+\.\d+\.\d+$", str(version)):
                result.add_warning(
                    f"Invalid version format: {version} (expected X.Y.Z)"
                )

        # Validate triggers structure
        if "triggers" in data and isinstance(data["triggers"], dict):
            triggers = data["triggers"]
            for key in triggers:
                if key not in ["keywords", "file_patterns", "labels"]:
                    result.add_warning(f"Unknown trigger type: {key}")

        # Validate instruction length
        if "instructions" in data:
            if len(data["instructions"]) > self.MAX_INSTRUCTION_LENGTH:
                result.add_warning(
                    f"Instructions exceed {self.MAX_INSTRUCTION_LENGTH} characters"
                )

    def _validate_security(self, instructions: str, result: ValidationResult) -> None:
        """Check for forbidden patterns in instructions.

        Args:
            instructions: Instruction text to check.
            result: ValidationResult to update.
        """
        for pattern, description in self._compiled_patterns:
            if pattern.search(instructions):
                result.add_security_flag(f"Forbidden pattern: {description}")


def is_skill_change(changed_files: List[str]) -> bool:
    """Check if any changed files are in the skills directory.

    Args:
        changed_files: List of changed file paths.

    Returns:
        True if any skill files were changed.
    """
    for file in changed_files:
        if file.startswith(".nebulus/skills/"):
            return True
    return False


def validate_skill_changes(
    changed_files: List[str], workspace: Path
) -> List[ValidationResult]:
    """Validate all changed skill files.

    Args:
        changed_files: List of changed file paths.
        workspace: Path to workspace root.

    Returns:
        List of validation results for skill files.
    """
    validator = SkillValidator()
    results = []

    for file in changed_files:
        if file.startswith(".nebulus/skills/") and file.endswith((".yaml", ".yml")):
            # Skip index file
            if file.endswith("_index.yaml"):
                continue

            path = workspace / file
            result = validator.validate_file(path)
            result.errors.insert(0, f"File: {file}")  # Add file context
            results.append(result)

    return results
