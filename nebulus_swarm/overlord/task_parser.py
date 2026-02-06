"""Natural language task parser for Overlord dispatch."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from nebulus_swarm.overlord.action_scope import ActionScope, scope_for_merge
from nebulus_swarm.overlord.dispatch import DispatchPlan, DispatchStep

if TYPE_CHECKING:
    from nebulus_swarm.overlord.graph import DependencyGraph


class TaskParser:
    """Parses natural language tasks into dispatch plans."""

    def __init__(self, graph: DependencyGraph):
        """Initialize the parser.

        Args:
            graph: Dependency graph for project context.
        """
        self.graph = graph

    def parse(self, task: str) -> DispatchPlan:
        """Parse a task string into a dispatch plan.

        Args:
            task: Natural language task description.

        Returns:
            DispatchPlan ready for execution.

        Raises:
            ValueError: If task cannot be parsed.
        """
        task_clean = task.strip()

        # Try pattern matchers in priority order
        parsers = [
            self._parse_merge,
            self._parse_test,
            self._parse_clean_branches,
            self._parse_multi_project,
        ]

        for parser in parsers:
            plan = parser(task_clean)
            if plan:
                return plan

        # Fallback: generic single-step plan
        return self._parse_generic(task_clean)

    def _parse_merge(self, task: str) -> DispatchPlan | None:
        """Parse merge tasks.

        Examples:
            - "merge Core develop to main"
            - "merge nebulus-prime develop into main"
            - "merge develop to main in Core"
        """
        patterns = [
            r"merge\s+(?P<project>[\w-]+)\s+(?P<source>[\w/-]+)\s+(?:to|into)\s+(?P<target>[\w/-]+)",
            r"merge\s+(?P<source>[\w/-]+)\s+(?:to|into)\s+(?P<target>[\w/-]+)\s+in\s+(?P<project>[\w-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, task, re.IGNORECASE)
            if match:
                project = match.group("project")
                source = match.group("source")
                target = match.group("target")

                # Validate project
                if project not in self.graph.config.projects:
                    raise ValueError(f"Unknown project: {project}")

                step = DispatchStep(
                    id="merge",
                    action=f"merge {source} to {target}",
                    project=project,
                    dependencies=[],
                    model_tier=None,
                    timeout=60,
                )

                scope = scope_for_merge(project, source, target)

                return DispatchPlan(
                    task=task,
                    steps=[step],
                    scope=scope,
                    estimated_duration=60,
                    requires_approval=True,
                )

        return None

    def _parse_test(self, task: str) -> DispatchPlan | None:
        """Parse test tasks.

        Examples:
            - "run tests in Core"
            - "run tests across all projects"
            - "test Prime and Edge"
        """
        # Single project
        match = re.search(
            r"(?:run\s+)?tests?\s+in\s+(?P<project>[\w-]+)", task, re.IGNORECASE
        )
        if match:
            project = match.group("project")
            if project not in self.graph.config.projects:
                raise ValueError(f"Unknown project: {project}")

            step = DispatchStep(
                id="test",
                action="run tests",
                project=project,
                dependencies=[],
                model_tier=None,
                timeout=300,
            )

            scope = ActionScope(
                projects=[project],
                branches=[],
                destructive=False,
                reversible=True,
                affects_remote=False,
                estimated_impact="low",
            )

            return DispatchPlan(
                task=task,
                steps=[step],
                scope=scope,
                estimated_duration=300,
                requires_approval=False,
            )

        # All projects
        if re.search(r"tests?\s+across\s+all", task, re.IGNORECASE):
            projects = list(self.graph.config.projects.keys())
            steps = [
                DispatchStep(
                    id=f"test-{project}",
                    action="run tests",
                    project=project,
                    dependencies=[],
                    model_tier=None,
                    timeout=300,
                )
                for project in projects
            ]

            scope = ActionScope(
                projects=projects,
                branches=[],
                destructive=False,
                reversible=True,
                affects_remote=False,
                estimated_impact="medium",
            )

            return DispatchPlan(
                task=task,
                steps=steps,
                scope=scope,
                estimated_duration=300 * len(projects),
                requires_approval=False,
            )

        return None

    def _parse_clean_branches(self, task: str) -> DispatchPlan | None:
        """Parse branch cleanup tasks.

        Examples:
            - "clean stale branches in Prime"
            - "clean branches in Prime and Edge"
        """
        match = re.search(
            r"clean\s+(?:stale\s+)?branches?\s+in\s+(?P<projects>[\w\s,and-]+)",
            task,
            re.IGNORECASE,
        )
        if match:
            # Parse project list
            projects_str = match.group("projects")
            projects = [
                p.strip()
                for p in re.split(r"[,\s]+and\s+|,\s*", projects_str)
                if p.strip()
            ]

            # Validate projects
            for project in projects:
                if project not in self.graph.config.projects:
                    raise ValueError(f"Unknown project: {project}")

            steps = [
                DispatchStep(
                    id=f"clean-{project}",
                    action="clean stale branches",
                    project=project,
                    dependencies=[],
                    model_tier=None,
                    timeout=120,
                )
                for project in projects
            ]

            scope = ActionScope(
                projects=projects,
                branches=[],
                destructive=True,
                reversible=False,
                affects_remote=False,
                estimated_impact="low",
            )

            return DispatchPlan(
                task=task,
                steps=steps,
                scope=scope,
                estimated_duration=120 * len(projects),
                requires_approval=True,
            )

        return None

    def _parse_multi_project(self, task: str) -> DispatchPlan | None:
        """Parse multi-project tasks.

        Examples:
            - "update Core in Prime and Edge"
        """
        match = re.search(
            r"update\s+(?P<dependency>[\w-]+)\s+in\s+(?P<projects>[\w\s,and-]+)",
            task,
            re.IGNORECASE,
        )
        if match:
            dependency = match.group("dependency")
            projects_str = match.group("projects")
            projects = [
                p.strip()
                for p in re.split(r"[,\s]+and\s+|,\s*", projects_str)
                if p.strip()
            ]

            # Validate
            if dependency not in self.graph.config.projects:
                raise ValueError(f"Unknown project: {dependency}")
            for project in projects:
                if project not in self.graph.config.projects:
                    raise ValueError(f"Unknown project: {project}")

            steps = [
                DispatchStep(
                    id=f"update-{project}",
                    action=f"update {dependency}",
                    project=project,
                    dependencies=[],
                    model_tier=None,
                    timeout=180,
                )
                for project in projects
            ]

            scope = ActionScope(
                projects=projects,
                branches=[],
                destructive=False,
                reversible=True,
                affects_remote=False,
                estimated_impact="medium",
            )

            return DispatchPlan(
                task=task,
                steps=steps,
                scope=scope,
                estimated_duration=180 * len(projects),
                requires_approval=True,
            )

        return None

    def _parse_generic(self, task: str) -> DispatchPlan:
        """Fallback parser for generic tasks.

        Args:
            task: Task description.

        Returns:
            Single-step plan for the first project in config.
        """
        # Use first project as default
        projects = list(self.graph.config.projects.keys())
        if not projects:
            raise ValueError("No projects configured")

        project = projects[0]

        step = DispatchStep(
            id="generic",
            action=task,
            project=project,
            dependencies=[],
            model_tier="cloud-fast",  # Generic tasks use LLM
            timeout=300,
        )

        scope = ActionScope(
            projects=[project],
            branches=[],
            destructive=False,
            reversible=True,
            affects_remote=False,
            estimated_impact="medium",
        )

        return DispatchPlan(
            task=task,
            steps=[step],
            scope=scope,
            estimated_duration=300,
            requires_approval=True,
        )
