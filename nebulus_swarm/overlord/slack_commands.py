"""Slack command router for Overlord Phase 3.

Routes @atom mentions in Slack to the Phase 2 Overlord stack:
scanner, graph, autonomy, dispatch, release, memory.

All Phase 2 modules are synchronous — this module bridges them
to async Slack handlers via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import re
import time
from typing import TYPE_CHECKING, Optional

from openai import AsyncOpenAI

from nebulus_swarm.config import OverlordLLMConfig
from nebulus_swarm.overlord.autonomy import AutonomyEngine, get_autonomy_summary
from nebulus_swarm.overlord.detectors import DetectionEngine
from nebulus_swarm.overlord.dispatch import DispatchEngine
from nebulus_swarm.overlord.graph import DependencyGraph
from nebulus_swarm.overlord.memory import VALID_CATEGORIES, OverlordMemory
from nebulus_swarm.overlord.model_router import ModelRouter
from nebulus_swarm.overlord.release import (
    ReleaseCoordinator,
    ReleaseSpec,
    validate_release_spec,
)
from nebulus_swarm.overlord.scanner import scan_ecosystem, scan_project
from nebulus_swarm.overlord.task_parser import TaskParser
from nebulus_swarm.overlord.worker_claude import ClaudeWorker

if TYPE_CHECKING:
    from nebulus_swarm.overlord.proposal_manager import ProposalManager
    from nebulus_swarm.overlord.registry import OverlordConfig

logger = logging.getLogger(__name__)

# Command patterns
_RE_STATUS = re.compile(r"^status(?:\s+(\S+))?$", re.IGNORECASE)
_RE_SCAN = re.compile(r"^scan(?:\s+(\S+))?$", re.IGNORECASE)
_RE_MERGE = re.compile(r"^merge\s+(\S+)\s+(\S+)\s+to\s+(\S+)$", re.IGNORECASE)
_RE_RELEASE = re.compile(r"^release\s+(\S+)\s+(\S+)$", re.IGNORECASE)
_RE_AUTONOMY = re.compile(r"^autonomy(?:\s+(\S+))?$", re.IGNORECASE)
_RE_MEMORY = re.compile(r"^memory\s+(.+)$", re.IGNORECASE)
_RE_APPROVE = re.compile(r"^approve\s+(\S+)$", re.IGNORECASE)
_RE_DENY = re.compile(r"^deny\s+(\S+)$", re.IGNORECASE)
_RE_HELP = re.compile(r"^help$", re.IGNORECASE)
_RE_GREETING = re.compile(
    r"^(hi|hello|hey|howdy|yo|sup|what'?s\s*up|how\s*are\s*you|how'?s\s*it\s*going)\b",
    re.IGNORECASE,
)
_RE_UPDATE = re.compile(
    r"(?:update|status\s+update|report|fyi|heads\s*up|completed?|shipped|deployed|pushed|merged|complete|done|finished)\b",
    re.IGNORECASE,
)
_RE_AGENT_UPDATE = re.compile(
    r"(?:agent\s*\d+|track\s*\d+|phase\s*[a-d]|gap[- ]?\d+)",
    re.IGNORECASE,
)
_RE_MEMORY_FILTER = re.compile(r"(cat|proj):(\S+)", re.IGNORECASE)
_RE_ROADMAP = re.compile(r"^roadmap$", re.IGNORECASE)
_RE_INVESTIGATE = re.compile(r"^investigate\s+(.+)$", re.IGNORECASE)
_RE_STRUCTURED_REPORT = re.compile(
    r"(?:commits?\s+pushed|tests?\s+pass|merged|shipped|deployed|zero\s+regressions)",
    re.IGNORECASE,
)


class SlackCommandRouter:
    """Routes Slack messages to Overlord Phase 2 module calls."""

    def __init__(
        self,
        config: OverlordConfig,
        proposal_manager: Optional[ProposalManager] = None,
        workspace_root: Optional[Path] = None,
    ):
        """Initialize the command router with the full Phase 2 stack.

        Args:
            config: Overlord configuration with project registry.
            proposal_manager: Optional proposal manager for approval workflows.
            workspace_root: Root directory of the workspace. Used to locate
                conductor/tracks.md, OVERLORD.md, and other governance files.
        """
        self.config = config
        self.workspace_root = workspace_root
        self.graph = DependencyGraph(config)
        self.autonomy = AutonomyEngine(config)
        self.router = ModelRouter(config)
        self.dispatch = DispatchEngine(config, self.autonomy, self.graph, self.router)
        self.memory = OverlordMemory()
        self.task_parser = TaskParser(self.graph)
        self.release_coordinator = ReleaseCoordinator(
            config, self.graph, self.dispatch, self.memory
        )
        self.proposal_manager = proposal_manager
        self._detection_engine = DetectionEngine(config, self.graph, self.autonomy)

        # LLM chat fallback
        self._llm_config = OverlordLLMConfig()
        self._llm_client: Optional[AsyncOpenAI] = None
        self._chat_history: dict[str, list[dict[str, str]]] = {}
        self._ecosystem_cache: Optional[list] = None
        self._cache_ts: float = 0.0
        self._CACHE_TTL: float = 60.0

        # AI directives — loaded once for LLM system prompt enrichment
        self._ai_directives: str = self._load_ai_directives()

        # Known project names for update tagging
        self._project_names: set[str] = set(config.projects.keys())

        # Command validator for LLM guardrails
        self._command_validator = CommandValidator(config)

        # Claude worker for investigation dispatch
        self._claude_worker: Optional[ClaudeWorker] = None
        workers_raw = getattr(config, "workers", {}) or {}
        claude_cfg = workers_raw.get("claude")
        if claude_cfg and isinstance(claude_cfg, dict) and claude_cfg.get("enabled"):
            from nebulus_swarm.overlord.worker_claude import load_worker_config

            worker_config = load_worker_config(workers_raw)
            if worker_config:
                self._claude_worker = ClaudeWorker(worker_config)

        # Slack bot reference for buffered responses (set externally by daemon)
        self.slack_bot: Optional[object] = None

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

            m = _RE_ROADMAP.match(text)
            if m:
                return await self._handle_roadmap()

            m = _RE_INVESTIGATE.match(text)
            if m:
                return await self._handle_investigate(m.group(1), user_id, channel_id)

            m = _RE_APPROVE.match(text)
            if m:
                return await self._handle_approve(m.group(1))

            m = _RE_DENY.match(text)
            if m:
                return await self._handle_deny(m.group(1))

            m = _RE_HELP.match(text)
            if m:
                return await self._handle_help()

            if _RE_GREETING.match(text):
                return (
                    "👋 Hey! I'm the Overlord — your ecosystem orchestrator.\n"
                    "Type `help` to see what I can do."
                )

            if (
                _RE_AGENT_UPDATE.search(text)
                or _RE_UPDATE.search(text)
                or _RE_STRUCTURED_REPORT.search(text)
            ):
                return await self._handle_update(text)

            return await self._handle_llm_fallback(text, user_id, channel_id)

        except Exception as e:
            logger.exception("Error handling Slack command: %s", text)
            return f"Error processing command: {e}"

    @staticmethod
    def _load_ai_directives() -> str:
        """Load and condense AI_DIRECTIVES.md for LLM system prompt.

        Reads the file from the nebulus-atom project root and extracts
        the Development Standards, Architecture Standards, and Source
        Control sections. Returns empty string if file not found.
        """
        # Walk up from this file to find AI_DIRECTIVES.md at project root
        directives_path = Path(__file__).resolve().parents[2] / "AI_DIRECTIVES.md"
        if not directives_path.is_file():
            return ""

        try:
            content = directives_path.read_text(encoding="utf-8")
        except OSError:
            return ""

        # Extract relevant sections (skip Autonomy Mandates, Execution
        # Protocol, and Communication Standards which are agent-specific)
        sections: list[str] = []
        capture = False
        for line in content.splitlines():
            if (
                line.startswith("# Development Standards")
                or line.startswith("# Architecture Standards")
                or line.startswith("## Source Control Standards")
            ):
                capture = True
            elif (
                line.startswith("# Strict Execution Protocol")
                or line.startswith("# Autonomy Mandates")
                or line.startswith("## Communication Standards")
            ):
                capture = False
            if capture:
                sections.append(line)

        return "\n".join(sections).strip()

    def _infer_project(self, text: str) -> Optional[str]:
        """Infer a project name from freeform text.

        Args:
            text: Message text to scan.

        Returns:
            First matching project name, or None.
        """
        text_lower = text.lower()
        for name in self._project_names:
            if name.lower() in text_lower:
                return name
        return None

    async def _handle_update(self, text: str) -> str:
        """Log an update/notification to memory and acknowledge.

        Extracts structured metadata (status, test counts) from agent
        status messages for richer memory entries.

        Args:
            text: The update message text.

        Returns:
            Short acknowledgment string with status emoji.
        """
        project = self._infer_project(text)

        # Infer status from keywords
        status = "update"
        if re.search(r"(?:complete|done|finished|green|passed)", text, re.IGNORECASE):
            status = "completed"
        elif re.search(r"(?:fail|error|red|blocked|broken)", text, re.IGNORECASE):
            status = "failed"
        elif re.search(
            r"(?:in.?progress|working|active|underway)", text, re.IGNORECASE
        ):
            status = "in_progress"

        # Extract test counts if present (handles "73 new tests", "407 total tests")
        test_match = re.search(
            r"(\d+)\s*(?:new\s+|total\s+)?tests?", text, re.IGNORECASE
        )
        test_count = int(test_match.group(1)) if test_match else None

        summary = text[:120].strip()

        await asyncio.to_thread(
            self.memory.remember,
            "update",
            text,
            project=project,
        )

        proj_label = f" for *{project}*" if project else ""
        status_emoji = {"completed": "✅", "failed": "❌", "in_progress": "🔄"}.get(
            status, "📝"
        )
        test_note = f" ({test_count} tests)" if test_count else ""
        return f"{status_emoji} Logged{proj_label}{test_note}. Noted: {summary}"

    async def _get_llm_health_line(self) -> str:
        """Check LLM fallback connectivity and return a status line.

        Returns:
            Formatted single-line string showing LLM health.
        """
        if not self._llm_enabled:
            return "LLM Fallback: disabled"

        try:
            client = self._client
            await asyncio.wait_for(
                client.models.list(),
                timeout=3.0,
            )
            return (
                f"LLM Fallback: ✅ connected "
                f"(`{self._llm_config.base_url}`) "
                f"| Model: {self._llm_config.model}"
            )
        except Exception:
            return f"LLM Fallback: ❌ unreachable (`{self._llm_config.base_url}`)"

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
            status_text = _format_ecosystem_status(results)
            # Append LLM fallback health
            status_text += "\n" + await self._get_llm_health_line()
            return status_text

    async def _handle_scan(self, project: Optional[str]) -> str:
        """Detailed scan with issue detection and proactive detectors.

        Args:
            project: Optional project name to scan.

        Returns:
            Formatted scan results with detection findings.
        """
        if project:
            if project not in self.config.projects:
                return _unknown_project(project, self.config)
            result = await asyncio.to_thread(
                scan_project, self.config.projects[project]
            )
            scan_text = _format_scan_detail(result)
        else:
            results = await asyncio.to_thread(scan_ecosystem, self.config)
            scan_text = "\n\n".join(_format_scan_detail(r) for r in results)

        # Run detectors
        if self._detection_engine:
            detections = await asyncio.to_thread(
                self._detection_engine.run_all, project
            )
            if detections:
                scan_text += "\n\n" + self._detection_engine.format_summary(detections)

        return scan_text

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
            if self.proposal_manager:
                pid = await self.proposal_manager.propose(
                    task, scope, "Dispatched via Slack", plan=plan
                )
                lines.append(
                    f"Requires approval — proposal `{pid}` created.\n"
                    "Reply in the proposal thread or use `approve {pid}` / `deny {pid}`."
                )
            else:
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
            if self.proposal_manager:
                pid = await self.proposal_manager.propose(
                    f"Release {project} {version}",
                    scope,
                    "Release requested via Slack",
                    plan=plan,
                )
                lines.append(
                    f"Requires approval — proposal `{pid}` created.\n"
                    "Reply in the proposal thread or use `approve {pid}` / `deny {pid}`."
                )
            else:
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

    def _parse_memory_filters(
        self, query: str
    ) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
        """Extract cat: and proj: filters from a memory query.

        Args:
            query: Raw query string, e.g. "cat:update proj:core gantry".

        Returns:
            Tuple of (clean_query, category, project, error).
            If error is not None, the other values are meaningless.
        """
        category: Optional[str] = None
        project: Optional[str] = None

        for match in _RE_MEMORY_FILTER.finditer(query):
            key = match.group(1).lower()
            value = match.group(2)
            if key == "cat":
                category = value
            elif key == "proj":
                project = value

        clean_query = _RE_MEMORY_FILTER.sub("", query).strip()

        if category and category not in VALID_CATEGORIES:
            valid = ", ".join(sorted(VALID_CATEGORIES))
            return ("", None, None, f"Invalid category: `{category}`\nValid: {valid}")

        if project and project not in self.config.projects:
            available = ", ".join(sorted(self.config.projects.keys()))
            return (
                "",
                None,
                None,
                f"Unknown project: `{project}`\nAvailable: {available}",
            )

        return (clean_query, category, project, None)

    async def _handle_memory(self, query: str) -> str:
        """Search cross-project memory.

        Args:
            query: Search query string with optional cat:/proj: filters.

        Returns:
            Formatted memory results.
        """
        clean_query, category, project, error = self._parse_memory_filters(query)
        if error:
            return error

        results = await asyncio.to_thread(
            self.memory.search, clean_query, category=category, project=project, limit=5
        )
        if not results:
            return f"No memories found for: {query}"

        lines = [f"Memory results for '{query}':"]
        for entry in results:
            proj = entry.project or "global"
            lines.append(
                f"  [{entry.id[:8]}] ({proj}/{entry.category}) {entry.content[:80]}"
            )
        return "\n".join(lines)

    async def _handle_roadmap(self) -> str:
        """Show the current roadmap from governance files and conductor tracks.

        Reads OVERLORD.md (critical path + active tracks) and falls back to
        conductor/tracks.md if the workspace root is configured. Pure file
        reads — no LLM involved.

        Returns:
            Formatted roadmap string for Slack.
        """
        if not self.workspace_root:
            return "Workspace root not configured — cannot read roadmap files."

        lines: list[str] = []

        # Read critical path from OVERLORD.md
        overlord_md = self.workspace_root / "OVERLORD.md"
        if overlord_md.is_file():
            critical_path = await asyncio.to_thread(
                _parse_overlord_md_section, overlord_md, "Critical Path"
            )
            if critical_path:
                lines.append("*Critical Path:*")
                lines.extend(f"  {line}" for line in critical_path)

        # Read active tracks from conductor/tracks.md or OVERLORD.md fallback
        tracks_md = self.workspace_root / "conductor" / "tracks.md"
        if tracks_md.is_file():
            tracks = await asyncio.to_thread(_parse_tracks_md, tracks_md)
            if tracks:
                if lines:
                    lines.append("")
                lines.append("*Active Tracks:*")
                lines.extend(f"  {line}" for line in tracks)
        elif overlord_md.is_file():
            # Fallback: read Active Tracks table from OVERLORD.md
            active_tracks = await asyncio.to_thread(
                _parse_overlord_md_section, overlord_md, "Active Tracks"
            )
            if active_tracks:
                if lines:
                    lines.append("")
                lines.append("*Active Tracks:*")
                lines.extend(f"  {line}" for line in active_tracks)

        # For each track, read the plan.md and count done/total
        tracks_dir = self.workspace_root / "conductor" / "tracks"
        if tracks_dir.is_dir():
            plan_summaries = await asyncio.to_thread(_parse_track_plans, tracks_dir)
            if plan_summaries:
                if lines:
                    lines.append("")
                lines.append("*Track Progress:*")
                lines.extend(f"  {line}" for line in plan_summaries)

        # Read strategic priorities from BUSINESS.md
        business_md = self.workspace_root / "BUSINESS.md"
        if business_md.is_file():
            priorities = await asyncio.to_thread(
                _parse_overlord_md_section, business_md, "Strategic Priorities"
            )
            if priorities:
                if lines:
                    lines.append("")
                lines.append("*Strategic Priorities:*")
                lines.extend(f"  {line}" for line in priorities)

        if not lines:
            return "No roadmap data found. Ensure OVERLORD.md and conductor/tracks.md exist."

        return "\n".join(lines)

    async def _handle_investigate(
        self, query: str, user_id: str, channel_id: str
    ) -> str:
        """Dispatch a freeform research query to the Claude worker.

        Returns an immediate acknowledgment and posts the result
        asynchronously when the investigation completes.

        Args:
            query: Natural language research question.
            user_id: Slack user ID.
            channel_id: Slack channel ID.

        Returns:
            Immediate acknowledgment string.
        """
        if not self._claude_worker or not self._claude_worker.available:
            return (
                "Investigation dispatch is not available — "
                "Claude worker is not configured or not found."
            )

        # Build a research prompt with ecosystem context
        project = self._infer_project(query)
        project_path = (
            self.config.projects[project].path
            if project and project in self.config.projects
            else self.workspace_root or Path.cwd()
        )

        prompt = (
            f"Research request from Slack user {user_id}:\n\n"
            f"{query}\n\n"
            "Provide a concise, factual answer. Cite file paths and line numbers "
            "where relevant. Do not speculate."
        )

        # Fire-and-forget: run investigation in background, post result when done
        asyncio.create_task(
            self._run_investigation(prompt, project_path, channel_id, query)
        )

        proj_label = f" (in *{project}*)" if project else ""
        return (
            f"Investigating{proj_label}: _{query[:100]}_\nI'll post results when ready."
        )

    async def _run_investigation(
        self,
        prompt: str,
        project_path: Path,
        channel_id: str,
        original_query: str,
    ) -> None:
        """Execute an investigation in the background and post the result.

        Args:
            prompt: The research prompt for the worker.
            project_path: Working directory for the subprocess.
            channel_id: Slack channel to post the result to.
            original_query: The user's original query for context.
        """
        try:
            result = await asyncio.to_thread(
                self._claude_worker.execute,  # type: ignore[union-attr]
                prompt,
                project_path,
                task_type="research",
            )

            if result.success:
                # Truncate long output for Slack (4000 char limit)
                output = result.output[:3800]
                response = (
                    f"*Investigation complete* ({result.duration:.1f}s):\n"
                    f"> {original_query[:100]}\n\n"
                    f"{output}"
                )
            else:
                response = (
                    f"*Investigation failed* ({result.duration:.1f}s):\n"
                    f"> {original_query[:100]}\n\n"
                    f"Error: {result.error}"
                )

            # Post buffered result back to Slack
            if self.slack_bot and hasattr(self.slack_bot, "post_message"):
                await self.slack_bot.post_message(response)  # type: ignore[attr-defined]
            else:
                logger.info("Investigation result (no Slack bot): %s", response[:200])

            # Log to memory
            await asyncio.to_thread(
                self.memory.remember,
                "observation",
                f"Investigation: {original_query[:120]} → "
                f"{'success' if result.success else 'failed'}",
            )

        except Exception:
            logger.exception("Investigation failed for: %s", original_query[:100])

    async def _handle_approve(self, proposal_id: str) -> str:
        """Approve a pending proposal by ID.

        Args:
            proposal_id: Proposal ID to approve.

        Returns:
            Result message.
        """
        if not self.proposal_manager:
            return "Proposal system not configured."

        from nebulus_swarm.overlord.proposal_manager import ProposalState

        proposal = self.proposal_manager.store.get(proposal_id)
        if not proposal:
            return f"Proposal `{proposal_id}` not found."
        if not proposal.is_pending:
            return f"Proposal `{proposal_id}` is {proposal.state.value}, not pending."

        self.proposal_manager.store.update_state(proposal_id, ProposalState.APPROVED)
        result = await self.proposal_manager.execute_approved(proposal_id)
        if result and result.status == "success":
            return f"Proposal `{proposal_id}` approved and executed successfully."
        elif result:
            return f"Proposal `{proposal_id}` approved but failed: {result.reason}"
        return f"Proposal `{proposal_id}` approved (no execution plan cached)."

    async def _handle_deny(self, proposal_id: str) -> str:
        """Deny a pending proposal by ID.

        Args:
            proposal_id: Proposal ID to deny.

        Returns:
            Result message.
        """
        if not self.proposal_manager:
            return "Proposal system not configured."

        from nebulus_swarm.overlord.proposal_manager import ProposalState

        proposal = self.proposal_manager.store.get(proposal_id)
        if not proposal:
            return f"Proposal `{proposal_id}` not found."
        if not proposal.is_pending:
            return f"Proposal `{proposal_id}` is {proposal.state.value}, not pending."

        self.proposal_manager.store.update_state(
            proposal_id, ProposalState.DENIED, result_summary="Denied via command"
        )
        return f"Proposal `{proposal_id}` denied."

    @property
    def _llm_enabled(self) -> bool:
        """Check if LLM fallback is enabled."""
        return self._llm_config.enabled

    @property
    def _client(self) -> AsyncOpenAI:
        """Get or create the AsyncOpenAI client (lazy init)."""
        if self._llm_client is None:
            self._llm_client = AsyncOpenAI(
                base_url=self._llm_config.base_url,
                api_key="not-needed",
                timeout=self._llm_config.timeout,
            )
        return self._llm_client

    async def _get_ecosystem(self) -> list:
        """Return cached ecosystem scan results, refreshing if stale."""
        now = time.monotonic()
        if self._ecosystem_cache is None or (now - self._cache_ts) > self._CACHE_TTL:
            self._ecosystem_cache = await asyncio.to_thread(scan_ecosystem, self.config)
            self._cache_ts = now
        return self._ecosystem_cache

    def _build_system_prompt(self, ecosystem: list, memory_results: list) -> str:
        """Build the system prompt with ecosystem state and memory.

        Args:
            ecosystem: List of ProjectStatus from scan_ecosystem.
            memory_results: List of memory entries from search.

        Returns:
            System prompt string for the LLM.
        """
        # Project summaries
        project_lines = []
        for status in ecosystem:
            clean = "clean" if status.git.clean else "dirty"
            line = f"- {status.name}: branch={status.git.branch}, {clean}"
            if status.git.ahead:
                line += f", {status.git.ahead} ahead"
            if status.issues:
                line += f", issues: {'; '.join(status.issues)}"
            project_lines.append(line)
        projects_text = "\n".join(project_lines) if project_lines else "(no projects)"

        # Memory entries
        memory_lines = []
        for entry in memory_results:
            proj = entry.project or "global"
            memory_lines.append(f"- [{proj}] {entry.content[:120]}")
        memory_text = (
            "\n".join(memory_lines) if memory_lines else "(no recent observations)"
        )

        prompt = (
            "You are Overlord, the ecosystem orchestrator for Nebulus AI Labs.\n"
            f"You manage {len(ecosystem)} projects. Current state:\n\n"
            f"{projects_text}\n\n"
            f"Recent observations:\n{memory_text}\n\n"
            "The user can also run these commands directly:\n"
            "status [project], scan [project], merge <project> <src> to <target>, "
            "release <project> <version>, autonomy [level], memory <query>, help\n\n"
            "Answer concisely. If a command would help, suggest it.\n"
            "Do not generate destructive shell commands."
        )

        if self._ai_directives:
            prompt += (
                "\n\nProject standards (follow these when answering):\n"
                f"{self._ai_directives}"
            )

        return prompt

    async def _handle_llm_fallback(
        self, text: str, user_id: str, channel_id: str
    ) -> str:
        """Handle unrecognized text via LLM chat.

        Args:
            text: The unrecognized user message.
            user_id: Slack user ID.
            channel_id: Slack channel ID.

        Returns:
            LLM response or graceful fallback message.
        """
        if not self._llm_enabled:
            return f"Unknown command: `{text}`\nType `help` to see available commands."

        try:
            # Gather context
            ecosystem = await self._get_ecosystem()
            memory_results = await asyncio.to_thread(self.memory.search, text, limit=5)

            system_prompt = self._build_system_prompt(ecosystem, memory_results)

            # Build messages with conversation history
            messages: list[dict[str, str]] = [
                {"role": "system", "content": system_prompt}
            ]
            history = self._chat_history.get(channel_id, [])
            messages.extend(history)
            messages.append({"role": "user", "content": text})

            # Call LLM
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._llm_config.model,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.7,
                ),
                timeout=15.0,
            )

            content = response.choices[0].message.content or ""

            # Update conversation history (sliding window of 5 exchanges)
            if channel_id not in self._chat_history:
                self._chat_history[channel_id] = []
            self._chat_history[channel_id].append({"role": "user", "content": text})
            self._chat_history[channel_id].append(
                {"role": "assistant", "content": content}
            )
            # Keep last 10 messages (5 exchanges)
            self._chat_history[channel_id] = self._chat_history[channel_id][-10:]

            # Validate LLM-suggested commands before returning
            return self._command_validator.annotate_response(content)

        except asyncio.TimeoutError:
            logger.warning("LLM chat fallback timed out for: %s", text[:100])
            return (
                f"⏱️ LLM timed out ({self._llm_config.timeout}s). "
                f"Endpoint: `{self._llm_config.base_url}`\n"
                "Check if your LLM service is running. Type `help` for commands."
            )
        except Exception as e:
            logger.warning("LLM chat fallback failed: %s", e)
            return (
                f"⚠️ LLM unavailable: `{type(e).__name__}`\n"
                f"Endpoint: `{self._llm_config.base_url}`\n"
                "Type `help` for available commands."
            )

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
            "  `memory <query> [cat:<category>] [proj:<project>]` — search memory with optional filters\n"
            "  `roadmap` — show active tracks, critical path, and priorities\n"
            "  `investigate <question>` — research a question (async, posts result when done)\n"
            "  `approve <id>` — approve a pending proposal\n"
            "  `deny <id>` — deny a pending proposal\n"
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


# --- Roadmap parsing helpers ---

_RE_MD_TABLE_ROW = re.compile(r"^\|(.+)\|$")
_RE_MD_CHECKBOX = re.compile(r"^- \[([ xX])\] \*\*(.+?)\*\*")


def _parse_overlord_md_section(path: Path, section_name: str) -> list[str]:
    """Extract table rows from a named section in a Markdown file.

    Args:
        path: Path to the Markdown file.
        section_name: Heading text to find (e.g. "Critical Path").

    Returns:
        List of formatted strings, one per table row (excluding header/separator).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines: list[str] = []
    in_section = False
    header_skipped = False

    for line in content.splitlines():
        stripped = line.strip()

        # Detect section start
        if stripped.startswith("#") and section_name in stripped:
            in_section = True
            header_skipped = False
            continue

        # Detect next section (stop)
        if in_section and stripped.startswith("#"):
            break

        if not in_section:
            continue

        # Parse table rows
        m = _RE_MD_TABLE_ROW.match(stripped)
        if m:
            cells = [c.strip() for c in m.group(1).split("|")]
            # Skip header row and separator row (---|---)
            if any("---" in c for c in cells):
                header_skipped = True
                continue
            if not header_skipped:
                header_skipped = True
                continue
            # Format: "Phase | Description | Status" or similar
            lines.append(" | ".join(c for c in cells if c))

    return lines


def _parse_tracks_md(path: Path) -> list[str]:
    """Parse conductor/tracks.md for track names and status.

    Args:
        path: Path to tracks.md.

    Returns:
        List of formatted track strings.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines: list[str] = []
    for line in content.splitlines():
        m = _RE_MD_CHECKBOX.match(line.strip())
        if m:
            done = m.group(1).lower() == "x"
            name = m.group(2).strip()
            icon = "done" if done else "pending"
            lines.append(f"[{icon}] {name}")

    return lines


def _parse_track_plans(tracks_dir: Path) -> list[str]:
    """Parse plan.md files in each track directory for task completion counts.

    Args:
        tracks_dir: Path to conductor/tracks/ directory.

    Returns:
        List of formatted progress strings.
    """
    lines: list[str] = []
    for plan_path in sorted(tracks_dir.glob("*/plan.md")):
        track_name = plan_path.parent.name
        try:
            content = plan_path.read_text(encoding="utf-8")
        except OSError:
            continue

        total = 0
        done = 0
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ["):
                total += 1
                if stripped.startswith("- [x]") or stripped.startswith("- [X]"):
                    done += 1

        if total > 0:
            lines.append(f"{track_name}: {done}/{total} tasks done")

    return lines


# --- Command validation ---

# Known Overlord Slack commands for guardrail validation.
KNOWN_COMMANDS: frozenset[str] = frozenset(
    {
        "status",
        "scan",
        "merge",
        "release",
        "autonomy",
        "memory",
        "roadmap",
        "investigate",
        "approve",
        "deny",
        "help",
    }
)

# Known autonomy levels
KNOWN_AUTONOMY_LEVELS: frozenset[str] = frozenset(
    {"cautious", "proactive", "scheduled"}
)


class CommandValidator:
    """Validates LLM-suggested commands against the known command registry.

    Prevents hallucinated commands like 'autonomy high' from reaching
    the user. Used as a post-filter on LLM fallback responses.
    """

    def __init__(self, config: "OverlordConfig") -> None:
        self._project_names: set[str] = set(config.projects.keys())

    def validate_suggestion(self, text: str) -> list[str]:
        """Check LLM response text for invalid command suggestions.

        Scans for backtick-wrapped commands and validates them against
        the known command registry.

        Args:
            text: LLM response text to validate.

        Returns:
            List of warning strings for invalid commands found.
            Empty list if all commands are valid.
        """
        warnings: list[str] = []
        # Find backtick-wrapped command suggestions
        for match in re.finditer(r"`([^`]+)`", text):
            candidate = match.group(1).strip()
            tokens = candidate.split()
            if not tokens:
                continue

            cmd = tokens[0].lower()
            if cmd not in KNOWN_COMMANDS:
                continue  # Not an Overlord command reference

            # Validate arguments for known commands
            if cmd == "autonomy" and len(tokens) > 1:
                level = tokens[1].lower()
                if level not in KNOWN_AUTONOMY_LEVELS:
                    warnings.append(
                        f"Invalid autonomy level `{tokens[1]}`. "
                        f"Valid: {', '.join(sorted(KNOWN_AUTONOMY_LEVELS))}"
                    )

            if cmd in ("status", "scan") and len(tokens) > 1:
                proj = tokens[1]
                if proj not in self._project_names:
                    warnings.append(f"Unknown project `{proj}` in `{candidate}`")

        return warnings

    def annotate_response(self, text: str) -> str:
        """Validate and annotate an LLM response with warnings.

        Args:
            text: LLM response text.

        Returns:
            Original text with appended warnings, or unmodified if valid.
        """
        warnings = self.validate_suggestion(text)
        if not warnings:
            return text
        correction = "\n".join(f"  - {w}" for w in warnings)
        return (
            f"{text}\n\n_Note: Some suggested commands may be incorrect:_\n{correction}"
        )
