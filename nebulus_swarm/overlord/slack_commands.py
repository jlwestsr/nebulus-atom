"""Slack command router for Overlord Phase 3.

Routes @atom mentions in Slack to the Phase 2 Overlord stack:
scanner, graph, autonomy, dispatch, release, memory.

All Phase 2 modules are synchronous — this module bridges them
to async Slack handlers via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

from nebulus_swarm.overlord.autonomy import AutonomyEngine, get_autonomy_summary
from nebulus_swarm.overlord.dispatch import DispatchEngine
from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.memory import OverlordMemory
from nebulus_swarm.overlord.model_router import ModelRouter
from nebulus_swarm.overlord.release import (
    ReleaseCoordinator,
    ReleaseSpec,
    validate_release_spec,
)
from nebulus_swarm.overlord.scanner import scan_ecosystem, scan_project
from nebulus_swarm.overlord.task_parser import TaskParser

if TYPE_CHECKING:
    from nebulus_swarm.overlord.registry import OverlordConfig

logger = logging.getLogger(__name__)

# Command patterns
_RE_STATUS = re.compile(r"^status(?:\s+(\S+))?$", re.IGNORECASE)
_RE_SCAN = re.compile(r"^scan(?:\s+(\S+))?$", re.IGNORECASE)
_RE_MERGE = re.compile(r"^merge\s+(\S+)\s+(\S+)\s+to\s+(\S+)$", re.IGNORECASE)
_RE_RELEASE = re.compile(r"^release\s+(\S+)\s+(\S+)$", re.IGNORECASE)
_RE_AUTONOMY = re.compile(r"^autonomy(?:\s+(\S+))?$", re.IGNORECASE)
_RE_MEMORY = re.compile(r"^memory\s+(.+)$", re.IGNORECASE)
_RE_HELP = re.compile(r"^help$", re.IGNORECASE)


class SlackCommandRouter:
    """Routes Slack messages to Overlord Phase 2 module calls."""

    def __init__(self, config: OverlordConfig):
        """Initialize the command router with the full Phase 2 stack.

        Args:
            config: Overlord configuration with project registry.
        """
        self.config = config
        self.graph = DependencyGraph(config)
        self.autonomy = AutonomyEngine(config)
        self.router = ModelRouter(config)
        self.dispatch = DispatchEngine(config, self.autonomy, self.graph, self.router)
        self.memory = OverlordMemory()
        self.task_parser = TaskParser(self.graph)
        self.release_coordinator = ReleaseCoordinator(
            config, self.graph, self.dispatch, self.memory
        )

    async def handle(self, text: str, user_id: str, channel_id: str) -> str:
        """Parse a command and dispatch to the appropriate handler.

        Args:
            text: Raw message text (with @mention already stripped).
            user_id: Slack user ID of the sender.
            channel_id: Slack channel ID.

        Returns:
            Formatted response string for Slack.
        """
        text = text.strip()
        if not text:
            return await self._handle_help()

        try:
            # Match patterns in priority order
            m = _RE_STATUS.match(text)
            if m:
                return await self._handle_status(m.group(1))

            m = _RE_SCAN.match(text)
            if m:
                return await self._handle_scan(m.group(1))

            m = _RE_MERGE.match(text)
            if m:
                return await self._handle_dispatch(text)

            m = _RE_RELEASE.match(text)
            if m:
                return await self._handle_release(m.group(1), m.group(2))

            m = _RE_AUTONOMY.match(text)
            if m:
                return await self._handle_autonomy(m.group(1))

            m = _RE_MEMORY.match(text)
            if m:
                return await self._handle_memory(m.group(1))

            m = _RE_HELP.match(text)
            if m:
                return await self._handle_help()

            return f"Unknown command: `{text}`\nType `help` to see available commands."

        except Exception as e:
            logger.exception("Error handling Slack command: %s", text)
            return f"Error processing command: {e}"

    async def _handle_status(self, project: Optional[str]) -> str:
        """Show ecosystem or project health via scanner.

        Args:
            project: Optional project name to check.

        Returns:
            Formatted status string.
        """
        if project:
            if project not in self.config.projects:
                return _unknown_project(project, self.config)
            result = await asyncio.to_thread(
                scan_project, self.config.projects[project]
            )
            return _format_project_status(result)
        else:
            results = await asyncio.to_thread(scan_ecosystem, self.config)
            return _format_ecosystem_status(results)

    async def _handle_scan(self, project: Optional[str]) -> str:
        """Detailed scan with issue detection.

        Args:
            project: Optional project name to scan.

        Returns:
            Formatted scan results.
        """
        if project:
            if project not in self.config.projects:
                return _unknown_project(project, self.config)
            result = await asyncio.to_thread(
                scan_project, self.config.projects[project]
            )
            return _format_scan_detail(result)
        else:
            results = await asyncio.to_thread(scan_ecosystem, self.config)
            lines = [_format_scan_detail(r) for r in results]
            return "\n\n".join(lines)

    async def _handle_dispatch(self, task: str) -> str:
        """Dispatch a task via TaskParser and DispatchEngine.

        Args:
            task: Natural language task string.

        Returns:
            Formatted dispatch result.
        """
        try:
            plan = await asyncio.to_thread(self.task_parser.parse, task)
        except ValueError as e:
            return f"Failed to parse task: {e}"

        scope = plan.scope
        lines = [
            f"Dispatch: {plan.task}",
            f"Steps: {len(plan.steps)}",
            f"Scope: {', '.join(scope.projects)} | impact: {scope.estimated_impact}",
        ]

        if plan.requires_approval:
            lines.append("Requires approval — use the approval workflow.")
            return "\n".join(lines)

        result = await asyncio.to_thread(self.dispatch.execute, plan, True)

        if result.status == "success":
            lines.append("Result: completed successfully")
        elif result.status == "cancelled":
            lines.append(f"Result: cancelled — {result.reason}")
        else:
            lines.append(f"Result: failed — {result.reason}")

        return "\n".join(lines)

    async def _handle_release(self, project: str, version: str) -> str:
        """Coordinated release via ReleaseCoordinator.

        Args:
            project: Project name to release.
            version: Version string (e.g., v0.2.0).

        Returns:
            Formatted release result.
        """
        if project not in self.config.projects:
            return _unknown_project(project, self.config)

        spec = ReleaseSpec(project=project, version=version)
        errors = validate_release_spec(spec, self.config)
        if errors:
            return "Release validation failed:\n" + "\n".join(
                f"  - {e}" for e in errors
            )

        try:
            plan = await asyncio.to_thread(self.release_coordinator.plan_release, spec)
        except ValueError as e:
            return f"Failed to plan release: {e}"

        scope = plan.scope
        lines = [
            f"Release: {project} {version}",
            f"Steps: {len(plan.steps)}",
            f"Scope: {', '.join(scope.projects)} | impact: {scope.estimated_impact}",
        ]

        if plan.requires_approval:
            lines.append("Requires approval — use the approval workflow.")
            return "\n".join(lines)

        result = await asyncio.to_thread(
            self.release_coordinator.execute_release, spec, True
        )

        if result.status == "success":
            lines.append(f"Result: {project} {version} released successfully")
        else:
            lines.append(f"Result: {result.status} — {result.reason}")

        return "\n".join(lines)

    async def _handle_autonomy(self, level: Optional[str]) -> str:
        """Show or describe autonomy level.

        Args:
            level: Optional level name to describe.

        Returns:
            Formatted autonomy info.
        """
        if level:
            descriptions = {
                "cautious": (
                    "Cautious: Nothing auto-executes. "
                    "All actions require explicit approval."
                ),
                "proactive": (
                    "Proactive: Safe local operations auto-execute. "
                    "Remote-affecting actions require approval."
                ),
                "scheduled": (
                    "Scheduled: Pre-approved actions auto-execute on schedule. "
                    "Others require approval."
                ),
            }
            desc = descriptions.get(level.lower())
            if desc:
                return desc
            return (
                f"Unknown autonomy level: `{level}`\n"
                "Valid levels: cautious, proactive, scheduled"
            )

        summary = get_autonomy_summary(self.config)
        lines = [f"Autonomy: global = {summary['__global__']}"]
        for proj_name in sorted(self.config.projects.keys()):
            lines.append(f"  {proj_name}: {summary[proj_name]}")
        return "\n".join(lines)

    async def _handle_memory(self, query: str) -> str:
        """Search cross-project memory.

        Args:
            query: Search query string.

        Returns:
            Formatted memory results.
        """
        results = await asyncio.to_thread(self.memory.search, query, limit=5)
        if not results:
            return f"No memories found for: {query}"

        lines = [f"Memory results for '{query}':"]
        for entry in results:
            proj = entry.project or "global"
            lines.append(
                f"  [{entry.id[:8]}] ({proj}/{entry.category}) {entry.content[:80]}"
            )
        return "\n".join(lines)

    async def _handle_help(self) -> str:
        """List available commands.

        Returns:
            Help text with all supported commands.
        """
        return (
            "Overlord Commands:\n"
            "  `status [project]` — ecosystem or project health\n"
            "  `scan [project]` — detailed scan with issue detection\n"
            "  `merge <project> <source> to <target>` — dispatch a merge\n"
            "  `release <project> <version>` — coordinated release\n"
            "  `autonomy [level]` — show/describe autonomy level\n"
            "  `memory <query>` — search cross-project memory\n"
            "  `help` — show this message"
        )


# --- Formatting helpers ---


def _unknown_project(name: str, config: OverlordConfig) -> str:
    """Format an unknown-project error message."""
    available = ", ".join(sorted(config.projects.keys()))
    return f"Unknown project: `{name}`\nAvailable: {available}"


def _format_project_status(result: object) -> str:
    """Format a single ProjectStatus for Slack."""
    # result is a ProjectStatus dataclass
    status_icon = "🟢" if not result.issues else "🟡"
    clean = "clean" if result.git.clean else "dirty"
    lines = [
        f"{status_icon} *{result.name}*",
        f"  Branch: `{result.git.branch}` ({clean})",
        f"  Last commit: {result.git.last_commit[:50]}",
    ]
    if result.git.ahead:
        lines.append(f"  Ahead: {result.git.ahead} commits")
    if result.issues:
        lines.append("  Issues: " + "; ".join(result.issues))
    return "\n".join(lines)


def _format_ecosystem_status(results: list) -> str:
    """Format ecosystem status summary for Slack."""
    total = len(results)
    healthy = sum(1 for r in results if not r.issues)
    icon = "🟢" if healthy == total else "🟡"

    lines = [f"{icon} *Ecosystem Status*: {healthy}/{total} healthy"]
    for r in results:
        status = "🟢" if not r.issues else "🟡"
        clean = "clean" if r.git.clean else "dirty"
        lines.append(f"  {status} {r.name} — `{r.git.branch}` ({clean})")
    return "\n".join(lines)


def _format_scan_detail(result: object) -> str:
    """Format detailed scan for a single project."""
    lines = [
        f"*{result.name}*",
        f"  Branch: `{result.git.branch}`"
        f" | Clean: {'yes' if result.git.clean else 'no'}",
        f"  Ahead/Behind: {result.git.ahead}/{result.git.behind}",
        f"  Last commit: {result.git.last_commit[:60]}",
    ]
    if result.git.stale_branches:
        lines.append(f"  Stale branches: {', '.join(result.git.stale_branches)}")
    if result.git.tags:
        lines.append(f"  Tags: {', '.join(result.git.tags[-3:])}")
    if result.tests.has_tests:
        lines.append(f"  Tests: {result.tests.test_command}")
    if result.issues:
        lines.append("  Issues:")
        for issue in result.issues:
            lines.append(f"    - {issue}")
    return "\n".join(lines)
