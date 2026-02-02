"""Skill schema definitions."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SkillTriggers:
    """Triggers that determine when a skill applies."""

    keywords: List[str] = field(default_factory=list)
    file_patterns: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)


@dataclass
class SkillExample:
    """Example usage of a skill."""

    input: str
    approach: str


@dataclass
class Skill:
    """A skill definition."""

    name: str
    description: str
    instructions: str
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    triggers: SkillTriggers = field(default_factory=SkillTriggers)
    examples: List[SkillExample] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "tags": self.tags,
            "triggers": {
                "keywords": self.triggers.keywords,
                "file_patterns": self.triggers.file_patterns,
                "labels": self.triggers.labels,
            },
            "instructions": self.instructions,
            "examples": [
                {"input": ex.input, "approach": ex.approach} for ex in self.examples
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        """Create from dictionary."""
        triggers_data = data.get("triggers", {})
        triggers = SkillTriggers(
            keywords=triggers_data.get("keywords", []),
            file_patterns=triggers_data.get("file_patterns", []),
            labels=triggers_data.get("labels", []),
        )

        examples_data = data.get("examples", [])
        examples = [
            SkillExample(input=ex.get("input", ""), approach=ex.get("approach", ""))
            for ex in examples_data
        ]

        return cls(
            name=data.get("name", "unknown"),
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            version=data.get("version", "1.0.0"),
            tags=data.get("tags", []),
            triggers=triggers,
            examples=examples,
        )

    def matches_issue(
        self,
        title: str,
        body: str,
        labels: List[str],
        files: Optional[List[str]] = None,
    ) -> bool:
        """Check if this skill matches an issue.

        Args:
            title: Issue title.
            body: Issue body.
            labels: Issue labels.
            files: Optional list of files in the PR/issue.

        Returns:
            True if skill matches the issue.
        """
        text = f"{title} {body}".lower()

        # Check keywords
        for keyword in self.triggers.keywords:
            if keyword.lower() in text:
                return True

        # Check labels
        for label in self.triggers.labels:
            if label in labels:
                return True

        # Check file patterns (if files provided)
        if files and self.triggers.file_patterns:
            import fnmatch

            for pattern in self.triggers.file_patterns:
                for file in files:
                    if fnmatch.fnmatch(file, pattern):
                        return True

        return False
