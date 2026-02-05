"""Skill evolution workflow for supervisor-driven capability growth."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

from nebulus_swarm.overlord.proposals import (
    EnhancementProposal,
    ProposalStore,
    ProposalType,
)

logger = logging.getLogger(__name__)


class SkillCategory(Enum):
    """Category of skill being proposed."""

    CODE_ANALYSIS = "code_analysis"
    CODE_GENERATION = "code_generation"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    DEVOPS = "devops"
    CUSTOM = "custom"


@dataclass
class SkillSpec:
    """Specification for a new skill."""

    name: str
    description: str
    category: SkillCategory
    inputs: List[
        Dict[str, str]
    ]  # [{"name": "repo_path", "type": "str", "description": "..."}]
    outputs: List[
        Dict[str, str]
    ]  # [{"name": "result", "type": "str", "description": "..."}]
    constraints: List[str]  # ["Must not modify files outside scope", ...]
    test_cases: List[
        Dict[str, Any]
    ]  # [{"input": {...}, "expected_output": {...}, "description": "..."}]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def is_valid(self) -> bool:
        """Check if spec has minimum required fields."""
        return bool(
            self.name
            and self.description
            and self.inputs
            and self.outputs
            and self.test_cases
        )


@dataclass
class SkillValidationResult:
    """Result of validating an implemented skill against its spec."""

    spec_id: str
    passed: bool
    test_results: List[
        Dict[str, Any]
    ]  # [{"test_case": ..., "passed": bool, "error": Optional[str]}]
    feedback: str = ""

    @property
    def pass_rate(self) -> float:
        """Fraction of test cases that passed."""
        if not self.test_results:
            return 0.0
        passed = sum(1 for r in self.test_results if r.get("passed", False))
        return passed / len(self.test_results)


class SkillEvolution:
    """Manages the lifecycle of skill creation and validation."""

    def __init__(self, proposal_store: ProposalStore):
        self._store = proposal_store

    def draft_spec(self, spec: SkillSpec) -> EnhancementProposal:
        """Create an enhancement proposal for a new skill.

        Returns the proposal so it can be presented to the user for approval.
        """
        if not spec.is_valid:
            raise ValueError(
                f"Skill spec '{spec.name}' is incomplete: needs name, description, inputs, outputs, and test_cases"
            )

        proposal = EnhancementProposal(
            type=ProposalType.NEW_SKILL,
            title=f"New Skill: {spec.name}",
            rationale=spec.description,
            proposed_action=f"Implement skill '{spec.name}' with {len(spec.test_cases)} test cases. "
            f"Category: {spec.category.value}. "
            f"Inputs: {', '.join(i['name'] for i in spec.inputs)}. "
            f"Outputs: {', '.join(o['name'] for o in spec.outputs)}.",
            estimated_impact="Medium",
            risk="Low",
        )
        self._store.save(proposal)
        logger.info(f"Drafted skill proposal: {proposal.title} (id={proposal.id[:8]})")
        return proposal

    def validate_skill(
        self,
        spec: SkillSpec,
        skill_callable: Any,
    ) -> SkillValidationResult:
        """Validate an implemented skill against its spec.

        Runs each test case from the spec against the skill callable
        and reports results.
        """
        test_results = []
        for tc in spec.test_cases:
            try:
                result = skill_callable(**tc.get("input", {}))
                expected = tc.get("expected_output")
                if expected is not None:
                    passed = result == expected
                else:
                    passed = result is not None  # Just verify it returns something
                test_results.append(
                    {
                        "test_case": tc.get("description", "unnamed"),
                        "passed": passed,
                        "error": None
                        if passed
                        else f"Expected {expected}, got {result}",
                    }
                )
            except Exception as e:
                test_results.append(
                    {
                        "test_case": tc.get("description", "unnamed"),
                        "passed": False,
                        "error": str(e),
                    }
                )

        all_passed = all(r["passed"] for r in test_results)
        feedback = (
            "All test cases passed."
            if all_passed
            else f"{sum(1 for r in test_results if not r['passed'])} test case(s) failed."
        )

        return SkillValidationResult(
            spec_id=spec.id,
            passed=all_passed,
            test_results=test_results,
            feedback=feedback,
        )
