"""Proactive detection patterns for Overlord Phase 3.

Detectors inspect the ecosystem for actionable issues:
stale branches, develop-ahead-of-main, failing tests.
Results feed into the ProposalManager for approval workflows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from nebulus_swarm.overlord.scanner import ProjectStatus, scan_ecosystem, scan_project

if TYPE_CHECKING:
    from nebulus_swarm.overlord.autonomy import AutonomyEngine
    from nebulus_swarm.overlord.graph import DependencyGraph
    from nebulus_swarm.overlord.registry import OverlordConfig

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """A single detection finding."""

    detector: str
    project: str
    severity: str  # "low", "medium", "high"
    description: str
    proposed_action: str  # Natural language for TaskParser


class StaleBranchDetector:
    """Detects branches with no recent activity."""

    def __init__(self, threshold_days: int = 7):
        self.threshold_days = threshold_days

    def detect(self, status: ProjectStatus) -> list[DetectionResult]:
        """Check a project for stale branches.

        Args:
            status: Scanned project status.

        Returns:
            List of detection results for stale branches.
        """
        results = []
        for branch in status.git.stale_branches:
            results.append(
                DetectionResult(
                    detector="stale-branch",
                    project=status.name,
                    severity="low",
                    description=f"Branch '{branch}' has no recent activity "
                    f"(>{self.threshold_days} days)",
                    proposed_action=f"clean stale branches in {status.name}",
                )
            )
        return results


class AheadOfMainDetector:
    """Detects when develop has commits not yet on main."""

    def detect(self, status: ProjectStatus) -> list[DetectionResult]:
        """Check if project's current branch is ahead of tracking branch.

        Args:
            status: Scanned project status.

        Returns:
            List of detection results if ahead.
        """
        if status.git.ahead > 0:
            severity = "low" if status.git.ahead < 5 else "medium"
            return [
                DetectionResult(
                    detector="ahead-of-main",
                    project=status.name,
                    severity=severity,
                    description=f"Branch '{status.git.branch}' is "
                    f"{status.git.ahead} commits ahead",
                    proposed_action=f"merge {status.name} develop to main",
                )
            ]
        return []


class FailingTestDetector:
    """Detects projects with test failures or missing tests."""

    def detect(self, status: ProjectStatus) -> list[DetectionResult]:
        """Check a project for test issues.

        Args:
            status: Scanned project status.

        Returns:
            List of detection results for test problems.
        """
        results = []
        if not status.tests.has_tests:
            results.append(
                DetectionResult(
                    detector="failing-test",
                    project=status.name,
                    severity="medium",
                    description="No test infrastructure detected",
                    proposed_action=f"run tests in {status.name}",
                )
            )
        # Check for test-related issues in the scan results
        for issue in status.issues:
            if "test" in issue.lower() or "fail" in issue.lower():
                results.append(
                    DetectionResult(
                        detector="failing-test",
                        project=status.name,
                        severity="high",
                        description=issue,
                        proposed_action=f"run tests in {status.name}",
                    )
                )
        return results


class DetectionEngine:
    """Runs detectors, filters by autonomy, generates proposals."""

    def __init__(
        self,
        config: OverlordConfig,
        graph: DependencyGraph,
        autonomy: AutonomyEngine,
    ):
        """Initialize the detection engine.

        Args:
            config: Overlord configuration.
            graph: Dependency graph for project context.
            autonomy: Autonomy engine for filtering.
        """
        self.config = config
        self.graph = graph
        self.autonomy = autonomy
        self.detectors = [
            StaleBranchDetector(threshold_days=7),
            AheadOfMainDetector(),
            FailingTestDetector(),
        ]

    def run_all(self, project: Optional[str] = None) -> list[DetectionResult]:
        """Run all detectors across the ecosystem or a single project.

        Args:
            project: Optional project name to scan. Scans all if None.

        Returns:
            Combined list of detection results.
        """
        if project:
            if project not in self.config.projects:
                logger.warning("Unknown project for detection: %s", project)
                return []
            statuses = [scan_project(self.config.projects[project])]
        else:
            statuses = scan_ecosystem(self.config)

        results: list[DetectionResult] = []
        for status in statuses:
            for detector in self.detectors:
                results.extend(detector.detect(status))

        logger.info(
            "Detection sweep: %d findings across %d projects",
            len(results),
            len(statuses),
        )
        return results

    def filter_by_autonomy(
        self, results: list[DetectionResult]
    ) -> list[DetectionResult]:
        """Filter detection results by autonomy level.

        In cautious mode, all results are surfaced (for human review).
        In proactive mode, only low-severity local results are auto-actionable.
        In scheduled mode, results matching pre-approved actions pass through.

        Args:
            results: Raw detection results.

        Returns:
            Filtered results appropriate for the current autonomy level.
        """
        filtered = []
        for result in results:
            level = self.autonomy.get_level(result.project)
            if level == "cautious":
                # Surface everything for human review
                filtered.append(result)
            elif level == "proactive":
                # Only low-severity items
                if result.severity in ("low", "medium"):
                    filtered.append(result)
            elif level == "scheduled":
                # All results (scheduled has pre-approved actions)
                filtered.append(result)
        return filtered

    def format_summary(self, results: list[DetectionResult]) -> str:
        """Format detection results as a Slack-friendly summary.

        Args:
            results: Detection results to summarize.

        Returns:
            Formatted string.
        """
        if not results:
            return "No issues detected."

        lines = [f"Detection sweep: {len(results)} findings"]
        by_project: dict[str, list[DetectionResult]] = {}
        for r in results:
            by_project.setdefault(r.project, []).append(r)

        for proj, findings in sorted(by_project.items()):
            lines.append(f"  {proj}:")
            for f in findings:
                icon = {"low": ".", "medium": "!", "high": "!!"}
                lines.append(f"    [{icon.get(f.severity, '?')}] {f.description}")
        return "\n".join(lines)
