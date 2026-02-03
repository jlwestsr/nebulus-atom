"""
Data models for the failure memory system.

Tracks tool failures, classifies error patterns, and provides
confidence penalty context to the cognition system.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class FailureRecord:
    """A single recorded tool failure event."""

    id: str
    session_id: str
    timestamp: float
    tool_name: str
    error_type: str
    error_message: str
    args_context: dict = field(default_factory=dict)
    recovery_attempted: str = ""
    resolved: bool = False


@dataclass
class FailurePattern:
    """Aggregated failure pattern for a tool+error_type combination."""

    tool_name: str
    error_type: str
    occurrence_count: int
    resolved_count: int = 0

    @property
    def resolution_rate(self) -> float:
        """Fraction of occurrences that were resolved."""
        if self.occurrence_count == 0:
            return 0.0
        return self.resolved_count / self.occurrence_count

    @property
    def confidence_penalty(self) -> float:
        """Calculate confidence penalty for this pattern.

        Base: min(occurrence_count * 0.03, 0.15)
        Discount: resolved failures reduce penalty by 50%
        Hard cap: 0.20 per pattern
        """
        base = min(self.occurrence_count * 0.03, 0.15)
        discount = self.resolution_rate * 0.5
        penalty = base * (1.0 - discount)
        return min(penalty, 0.20)


@dataclass
class FailureContext:
    """Container passed to CognitionService with aggregated failure info."""

    patterns: List[FailurePattern] = field(default_factory=list)
    warning_messages: List[str] = field(default_factory=list)

    @property
    def total_penalty(self) -> float:
        """Total confidence penalty across all patterns, capped at 0.25."""
        raw = sum(p.confidence_penalty for p in self.patterns)
        return min(raw, 0.25)
