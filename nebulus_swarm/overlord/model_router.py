"""Multi-LLM model router for complexity-based model selection."""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from nebulus_swarm.config import ModelProfile, RoutingConfig

logger = logging.getLogger(__name__)


@dataclass
class ComplexityScore:
    """Result of issue complexity analysis."""

    score: int
    tier: str
    reasons: list[str]


# Label hints that suggest simple or complex issues
SIMPLE_LABELS = {"typo", "docs", "documentation", "good-first-issue", "easy", "minor"}
COMPLEX_LABELS = {
    "refactor",
    "architecture",
    "performance",
    "security",
    "breaking-change",
    "multi-file",
}


class ModelRouter:
    """Selects the appropriate LLM model based on issue complexity.

    Complexity is scored from 0-10 using heuristics:
    - Body length and structure (checklists, code blocks, file references)
    - Label hints (simple vs complex labels)
    - Title keywords

    Scores at or above the threshold route to "heavy" tier,
    below route to "light" tier.
    """

    def __init__(self, config: RoutingConfig):
        """Initialize the router.

        Args:
            config: Routing configuration with model profiles and thresholds.
        """
        self.config = config

    def analyze_complexity(
        self,
        title: str,
        body: str,
        labels: list[str],
    ) -> ComplexityScore:
        """Analyze issue complexity and return a score with tier recommendation.

        Args:
            title: Issue title.
            body: Issue body text.
            labels: Issue label names.

        Returns:
            ComplexityScore with score (0-10), tier, and reasons.
        """
        score = 0
        reasons: list[str] = []

        # --- Label signals ---
        lower_labels = {label.lower() for label in labels}

        simple_matches = lower_labels & SIMPLE_LABELS
        if simple_matches:
            score -= 2
            reasons.append(f"simple labels: {', '.join(simple_matches)}")

        complex_matches = lower_labels & COMPLEX_LABELS
        if complex_matches:
            score += 2
            reasons.append(f"complex labels: {', '.join(complex_matches)}")

        # --- Body length ---
        body_len = len(body) if body else 0
        if body_len > 2000:
            score += 2
            reasons.append(f"long body ({body_len} chars)")
        elif body_len > 800:
            score += 1
            reasons.append(f"medium body ({body_len} chars)")

        # --- Checklist items ---
        if body:
            checklist_items = len(re.findall(r"- \[[ x]\]", body))
            if checklist_items >= 5:
                score += 2
                reasons.append(f"{checklist_items} checklist items")
            elif checklist_items >= 2:
                score += 1
                reasons.append(f"{checklist_items} checklist items")

        # --- Code blocks ---
        if body:
            code_blocks = len(re.findall(r"```", body)) // 2
            if code_blocks >= 3:
                score += 1
                reasons.append(f"{code_blocks} code blocks")

        # --- File references ---
        if body:
            file_refs = len(re.findall(r"[\w/]+\.\w{1,5}", body))
            if file_refs >= 5:
                score += 2
                reasons.append(f"{file_refs} file references")
            elif file_refs >= 2:
                score += 1
                reasons.append(f"{file_refs} file references")

        # --- Title complexity keywords ---
        title_lower = title.lower() if title else ""
        complex_keywords = {"refactor", "redesign", "migrate", "rewrite", "overhaul"}
        simple_keywords = {"fix typo", "update readme", "bump version", "rename"}

        if any(kw in title_lower for kw in complex_keywords):
            score += 2
            reasons.append("complex keyword in title")

        if any(kw in title_lower for kw in simple_keywords):
            score -= 1
            reasons.append("simple keyword in title")

        # Clamp to 0-10
        score = max(0, min(10, score))

        # Determine tier
        tier = "heavy" if score >= self.config.complexity_threshold else "light"

        return ComplexityScore(score=score, tier=tier, reasons=reasons)

    def select_model(
        self,
        title: str,
        body: str,
        labels: list[str],
    ) -> Optional[ModelProfile]:
        """Select the appropriate model for an issue.

        Args:
            title: Issue title.
            body: Issue body text.
            labels: Issue label names.

        Returns:
            ModelProfile for the selected tier, or None if routing is disabled
            or no model is configured for the tier.
        """
        if not self.config.enabled:
            return None

        complexity = self.analyze_complexity(title, body, labels)

        logger.info(
            f"Complexity analysis: score={complexity.score}, "
            f"tier={complexity.tier}, reasons={complexity.reasons}"
        )

        model = self.config.get_model(complexity.tier)
        if model is None:
            # Fall back to default tier
            model = self.config.get_model(self.config.default_tier)

        if model:
            logger.info(f"Selected model: {model.name} (tier={model.tier})")
        else:
            logger.warning(
                f"No model configured for tier={complexity.tier}, "
                f"falling back to default LLM config"
            )

        return model
