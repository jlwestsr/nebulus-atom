"""Tests for certification packages."""

import json

import pytest

from nebulus_swarm.overlord.auditor import AuditIssue, AuditResult, AuditSeverity
from nebulus_swarm.overlord.certification import (
    CertificationBuilder,
    CertificationPackage,
    ImpactAnalysis,
    TestResult,
)
from nebulus_swarm.overlord.proposals import EnhancementProposal, ProposalType


class TestTestResult:
    def test_pass_rate_calculation(self):
        result = TestResult(total=100, passed=90, failed=10)
        assert result.pass_rate == 90.0

    def test_pass_rate_zero_total(self):
        result = TestResult(total=0, passed=0, failed=0)
        assert result.pass_rate == 0.0


class TestImpactAnalysis:
    def test_churn_calculation(self):
        impact = ImpactAnalysis(lines_added=50, lines_removed=20)
        assert impact.churn == 70

    def test_default_risk(self):
        impact = ImpactAnalysis()
        assert impact.estimated_risk == "low"


class TestCertificationPackage:
    def test_create_package(self):
        pkg = CertificationPackage(
            proposal_id="p-123",
            proposal_title="Add feature X",
            proposal_type="new_skill",
            proposal_rationale="Needed for Y",
            proposal_action="Implement Z",
        )
        assert pkg.proposal_id == "p-123"
        assert pkg.status == "pending"

    def test_to_dict_and_back(self):
        pkg = CertificationPackage(
            proposal_id="p-456",
            proposal_title="Fix bug",
            proposal_type="tool_fix",
            proposal_rationale="Bug causes X",
            proposal_action="Fix Y",
            test_results=TestResult(total=10, passed=9, failed=1),
            impact_analysis=ImpactAnalysis(
                files_affected=3, lines_added=20, lines_removed=5
            ),
        )
        d = pkg.to_dict()
        restored = CertificationPackage.from_dict(d)
        assert restored.proposal_id == pkg.proposal_id
        assert restored.test_results.total == 10
        assert restored.impact_analysis.churn == 25

    def test_to_json(self):
        pkg = CertificationPackage(
            proposal_id="p-789",
            proposal_title="Test",
            proposal_type="config_change",
            proposal_rationale="R",
            proposal_action="A",
        )
        json_str = pkg.to_json()
        parsed = json.loads(json_str)
        assert parsed["proposal_id"] == "p-789"

    def test_format_summary(self):
        pkg = CertificationPackage(
            proposal_id="p-001",
            proposal_title="New Feature",
            proposal_type="new_skill",
            proposal_rationale="Because reasons",
            proposal_action="Do the thing",
            test_results=TestResult(total=50, passed=48, failed=2),
            auditor_score=0.95,
            evaluator_score="pass",
        )
        summary = pkg.format_summary()
        assert "New Feature" in summary
        assert "48/50" in summary
        assert "95%" in summary


class TestCertificationBuilder:
    def test_build_requires_proposal(self):
        builder = CertificationBuilder()
        with pytest.raises(ValueError, match="Proposal is required"):
            builder.build()

    def test_build_from_proposal(self):
        proposal = EnhancementProposal(
            type=ProposalType.NEW_SKILL,
            title="New Skill: Parser",
            rationale="Need to parse things",
            proposed_action="Implement parser",
        )
        pkg = CertificationBuilder().from_proposal(proposal).build()
        assert pkg.proposal_title == "New Skill: Parser"
        assert pkg.proposal_type == "new_skill"

    def test_builder_chaining(self):
        proposal = EnhancementProposal(
            type=ProposalType.TOOL_FIX,
            title="Fix Tool",
            rationale="It's broken",
            proposed_action="Fix it",
        )
        pkg = (
            CertificationBuilder()
            .from_proposal(proposal)
            .with_diff("Changed 3 files")
            .with_test_results(total=100, passed=99, failed=1)
            .with_impact(
                files_affected=3, lines_added=50, lines_removed=10, risk="medium"
            )
            .build()
        )
        assert pkg.diff_summary == "Changed 3 files"
        assert pkg.test_results.passed == 99
        assert pkg.impact_analysis.estimated_risk == "medium"

    def test_with_audit_result(self):
        proposal = EnhancementProposal(
            type=ProposalType.CONFIG_CHANGE,
            title="Config Change",
            rationale="Optimization",
            proposed_action="Update config",
        )
        audit = AuditResult(
            passed=True,
            confidence=0.9,
            issues=[
                AuditIssue(
                    check="safety", severity=AuditSeverity.WARNING, message="eval usage"
                ),
            ],
        )
        pkg = (
            CertificationBuilder()
            .from_proposal(proposal)
            .with_audit_result(audit)
            .build()
        )
        assert pkg.auditor_score == 0.9
        assert len(pkg.auditor_issues) == 1
        assert "eval" in pkg.auditor_issues[0]


class TestExportFormat:
    def test_json_export_complete(self):
        pkg = CertificationPackage(
            proposal_id="export-test",
            proposal_title="Export Test",
            proposal_type="workflow_improvement",
            proposal_rationale="Test export",
            proposal_action="Verify JSON",
            test_results=TestResult(total=5, passed=5, failed=0, duration_seconds=1.5),
            impact_analysis=ImpactAnalysis(
                files_affected=2,
                lines_added=30,
                lines_removed=10,
                estimated_risk="low",
                affected_components=["api", "cli"],
            ),
        )
        json_str = pkg.to_json()
        data = json.loads(json_str)

        # Verify structure
        assert "proposal_id" in data
        assert "test_results" in data
        # Pass rate is a property, not stored in dict
        assert "pass_rate" not in data["test_results"]
        assert "impact_analysis" in data
        assert data["impact_analysis"]["affected_components"] == ["api", "cli"]
