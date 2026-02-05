"""Tests for skill evolution workflow."""

import pytest

pytest.importorskip("nebulus_swarm.overlord.proposals")

from nebulus_swarm.overlord.proposals import (
    ProposalStore,
    ProposalType,
)
from nebulus_swarm.overlord.skill_evolution import (
    SkillCategory,
    SkillSpec,
    SkillValidationResult,
    SkillEvolution,
)


def test_skill_spec_valid():
    """Test that a complete SkillSpec is valid."""
    spec = SkillSpec(
        name="test_skill",
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "input1", "type": "str", "description": "Test input"}],
        outputs=[{"name": "output1", "type": "str", "description": "Test output"}],
        constraints=["No file modification"],
        test_cases=[
            {
                "input": {"arg": "value"},
                "expected_output": "result",
                "description": "Test case 1",
            }
        ],
    )
    assert spec.is_valid is True


def test_skill_spec_invalid_missing_name():
    """Test that a spec with empty name is invalid."""
    spec = SkillSpec(
        name="",
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "input1", "type": "str", "description": "Test input"}],
        outputs=[{"name": "output1", "type": "str", "description": "Test output"}],
        constraints=["No file modification"],
        test_cases=[
            {
                "input": {"arg": "value"},
                "expected_output": "result",
                "description": "Test case 1",
            }
        ],
    )
    assert spec.is_valid is False


def test_skill_spec_invalid_missing_tests():
    """Test that a spec with empty test_cases is invalid."""
    spec = SkillSpec(
        name="test_skill",
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "input1", "type": "str", "description": "Test input"}],
        outputs=[{"name": "output1", "type": "str", "description": "Test output"}],
        constraints=["No file modification"],
        test_cases=[],
    )
    assert spec.is_valid is False


def test_draft_spec_creates_proposal(tmp_path):
    """Test that draft_spec creates and saves a proposal."""
    store = ProposalStore(tmp_path / "test.db")
    evolution = SkillEvolution(store)

    spec = SkillSpec(
        name="test_skill",
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "input1", "type": "str", "description": "Test input"}],
        outputs=[{"name": "output1", "type": "str", "description": "Test output"}],
        constraints=["No file modification"],
        test_cases=[
            {
                "input": {"arg": "value"},
                "expected_output": "result",
                "description": "Test case 1",
            }
        ],
    )

    proposal = evolution.draft_spec(spec)

    # Verify proposal was saved
    retrieved = store.get(proposal.id)
    assert retrieved is not None
    assert retrieved.id == proposal.id
    assert retrieved.title == "New Skill: test_skill"


def test_draft_spec_invalid_raises(tmp_path):
    """Test that draft_spec raises ValueError for invalid spec."""
    store = ProposalStore(tmp_path / "test.db")
    evolution = SkillEvolution(store)

    spec = SkillSpec(
        name="",  # Invalid: empty name
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "input1", "type": "str", "description": "Test input"}],
        outputs=[{"name": "output1", "type": "str", "description": "Test output"}],
        constraints=["No file modification"],
        test_cases=[],  # Invalid: empty test cases
    )

    with pytest.raises(ValueError, match="incomplete"):
        evolution.draft_spec(spec)


def test_draft_spec_proposal_type(tmp_path):
    """Test that draft_spec creates a NEW_SKILL proposal type."""
    store = ProposalStore(tmp_path / "test.db")
    evolution = SkillEvolution(store)

    spec = SkillSpec(
        name="test_skill",
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "input1", "type": "str", "description": "Test input"}],
        outputs=[{"name": "output1", "type": "str", "description": "Test output"}],
        constraints=["No file modification"],
        test_cases=[
            {
                "input": {"arg": "value"},
                "expected_output": "result",
                "description": "Test case 1",
            }
        ],
    )

    proposal = evolution.draft_spec(spec)
    assert proposal.type == ProposalType.NEW_SKILL


def test_validate_skill_all_pass(tmp_path):
    """Test validating a skill where all test cases pass."""
    store = ProposalStore(tmp_path / "test.db")
    evolution = SkillEvolution(store)

    spec = SkillSpec(
        name="test_skill",
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "value", "type": "str", "description": "Input value"}],
        outputs=[{"name": "result", "type": "str", "description": "Output result"}],
        constraints=["No file modification"],
        test_cases=[
            {
                "input": {"value": "test"},
                "expected_output": "TEST",
                "description": "Uppercase conversion",
            },
            {
                "input": {"value": "hello"},
                "expected_output": "HELLO",
                "description": "Another uppercase test",
            },
        ],
    )

    # Mock skill that uppercases input
    def mock_skill(value: str) -> str:
        return value.upper()

    result = evolution.validate_skill(spec, mock_skill)
    assert result.passed is True
    assert len(result.test_results) == 2
    assert all(r["passed"] for r in result.test_results)
    assert result.pass_rate == 1.0


def test_validate_skill_some_fail(tmp_path):
    """Test validating a skill where some test cases fail."""
    store = ProposalStore(tmp_path / "test.db")
    evolution = SkillEvolution(store)

    spec = SkillSpec(
        name="test_skill",
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "value", "type": "str", "description": "Input value"}],
        outputs=[{"name": "result", "type": "str", "description": "Output result"}],
        constraints=["No file modification"],
        test_cases=[
            {
                "input": {"value": "test"},
                "expected_output": "TEST",
                "description": "Uppercase conversion",
            },
            {
                "input": {"value": "hello"},
                "expected_output": "GOODBYE",  # Wrong expected value
                "description": "Failing test",
            },
        ],
    )

    # Mock skill that uppercases input
    def mock_skill(value: str) -> str:
        return value.upper()

    result = evolution.validate_skill(spec, mock_skill)
    assert result.passed is False
    assert len(result.test_results) == 2
    assert result.test_results[0]["passed"] is True
    assert result.test_results[1]["passed"] is False
    assert result.pass_rate == 0.5


def test_validate_skill_exception(tmp_path):
    """Test validating a skill that raises exceptions."""
    store = ProposalStore(tmp_path / "test.db")
    evolution = SkillEvolution(store)

    spec = SkillSpec(
        name="test_skill",
        description="A test skill",
        category=SkillCategory.CODE_ANALYSIS,
        inputs=[{"name": "value", "type": "str", "description": "Input value"}],
        outputs=[{"name": "result", "type": "str", "description": "Output result"}],
        constraints=["No file modification"],
        test_cases=[
            {
                "input": {"value": "test"},
                "expected_output": "result",
                "description": "Test that raises",
            }
        ],
    )

    # Mock skill that raises an exception
    def mock_skill(value: str) -> str:
        raise RuntimeError("Something went wrong")

    result = evolution.validate_skill(spec, mock_skill)
    assert result.passed is False
    assert len(result.test_results) == 1
    assert result.test_results[0]["passed"] is False
    assert "Something went wrong" in result.test_results[0]["error"]
    assert result.pass_rate == 0.0


def test_validation_pass_rate(tmp_path):
    """Test that pass_rate property calculates correctly."""
    # Test with all passed
    result = SkillValidationResult(
        spec_id="test",
        passed=True,
        test_results=[
            {"passed": True},
            {"passed": True},
            {"passed": True},
        ],
    )
    assert result.pass_rate == 1.0

    # Test with some failed
    result = SkillValidationResult(
        spec_id="test",
        passed=False,
        test_results=[
            {"passed": True},
            {"passed": False},
            {"passed": True},
        ],
    )
    assert result.pass_rate == 2 / 3

    # Test with empty results
    result = SkillValidationResult(
        spec_id="test",
        passed=False,
        test_results=[],
    )
    assert result.pass_rate == 0.0


def test_skill_category_values():
    """Test that all skill category enum values are accessible."""
    categories = [
        SkillCategory.CODE_ANALYSIS,
        SkillCategory.CODE_GENERATION,
        SkillCategory.TESTING,
        SkillCategory.DOCUMENTATION,
        SkillCategory.DEVOPS,
        SkillCategory.CUSTOM,
    ]
    assert len(categories) == 6
    assert SkillCategory.CODE_ANALYSIS.value == "code_analysis"
    assert SkillCategory.CODE_GENERATION.value == "code_generation"
    assert SkillCategory.TESTING.value == "testing"
    assert SkillCategory.DOCUMENTATION.value == "documentation"
    assert SkillCategory.DEVOPS.value == "devops"
    assert SkillCategory.CUSTOM.value == "custom"
