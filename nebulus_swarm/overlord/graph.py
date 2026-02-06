"""Dependency graph traversal for the Overlord project registry.

Wraps the project registry DAG to provide relationship queries
for release coordination and ripple/impact detection.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from nebulus_swarm.overlord.registry import OverlordConfig, get_dependency_order


@dataclass
class DependencyGraph:
    """DAG wrapper over the project registry for relationship queries."""

    config: OverlordConfig
    _adjacency: dict[str, list[str]] = field(default_factory=dict, init=False)
    _reverse: dict[str, list[str]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Build adjacency maps from config."""
        for name in self.config.projects:
            self._adjacency[name] = []
            self._reverse[name] = []

        for name, proj in self.config.projects.items():
            for dep in proj.depends_on:
                if dep in self.config.projects:
                    self._adjacency[name].append(dep)
                    self._reverse[dep].append(name)

    def get_upstream(self, project: str) -> list[str]:
        """Direct + transitive dependencies (what this project needs).

        Args:
            project: Project name to query.

        Returns:
            List of upstream project names, topologically ordered
            (deepest dependencies first).

        Raises:
            KeyError: If project is not in the registry.
        """
        self._validate_project(project)
        return self._bfs(project, self._adjacency)

    def get_downstream(self, project: str) -> list[str]:
        """Direct + transitive dependents (what depends on this project).

        Args:
            project: Project name to query.

        Returns:
            List of downstream project names.

        Raises:
            KeyError: If project is not in the registry.
        """
        self._validate_project(project)
        return self._bfs(project, self._reverse)

    def get_affected_by(self, project: str) -> list[str]:
        """All projects that could be impacted by a change in ``project``.

        Returns the project itself plus all downstream dependents.

        Args:
            project: Project name to query.

        Returns:
            List starting with ``project``, then its downstream dependents.

        Raises:
            KeyError: If project is not in the registry.
        """
        self._validate_project(project)
        downstream = self.get_downstream(project)
        return [project] + downstream

    def get_release_order(self) -> list[str]:
        """Return projects in topological order (dependencies first).

        Delegates to ``registry.get_dependency_order``.
        """
        return get_dependency_order(self.config)

    def get_subgraph(self, projects: list[str]) -> dict[str, list[str]]:
        """Return adjacency dict for a subset of projects.

        Only includes edges where both endpoints are in the subset.

        Args:
            projects: Project names to include.

        Returns:
            Dict mapping project name to list of dependencies within the subset.
        """
        subset = set(projects)
        return {
            name: [dep for dep in self._adjacency.get(name, []) if dep in subset]
            for name in projects
            if name in self.config.projects
        }

    def render_ascii(self) -> str:
        """Simple text visualization of the dependency tree.

        Returns:
            Multi-line string showing each project and its dependencies.
        """
        lines: list[str] = []
        order = self.get_release_order()

        for name in order:
            deps = self._adjacency.get(name, [])
            dependents = self._reverse.get(name, [])

            if deps:
                dep_str = ", ".join(deps)
                lines.append(f"  {name} <- [{dep_str}]")
            else:
                lines.append(f"  {name} (root)")

            for dep in dependents:
                lines.append(f"    -> {dep}")

        return "\n".join(lines)

    def _bfs(self, start: str, adj: dict[str, list[str]]) -> list[str]:
        """BFS traversal excluding the start node."""
        visited: set[str] = set()
        queue: deque[str] = deque(adj.get(start, []))
        result: list[str] = []

        for neighbor in adj.get(start, []):
            if neighbor not in visited:
                visited.add(neighbor)

        while queue:
            current = queue.popleft()
            result.append(current)
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return result

    def _validate_project(self, project: str) -> None:
        """Raise KeyError if project is not in the registry."""
        if project not in self.config.projects:
            raise KeyError(
                f"Unknown project '{project}'. "
                f"Available: {', '.join(sorted(self.config.projects.keys()))}"
            )
