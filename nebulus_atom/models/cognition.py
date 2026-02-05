"""
Data models for the cognition system.

Represents reasoning chains, complexity analysis, and cognitive state.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List
from datetime import datetime


class TaskComplexity(Enum):
    """Classification of task complexity levels."""

    SIMPLE = "simple"  # Single tool, clear intent
    MODERATE = "moderate"  # 2-3 tools, some planning needed
    COMPLEX = "complex"  # Multi-step, dependencies, unclear requirements


@dataclass
class ReasoningStep:
    """A single step in a reasoning chain."""

    step_number: int
    thought: str
    conclusion: str
    confidence: float = 1.0  # 0.0 - 1.0

    def __post_init__(self) -> None:
        """Validate confidence is in valid range."""
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class ClarificationQuestion:
    """A question to clarify ambiguous requirements."""

    question: str
    options: List[str] = field(default_factory=list)
    importance: str = "medium"  # "low" | "medium" | "high"


@dataclass
class CognitionResult:
    """Result of cognitive analysis of a task."""

    task_complexity: TaskComplexity
    reasoning_chain: List[ReasoningStep] = field(default_factory=list)
    recommended_approach: str = ""
    confidence: float = 1.0  # Overall confidence 0.0 - 1.0
    clarification_needed: bool = False
    clarification_questions: List[ClarificationQuestion] = field(default_factory=list)
    estimated_steps: int = 1
    potential_risks: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Validate confidence is in valid range."""
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def should_proceed(self) -> bool:
        """Determine if we should proceed without clarification."""
        return not self.clarification_needed or self.confidence >= 0.7

    @property
    def needs_planning(self) -> bool:
        """Determine if task needs explicit planning phase."""
        return (
            self.task_complexity == TaskComplexity.COMPLEX or self.estimated_steps > 3
        )


@dataclass
class ThoughtRecord:
    """A recorded thought for telemetry/debugging."""

    session_id: str
    thought_type: str  # "analysis" | "reasoning" | "critique" | "verification"
    content: str
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


@dataclass
class SelfCritiqueResult:
    """Result of self-critique analysis."""

    is_valid: bool
    issues_found: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    confidence: float = 1.0
    should_retry: bool = False
