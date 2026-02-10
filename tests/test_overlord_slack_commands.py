"""Tests for Overlord Slack Command Router."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.slack_commands import (
    KNOWN_COMMANDS,
    CommandValidator,
    SlackCommandRouter,
    _RE_AGENT_UPDATE,
    _RE_STRUCTURED_REPORT,
    _RE_UPDATE,
    _format_ecosystem_status,
    _format_project_status,
    _format_scan_detail,
    _parse_overlord_md_section,
    _parse_track_plans,
    _parse_tracks_md,
    _unknown_project,
)
from nebulus_swarm.overlord.task_parser import InvestigationTask, TaskParser


def _make_config(tmp_path: Path) -> OverlordConfig:
    """Build a test config with temporary directories."""
    projects = {}
    for name, role, deps in [
        ("core", "shared-library", []),
        ("prime", "platform-deployment", ["core"]),
        ("edge", "platform-deployment", ["core"]),
    ]:
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        projects[name] = ProjectConfig(
            name=name,
            path=d,
            remote=f"test/{name}",
            role=role,
            depends_on=deps,
        )

    return OverlordConfig(
        projects=projects,
        autonomy_global="cautious",
        models={
            "local": {
                "endpoint": "http://localhost:5000",
                "model": "test",
                "tier": "local",
            }
        },
    )


def _make_router(
    tmp_path: Path, workspace_root: Path | None = None
) -> SlackCommandRouter:
    """Build a SlackCommandRouter with test config."""
    config = _make_config(tmp_path)
    return SlackCommandRouter(config, workspace_root=workspace_root)


# --- Command Parsing Tests ---


class TestCommandParsing:
    """Tests for command parsing and routing."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_help(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("", "U123", "C456")
        assert "Overlord Commands" in result

    @pytest.mark.asyncio
    async def test_help_command(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("help", "U123", "C456")
        assert "status" in result
        assert "scan" in result
        assert "merge" in result
        assert "release" in result
        assert "autonomy" in result
        assert "memory" in result

    @pytest.mark.asyncio
    async def test_help_case_insensitive(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("HELP", "U123", "C456")
        assert "Overlord Commands" in result

    @pytest.mark.asyncio
    async def test_unknown_command_llm_disabled(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        router._llm_config.enabled = False
        result = await router.handle("foobar", "U123", "C456")
        assert "Unknown command" in result
        assert "foobar" in result

    @pytest.mark.asyncio
    async def test_status_routes_correctly(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with (
            patch("nebulus_swarm.overlord.slack_commands.scan_ecosystem") as mock_scan,
            patch.object(
                router,
                "_get_llm_health_line",
                new_callable=AsyncMock,
                return_value="LLM Fallback: disabled",
            ),
        ):
            mock_scan.return_value = []
            await router.handle("status", "U123", "C456")
            mock_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_routes_correctly(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch("nebulus_swarm.overlord.slack_commands.scan_ecosystem") as mock_scan:
            mock_scan.return_value = []
            await router.handle("scan", "U123", "C456")
            mock_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_autonomy_routes_correctly(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("autonomy", "U123", "C456")
        assert "cautious" in result


# --- Handler Execution Tests ---


class TestHandlerExecution:
    """Tests for handler execution with mocked Phase 2 modules."""

    @pytest.mark.asyncio
    async def test_status_ecosystem(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []
        mock_status.git = MagicMock(
            branch="develop", clean=True, last_commit="test commit", ahead=0
        )

        with (
            patch(
                "nebulus_swarm.overlord.slack_commands.scan_ecosystem",
                return_value=[mock_status],
            ),
            patch.object(
                router,
                "_get_llm_health_line",
                new_callable=AsyncMock,
                return_value="LLM Fallback: disabled",
            ),
        ):
            result = await router.handle("status", "U123", "C456")
            assert "Ecosystem Status" in result
            assert "core" in result

    @pytest.mark.asyncio
    async def test_status_single_project(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []
        mock_status.git = MagicMock(
            branch="develop", clean=True, last_commit="test commit", ahead=0
        )

        with patch(
            "nebulus_swarm.overlord.slack_commands.scan_project",
            return_value=mock_status,
        ):
            result = await router.handle("status core", "U123", "C456")
            assert "core" in result

    @pytest.mark.asyncio
    async def test_status_unknown_project(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("status nonexistent", "U123", "C456")
        assert "Unknown project" in result
        assert "nonexistent" in result

    @pytest.mark.asyncio
    async def test_scan_single_project(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        mock_status = MagicMock()
        mock_status.name = "prime"
        mock_status.issues = ["Dirty working tree"]
        mock_status.git = MagicMock(
            branch="develop",
            clean=False,
            last_commit="wip",
            ahead=2,
            behind=0,
            stale_branches=["old-feature"],
            tags=["v1.0.0"],
        )
        mock_status.tests = MagicMock(has_tests=True, test_command="pytest")

        with patch(
            "nebulus_swarm.overlord.slack_commands.scan_project",
            return_value=mock_status,
        ):
            result = await router.handle("scan prime", "U123", "C456")
            assert "prime" in result
            assert "Dirty" in result

    @pytest.mark.asyncio
    async def test_scan_unknown_project(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("scan nonexistent", "U123", "C456")
        assert "Unknown project" in result

    @pytest.mark.asyncio
    async def test_dispatch_merge(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        mock_plan = MagicMock()
        mock_plan.task = "merge core develop to main"
        mock_plan.steps = [MagicMock()]
        mock_plan.scope = MagicMock(projects=["core"], estimated_impact="low")
        mock_plan.requires_approval = False

        mock_result = MagicMock()
        mock_result.status = "success"

        with (
            patch.object(router.task_parser, "parse", return_value=mock_plan),
            patch.object(router.dispatch, "execute", return_value=mock_result),
        ):
            result = await router.handle("merge core develop to main", "U123", "C456")
            assert "completed successfully" in result

    @pytest.mark.asyncio
    async def test_dispatch_requires_approval(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        mock_plan = MagicMock()
        mock_plan.task = "merge core develop to main"
        mock_plan.steps = [MagicMock()]
        mock_plan.scope = MagicMock(projects=["core"], estimated_impact="high")
        mock_plan.requires_approval = True

        with patch.object(router.task_parser, "parse", return_value=mock_plan):
            result = await router.handle("merge core develop to main", "U123", "C456")
            assert "approval" in result.lower()

    @pytest.mark.asyncio
    async def test_release_command(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        mock_plan = MagicMock()
        mock_plan.steps = [MagicMock()]
        mock_plan.scope = MagicMock(projects=["core"], estimated_impact="high")
        mock_plan.requires_approval = True

        with (
            patch(
                "nebulus_swarm.overlord.slack_commands.validate_release_spec",
                return_value=[],
            ),
            patch.object(
                router.release_coordinator, "plan_release", return_value=mock_plan
            ),
        ):
            result = await router.handle("release core v1.0.0", "U123", "C456")
            assert "core" in result
            assert "v1.0.0" in result

    @pytest.mark.asyncio
    async def test_release_unknown_project(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("release unknown v1.0.0", "U123", "C456")
        assert "Unknown project" in result

    @pytest.mark.asyncio
    async def test_autonomy_show_current(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("autonomy", "U123", "C456")
        assert "cautious" in result
        assert "core" in result
        assert "prime" in result

    @pytest.mark.asyncio
    async def test_autonomy_describe_level(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("autonomy proactive", "U123", "C456")
        assert "Proactive" in result
        assert "auto-execute" in result

    @pytest.mark.asyncio
    async def test_autonomy_invalid_level(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        result = await router.handle("autonomy banana", "U123", "C456")
        assert "Unknown autonomy level" in result

    @pytest.mark.asyncio
    async def test_memory_search(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "search", return_value=[]):
            result = await router.handle("memory release", "U123", "C456")
            assert "No memories found" in result


# --- Async Wrapping Tests ---


class TestAsyncWrapping:
    """Tests for async bridging of sync Phase 2 modules."""

    @pytest.mark.asyncio
    async def test_scan_runs_in_thread(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with (
            patch("nebulus_swarm.overlord.slack_commands.scan_ecosystem") as mock_scan,
            patch.object(
                router,
                "_get_llm_health_line",
                new_callable=AsyncMock,
                return_value="LLM Fallback: disabled",
            ),
        ):
            mock_scan.return_value = []
            await router.handle("status", "U123", "C456")
            # Verify scan_ecosystem was called (via to_thread)
            mock_scan.assert_called_once_with(router.config)

    @pytest.mark.asyncio
    async def test_memory_search_runs_in_thread(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "search", return_value=[]) as mock:
            await router.handle("memory test", "U123", "C456")
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_parse_runs_in_thread(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        mock_plan = MagicMock()
        mock_plan.task = "merge core develop to main"
        mock_plan.steps = []
        mock_plan.scope = MagicMock(projects=["core"], estimated_impact="low")
        mock_plan.requires_approval = True

        with patch.object(router.task_parser, "parse", return_value=mock_plan) as mock:
            await router.handle("merge core develop to main", "U123", "C456")
            mock.assert_called_once()


# --- Error Handling Tests ---


class TestErrorHandling:
    """Tests for error handling in command processing."""

    @pytest.mark.asyncio
    async def test_scan_exception_returns_error(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch(
            "nebulus_swarm.overlord.slack_commands.scan_ecosystem",
            side_effect=RuntimeError("git not found"),
        ):
            result = await router.handle("status", "U123", "C456")
            assert "Error" in result
            assert "git not found" in result

    @pytest.mark.asyncio
    async def test_dispatch_parse_error(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(
            router.task_parser,
            "parse",
            side_effect=ValueError("cannot parse"),
        ):
            result = await router.handle("merge core develop to main", "U123", "C456")
            assert "Failed to parse" in result

    @pytest.mark.asyncio
    async def test_release_validation_errors(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch(
            "nebulus_swarm.overlord.slack_commands.validate_release_spec",
            return_value=["Version must start with v"],
        ):
            result = await router.handle("release core 1.0", "U123", "C456")
            assert "validation failed" in result.lower()


# --- Response Formatting Tests ---


class TestResponseFormatting:
    """Tests for Slack response formatting."""

    def test_format_project_status_healthy(self) -> None:
        mock = MagicMock()
        mock.name = "core"
        mock.issues = []
        mock.git = MagicMock(
            branch="develop", clean=True, last_commit="initial commit", ahead=0
        )
        result = _format_project_status(mock)
        assert "🟢" in result
        assert "core" in result
        assert "develop" in result

    def test_format_project_status_with_issues(self) -> None:
        mock = MagicMock()
        mock.name = "prime"
        mock.issues = ["Dirty working tree"]
        mock.git = MagicMock(branch="develop", clean=False, last_commit="wip", ahead=3)
        result = _format_project_status(mock)
        assert "🟡" in result
        assert "dirty" in result
        assert "Ahead: 3" in result

    def test_format_ecosystem_status(self) -> None:
        healthy = MagicMock()
        healthy.name = "core"
        healthy.issues = []
        healthy.git = MagicMock(branch="develop", clean=True)

        unhealthy = MagicMock()
        unhealthy.name = "prime"
        unhealthy.issues = ["dirty"]
        unhealthy.git = MagicMock(branch="main", clean=False)

        result = _format_ecosystem_status([healthy, unhealthy])
        assert "1/2 healthy" in result
        assert "core" in result
        assert "prime" in result

    def test_format_scan_detail(self) -> None:
        mock = MagicMock()
        mock.name = "edge"
        mock.issues = []
        mock.git = MagicMock(
            branch="develop",
            clean=True,
            ahead=0,
            behind=0,
            last_commit="commit msg",
            stale_branches=[],
            tags=["v1.0.0"],
        )
        mock.tests = MagicMock(has_tests=True, test_command="pytest")
        result = _format_scan_detail(mock)
        assert "edge" in result
        assert "pytest" in result

    def test_unknown_project_formatting(self) -> None:
        config = OverlordConfig(
            projects={
                "core": ProjectConfig(
                    name="core", path=Path("/tmp"), remote="r", role="tooling"
                )
            }
        )
        result = _unknown_project("nope", config)
        assert "Unknown project" in result
        assert "nope" in result
        assert "core" in result


# --- LLM Chat Fallback Tests ---


def _mock_llm_response(content: str) -> MagicMock:
    """Build a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


class TestLLMFallback:
    """Tests for the LLM chat fallback feature."""

    @pytest.mark.asyncio
    async def test_llm_fallback_called_for_unrecognized_text(
        self, tmp_path: Path
    ) -> None:
        """Unrecognized text routes to LLM when enabled."""
        router = _make_router(tmp_path)
        mock_response = _mock_llm_response("Here's what I think...")

        with (
            patch.object(
                router, "_get_ecosystem", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(router.memory, "search", return_value=[]),
            patch("nebulus_swarm.overlord.slack_commands.AsyncOpenAI"),
        ):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            router._llm_client = mock_client

            result = await router.handle(
                "What projects have dirty branches?", "U123", "C456"
            )
            assert result == "Here's what I think..."
            mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_disabled_returns_unknown_command(self, tmp_path: Path) -> None:
        """When LLM is disabled, unrecognized text returns 'Unknown command'."""
        router = _make_router(tmp_path)
        router._llm_config.enabled = False
        result = await router.handle("What should I work on?", "U123", "C456")
        assert "Unknown command" in result

    @pytest.mark.asyncio
    async def test_llm_timeout_returns_diagnostic_error(self, tmp_path: Path) -> None:
        """LLM timeout returns a diagnostic message with endpoint info."""
        router = _make_router(tmp_path)

        with (
            patch.object(
                router, "_get_ecosystem", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(router.memory, "search", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=asyncio.TimeoutError()
            )
            router._llm_client = mock_client

            result = await router.handle("Tell me something", "U123", "C456")
            assert "timed out" in result
            assert "help" in result.lower()

    @pytest.mark.asyncio
    async def test_llm_exception_returns_diagnostic_error(self, tmp_path: Path) -> None:
        """LLM exception returns a diagnostic message with error type."""
        router = _make_router(tmp_path)

        with (
            patch.object(
                router, "_get_ecosystem", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(router.memory, "search", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=RuntimeError("connection refused")
            )
            router._llm_client = mock_client

            result = await router.handle("Tell me something", "U123", "C456")
            assert "RuntimeError" in result
            assert "help" in result.lower()

    @pytest.mark.asyncio
    async def test_context_includes_project_data(self, tmp_path: Path) -> None:
        """System prompt includes project status information."""
        router = _make_router(tmp_path)

        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []
        mock_status.git = MagicMock(branch="develop", clean=True, ahead=0)

        mock_response = _mock_llm_response("All good.")

        with (
            patch.object(
                router,
                "_get_ecosystem",
                new_callable=AsyncMock,
                return_value=[mock_status],
            ),
            patch.object(router.memory, "search", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            router._llm_client = mock_client

            await router.handle("How are things?", "U123", "C456")

            # Verify system prompt contains project info
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            system_msg = messages[0]["content"]
            assert "core" in system_msg
            assert "develop" in system_msg

    @pytest.mark.asyncio
    async def test_context_includes_memory_results(self, tmp_path: Path) -> None:
        """System prompt includes memory search results."""
        router = _make_router(tmp_path)

        mock_entry = MagicMock()
        mock_entry.project = "prime"
        mock_entry.content = "Tests failing on prime after last deploy"

        mock_response = _mock_llm_response("Noted.")

        with (
            patch.object(
                router, "_get_ecosystem", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(router.memory, "search", return_value=[mock_entry]),
        ):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            router._llm_client = mock_client

            await router.handle("Any issues?", "U123", "C456")

            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            system_msg = messages[0]["content"]
            assert "Tests failing on prime" in system_msg

    @pytest.mark.asyncio
    async def test_known_commands_use_pattern_matching(self, tmp_path: Path) -> None:
        """Known commands like 'status' bypass LLM entirely."""
        router = _make_router(tmp_path)

        with (
            patch(
                "nebulus_swarm.overlord.slack_commands.scan_ecosystem",
                return_value=[],
            ),
            patch.object(
                router,
                "_get_llm_health_line",
                new_callable=AsyncMock,
                return_value="LLM Fallback: disabled",
            ),
        ):
            result = await router.handle("status", "U123", "C456")
            assert "Ecosystem Status" in result

    @pytest.mark.asyncio
    async def test_greeting_handled_without_llm(self, tmp_path: Path) -> None:
        """Greetings are pattern-matched, not sent to LLM."""
        router = _make_router(tmp_path)
        result = await router.handle("hello", "U123", "C456")
        assert "Overlord" in result
        assert router._llm_client is None


# --- Update Recognition Tests ---


class TestUpdatePatterns:
    """Tests for _RE_UPDATE and _RE_STRUCTURED_REPORT patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "update",
            "Update: gantry frontend rebuilt",
            "status update on core migration",
            "report: all tests passing",
            "FYI pushed new branch",
            "heads up — breaking change in core",
            "headsup deploying now",
            "completed the Phase 4 integration",
            "complete — gantry dashboard live",
            "shipped v2.3.0",
            "deployed to production",
            "pushed 12 commits to develop",
        ],
    )
    def test_re_update_positive(self, text: str) -> None:
        assert _RE_UPDATE.search(text), f"Expected match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "status",
            "status core",
            "help",
            "scan prime",
            "What should I work on?",
            "hello",
        ],
    )
    def test_re_update_negative(self, text: str) -> None:
        assert not _RE_UPDATE.search(text), f"Unexpected match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "12 commits pushed to develop",
            "463 tests passed, zero regressions",
            "merged feat/slack-updates into develop",
            "shipped the new dashboard",
            "deployed gantry backend",
            "zero regressions across the suite",
        ],
    )
    def test_re_structured_report_positive(self, text: str) -> None:
        assert _RE_STRUCTURED_REPORT.search(text), f"Expected match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "What should I work on next?",
            "How are things?",
            "Tell me about core",
            "hello world",
        ],
    )
    def test_re_structured_report_negative(self, text: str) -> None:
        assert not _RE_STRUCTURED_REPORT.search(text), f"Unexpected match for: {text!r}"


class TestHandleUpdate:
    """Tests for the _handle_update fast path."""

    @pytest.mark.asyncio
    async def test_update_logs_to_memory(self, tmp_path: Path) -> None:
        """Update messages are logged to memory with category 'update'."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember") as mock_remember:
            await router.handle("shipped v2.3.0 for core", "U123", "C456")
            mock_remember.assert_called_once()
            call_args = mock_remember.call_args
            assert call_args[0][0] == "update"  # category
            assert "shipped v2.3.0 for core" in call_args[0][1]  # content
            assert call_args[1]["project"] == "core"

    @pytest.mark.asyncio
    async def test_update_returns_acknowledgment(self, tmp_path: Path) -> None:
        """Update handler returns a short acknowledgment with status emoji."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle("FYI deployed edge", "U123", "C456")
            assert "Logged" in result
            assert "edge" in result
            # Should have a status emoji prefix
            assert result[0] in "✅❌🔄📝"

    @pytest.mark.asyncio
    async def test_update_no_project_match(self, tmp_path: Path) -> None:
        """Update without a recognized project still logs."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember") as mock_remember:
            result = await router.handle("deployed the new widget", "U123", "C456")
            mock_remember.assert_called_once()
            call_args = mock_remember.call_args
            assert call_args[1]["project"] is None
            assert "Logged" in result

    @pytest.mark.asyncio
    async def test_update_bypasses_llm(self, tmp_path: Path) -> None:
        """Update messages do not trigger LLM fallback."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            await router.handle("update: core tests passing", "U123", "C456")
            assert router._llm_client is None

    @pytest.mark.asyncio
    async def test_structured_report_handled(self, tmp_path: Path) -> None:
        """Structured reports (e.g., 'commits pushed') hit the update path."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember") as mock_remember:
            result = await router.handle(
                "12 commits pushed to develop, 463 tests passed",
                "U123",
                "C456",
            )
            mock_remember.assert_called_once()
            assert "Logged" in result


class TestAIDirectives:
    """Tests for AI directives in the LLM system prompt."""

    def test_system_prompt_includes_directives(self, tmp_path: Path) -> None:
        """System prompt includes AI directives when available."""
        router = _make_router(tmp_path)
        router._ai_directives = "# Development Standards\n1. Use pytest."

        prompt = router._build_system_prompt([], [])
        assert "Project standards" in prompt
        assert "Development Standards" in prompt
        assert "Use pytest" in prompt

    def test_system_prompt_without_directives(self, tmp_path: Path) -> None:
        """System prompt works cleanly when directives are empty."""
        router = _make_router(tmp_path)
        router._ai_directives = ""

        prompt = router._build_system_prompt([], [])
        assert "Project standards" not in prompt
        assert "Overlord" in prompt

    def test_load_ai_directives_missing_file(self) -> None:
        """Gracefully returns empty string when file is missing."""
        with patch(
            "nebulus_swarm.overlord.slack_commands.Path.__truediv__",
        ) as mock_div:
            mock_path = MagicMock()
            mock_path.is_file.return_value = False
            mock_div.return_value = mock_path
            result = SlackCommandRouter._load_ai_directives()
            # Should not raise — returns empty or the real file's content
            assert isinstance(result, str)


# --- Memory Filter Tests ---


class TestMemoryFilters:
    """Tests for cat:/proj: filter parsing in memory commands."""

    def test_parse_cat_filter(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        query, cat, proj, err = router._parse_memory_filters("cat:update gantry")
        assert query == "gantry"
        assert cat == "update"
        assert proj is None
        assert err is None

    def test_parse_proj_filter(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        query, cat, proj, err = router._parse_memory_filters("proj:core release")
        assert query == "release"
        assert cat is None
        assert proj == "core"
        assert err is None

    def test_parse_both_filters(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        query, cat, proj, err = router._parse_memory_filters("cat:update proj:core")
        assert query == ""
        assert cat == "update"
        assert proj == "core"
        assert err is None

    def test_parse_invalid_category(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        _, _, _, err = router._parse_memory_filters("cat:invalid query")
        assert err is not None
        assert "Invalid category" in err
        assert "invalid" in err

    def test_parse_unknown_project(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        _, _, _, err = router._parse_memory_filters("proj:nonexistent query")
        assert err is not None
        assert "Unknown project" in err
        assert "nonexistent" in err

    def test_parse_plain_query(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        query, cat, proj, err = router._parse_memory_filters("plain query")
        assert query == "plain query"
        assert cat is None
        assert proj is None
        assert err is None

    @pytest.mark.asyncio
    async def test_handle_memory_with_cat_filter(self, tmp_path: Path) -> None:
        """memory cat:update calls search with category='update'."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "search", return_value=[]) as mock_search:
            await router.handle("memory cat:update", "U123", "C456")
            mock_search.assert_called_once_with(
                "", category="update", project=None, limit=5
            )

    @pytest.mark.asyncio
    async def test_handle_memory_with_both_filters(self, tmp_path: Path) -> None:
        """memory cat:update proj:core calls search with both filters."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "search", return_value=[]) as mock_search:
            await router.handle("memory cat:update proj:core", "U123", "C456")
            mock_search.assert_called_once_with(
                "", category="update", project="core", limit=5
            )

    @pytest.mark.asyncio
    async def test_handle_memory_invalid_cat_returns_error(
        self, tmp_path: Path
    ) -> None:
        """memory cat:bogus returns a validation error."""
        router = _make_router(tmp_path)
        result = await router.handle("memory cat:bogus", "U123", "C456")
        assert "Invalid category" in result
        assert "bogus" in result


# --- Roadmap Command Tests ---


def _make_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace with governance and conductor files."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    # OVERLORD.md with Critical Path section
    (ws / "OVERLORD.md").write_text(
        "# OVERLORD.md\n\n"
        "## Critical Path\n\n"
        "| Phase | Description | Status | Priority |\n"
        "|-------|-------------|--------|----------|\n"
        "| A | MCP Server Migration | Pending | 1 |\n"
        "| B | Gantry Refactor | Pending | 1 |\n"
    )

    # BUSINESS.md with Strategic Priorities
    (ws / "BUSINESS.md").write_text(
        "# BUSINESS.md\n\n"
        "## Strategic Priorities\n\n"
        "| Priority | Goal | Key Result |\n"
        "|----------|------|------------|\n"
        "| 1 | Ship appliance | End-to-end on Tier 1 |\n"
        "| 2 | Demo-ready UI | Fix 13 issues |\n"
    )

    # conductor/tracks.md
    conductor = ws / "conductor"
    conductor.mkdir()
    (conductor / "tracks.md").write_text(
        "# Project Tracks\n\n"
        "- [ ] **Track: Overlord Slack Intelligence**\n"
        "- [x] **Track: Schema Design**\n"
    )

    # conductor/tracks/track_a/plan.md
    tracks_dir = conductor / "tracks"
    tracks_dir.mkdir()
    track_a = tracks_dir / "track_a"
    track_a.mkdir()
    (track_a / "plan.md").write_text(
        "# Plan\n\n"
        "## Phase 1\n"
        "- [x] Task: Done thing\n"
        "- [ ] Task: Pending thing\n"
        "- [ ] Task: Another pending\n"
    )

    return ws


class TestRoadmapCommand:
    """Tests for the roadmap Slack command."""

    @pytest.mark.asyncio
    async def test_roadmap_no_workspace(self, tmp_path: Path) -> None:
        """Roadmap without workspace_root returns error."""
        router = _make_router(tmp_path)
        result = await router.handle("roadmap", "U123", "C456")
        assert "Workspace root not configured" in result

    @pytest.mark.asyncio
    async def test_roadmap_with_workspace(self, tmp_path: Path) -> None:
        """Roadmap with workspace reads governance files."""
        ws = _make_workspace(tmp_path)
        router = _make_router(tmp_path, workspace_root=ws)
        result = await router.handle("roadmap", "U123", "C456")
        assert "Critical Path" in result
        assert "MCP Server Migration" in result
        assert "Active Tracks" in result
        assert "Overlord Slack Intelligence" in result
        assert "Track Progress" in result
        assert "track_a: 1/3 tasks done" in result
        assert "Strategic Priorities" in result
        assert "Ship appliance" in result

    @pytest.mark.asyncio
    async def test_roadmap_case_insensitive(self, tmp_path: Path) -> None:
        """Roadmap command is case-insensitive."""
        ws = _make_workspace(tmp_path)
        router = _make_router(tmp_path, workspace_root=ws)
        result = await router.handle("ROADMAP", "U123", "C456")
        assert "Critical Path" in result

    @pytest.mark.asyncio
    async def test_roadmap_empty_workspace(self, tmp_path: Path) -> None:
        """Roadmap with empty workspace returns no-data message."""
        ws = tmp_path / "empty_ws"
        ws.mkdir()
        router = _make_router(tmp_path, workspace_root=ws)
        result = await router.handle("roadmap", "U123", "C456")
        assert "No roadmap data found" in result


class TestRoadmapParsers:
    """Tests for roadmap file parsing helpers."""

    def test_parse_overlord_md_critical_path(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        rows = _parse_overlord_md_section(ws / "OVERLORD.md", "Critical Path")
        assert len(rows) == 2
        assert "MCP Server Migration" in rows[0]
        assert "Pending" in rows[0]

    def test_parse_overlord_md_missing_section(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        rows = _parse_overlord_md_section(ws / "OVERLORD.md", "Nonexistent")
        assert rows == []

    def test_parse_overlord_md_missing_file(self, tmp_path: Path) -> None:
        rows = _parse_overlord_md_section(tmp_path / "nope.md", "Critical Path")
        assert rows == []

    def test_parse_tracks_md(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        tracks = _parse_tracks_md(ws / "conductor" / "tracks.md")
        assert len(tracks) == 2
        assert "[pending] Track: Overlord Slack Intelligence" in tracks[0]
        assert "[done] Track: Schema Design" in tracks[1]

    def test_parse_track_plans(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        plans = _parse_track_plans(ws / "conductor" / "tracks")
        assert len(plans) == 1
        assert "track_a: 1/3 tasks done" in plans[0]


class TestCommandValidator:
    """Tests for CommandValidator guardrails."""

    def test_valid_commands_pass(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        validator = CommandValidator(config)
        warnings = validator.validate_suggestion(
            "Try `status core` or `autonomy cautious`"
        )
        assert warnings == []

    def test_invalid_autonomy_level(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        validator = CommandValidator(config)
        warnings = validator.validate_suggestion("Try `autonomy high`")
        assert len(warnings) == 1
        assert "Invalid autonomy level" in warnings[0]
        assert "high" in warnings[0]

    def test_unknown_project_in_status(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        validator = CommandValidator(config)
        warnings = validator.validate_suggestion("Run `status nebulus-forge`")
        assert len(warnings) == 1
        assert "Unknown project" in warnings[0]

    def test_non_overlord_commands_ignored(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        validator = CommandValidator(config)
        warnings = validator.validate_suggestion("Run `cd ~/projects` and `ls`")
        assert warnings == []

    def test_annotate_response_clean(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        validator = CommandValidator(config)
        text = "Try `status core`"
        assert validator.annotate_response(text) == text

    def test_annotate_response_with_warnings(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        validator = CommandValidator(config)
        result = validator.annotate_response("Try `autonomy high`")
        assert "Note: Some suggested commands may be incorrect" in result
        assert "Invalid autonomy level" in result

    @pytest.mark.asyncio
    async def test_llm_fallback_uses_guardrails(self, tmp_path: Path) -> None:
        """LLM fallback responses are validated by CommandValidator."""
        router = _make_router(tmp_path)
        mock_response = _mock_llm_response("Try `autonomy high` for full control.")

        with (
            patch.object(
                router, "_get_ecosystem", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(router.memory, "search", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            router._llm_client = mock_client

            result = await router.handle("How do I enable automation?", "U123", "C456")
            assert "Note: Some suggested commands may be incorrect" in result
            assert "Invalid autonomy level" in result


# --- Roadmap OVERLORD.md Fallback Tests ---


def _make_workspace_no_tracks_md(tmp_path: Path) -> Path:
    """Create a workspace with OVERLORD.md but no conductor/tracks.md."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    (ws / "OVERLORD.md").write_text(
        "# OVERLORD.md\n\n"
        "## Critical Path\n\n"
        "| Phase | Description | Status | Priority |\n"
        "|-------|-------------|--------|----------|\n"
        "| A | MCP Migration | Pending | 1 |\n"
        "\n"
        "## Active Tracks\n\n"
        "| Track | Status | Priority | Link |\n"
        "|-------|--------|----------|------|\n"
        "| Overlord Slack Intel | In Progress | 3 | tracks/overlord_slack/ |\n"
        "| Forge Profile | Completed | 3 | tracks/forge/ |\n"
    )

    # conductor/tracks/ dir with plan.md (but no tracks.md)
    tracks_dir = ws / "conductor" / "tracks" / "overlord_slack"
    tracks_dir.mkdir(parents=True)
    (tracks_dir / "plan.md").write_text(
        "# Plan\n"
        "- [x] Task: Roadmap command\n"
        "- [x] Task: CommandValidator\n"
        "- [ ] Task: Workspace path\n"
    )

    return ws


class TestRoadmapFallback:
    """Tests for OVERLORD.md Active Tracks fallback when tracks.md is missing."""

    @pytest.mark.asyncio
    async def test_roadmap_reads_active_tracks_from_overlord_md(
        self, tmp_path: Path
    ) -> None:
        """When conductor/tracks.md is missing, falls back to OVERLORD.md Active Tracks."""
        ws = _make_workspace_no_tracks_md(tmp_path)
        router = _make_router(tmp_path, workspace_root=ws)
        result = await router.handle("roadmap", "U123", "C456")
        assert "Active Tracks" in result
        assert "Overlord Slack Intel" in result
        assert "In Progress" in result

    @pytest.mark.asyncio
    async def test_roadmap_shows_track_progress_without_tracks_md(
        self, tmp_path: Path
    ) -> None:
        """Track progress is shown even when conductor/tracks.md is missing."""
        ws = _make_workspace_no_tracks_md(tmp_path)
        router = _make_router(tmp_path, workspace_root=ws)
        result = await router.handle("roadmap", "U123", "C456")
        assert "Track Progress" in result
        assert "overlord_slack: 2/3 tasks done" in result


# --- Investigation Command Tests ---


class TestInvestigateCommand:
    """Tests for the investigate command dispatch."""

    @pytest.mark.asyncio
    async def test_investigate_no_worker(self, tmp_path: Path) -> None:
        """investigate without a Claude worker returns an error."""
        router = _make_router(tmp_path)
        result = await router.handle(
            "investigate why are tests failing?", "U123", "C456"
        )
        assert "not available" in result

    @pytest.mark.asyncio
    async def test_investigate_returns_ack(self, tmp_path: Path) -> None:
        """investigate with a worker returns immediate acknowledgment."""
        router = _make_router(tmp_path)
        mock_worker = MagicMock()
        mock_worker.available = True
        router._claude_worker = mock_worker

        # Patch asyncio.create_task so the background task doesn't actually run
        with patch("nebulus_swarm.overlord.slack_commands.asyncio.create_task"):
            result = await router.handle(
                "investigate why are core tests failing?", "U123", "C456"
            )
            assert "Investigating" in result
            assert "core" in result
            assert "I'll post results when ready" in result

    @pytest.mark.asyncio
    async def test_investigate_infers_project(self, tmp_path: Path) -> None:
        """investigate infers project name from query."""
        router = _make_router(tmp_path)
        mock_worker = MagicMock()
        mock_worker.available = True
        router._claude_worker = mock_worker

        with patch("nebulus_swarm.overlord.slack_commands.asyncio.create_task"):
            result = await router.handle(
                "investigate prime deployment issues", "U123", "C456"
            )
            assert "prime" in result

    @pytest.mark.asyncio
    async def test_investigate_in_known_commands(self) -> None:
        """investigate is in KNOWN_COMMANDS for guardrail validation."""
        assert "investigate" in KNOWN_COMMANDS


# --- InvestigationTask Schema Tests ---


class TestInvestigationTask:
    """Tests for InvestigationTask dataclass and TaskParser.parse_investigation."""

    def test_investigation_task_defaults(self) -> None:
        task = InvestigationTask(query="Why are tests failing?")
        assert task.task_type == "research"
        assert task.timeout == 600
        assert task.project is None
        assert task.tags == []

    def test_parse_investigation_infers_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        from nebulus_swarm.overlord.graph import DependencyGraph

        graph = DependencyGraph(config)
        parser = TaskParser(graph)
        task = parser.parse_investigation("What tests are failing in core?")
        assert task.project == "core"
        assert task.query == "What tests are failing in core?"

    def test_parse_investigation_tags_testing(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        from nebulus_swarm.overlord.graph import DependencyGraph

        graph = DependencyGraph(config)
        parser = TaskParser(graph)
        task = parser.parse_investigation("How do tests work in this repo?")
        assert "testing" in task.tags

    def test_parse_investigation_tags_debugging(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        from nebulus_swarm.overlord.graph import DependencyGraph

        graph = DependencyGraph(config)
        parser = TaskParser(graph)
        task = parser.parse_investigation("Why is there a bug in the scanner?")
        assert "debugging" in task.tags

    def test_parse_investigation_tags_architecture(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        from nebulus_swarm.overlord.graph import DependencyGraph

        graph = DependencyGraph(config)
        parser = TaskParser(graph)
        task = parser.parse_investigation("What is the architecture of the dispatch?")
        assert "architecture" in task.tags

    def test_parse_investigation_no_project(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        from nebulus_swarm.overlord.graph import DependencyGraph

        graph = DependencyGraph(config)
        parser = TaskParser(graph)
        task = parser.parse_investigation("How does Python GIL work?")
        assert task.project is None
        assert task.tags == []


# --- Agent Update Pattern Tests ---


class TestAgentUpdatePatterns:
    """Tests for _RE_AGENT_UPDATE and Slack-formatted update recognition."""

    @pytest.mark.parametrize(
        "text",
        [
            "*Track 6 Phase B — Situation Map Sidebar: Complete*",
            # "_Cross-Repo Integration Validation Complete_" matches via _RE_UPDATE (complete)
            "_Agent 3 — Status Update: Forge Wiki v2_",
            "_GAP-1 & GAP-2 Fix Complete — Dispatch Bridge Merged_",
            "Agent 2 — nebulus-prime P0 Security Remediation Complete",
            "Track 5 Phase A done",
            "Phase B integration shipped",
        ],
    )
    def test_agent_update_regex_positive(self, text: str) -> None:
        assert _RE_AGENT_UPDATE.search(text), f"Expected match for: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "status",
            "help",
            "What should I work on?",
            "hello world",
        ],
    )
    def test_agent_update_regex_negative(self, text: str) -> None:
        assert not _RE_AGENT_UPDATE.search(text), f"Unexpected match for: {text!r}"

    @pytest.mark.asyncio
    async def test_slack_formatted_update_hits_update_path(
        self, tmp_path: Path
    ) -> None:
        """Messages with Slack bold/italic formatting are routed to update handler."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle("*Track 6 Phase B — Complete*", "U123", "C456")
            assert "Logged" in result
            assert router._llm_client is None

    @pytest.mark.asyncio
    async def test_agent_update_bypasses_llm(self, tmp_path: Path) -> None:
        """Agent-formatted messages do not fall through to LLM."""
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle(
                "_Agent 3 — Forge Wiki v2 deployed_", "U123", "C456"
            )
            assert "Logged" in result
            assert router._llm_client is None


# --- Structured Update Parsing Tests ---


class TestStructuredUpdateParsing:
    """Tests for status extraction and test count parsing in _handle_update."""

    @pytest.mark.asyncio
    async def test_completed_status_emoji(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle(
                "Agent 2 — Security Remediation Complete", "U123", "C456"
            )
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_failed_status_emoji(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle(
                "Agent 1 — Track 3 build failed", "U123", "C456"
            )
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_in_progress_status_emoji(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle("Track 2 Phase A in progress", "U123", "C456")
            assert "🔄" in result

    @pytest.mark.asyncio
    async def test_generic_update_emoji(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle(
                "FYI pushed new branch for core", "U123", "C456"
            )
            assert "📝" in result

    @pytest.mark.asyncio
    async def test_test_count_extraction(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle(
                "Agent 2 — 73 new tests passing, Phase 5 complete",
                "U123",
                "C456",
            )
            assert "73 tests" in result
            assert "✅" in result

    @pytest.mark.asyncio
    async def test_test_count_total_passing(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember"):
            result = await router.handle(
                "407 total tests pass, zero regressions",
                "U123",
                "C456",
            )
            assert "407 tests" in result

    @pytest.mark.asyncio
    async def test_project_inference_in_update(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with patch.object(router.memory, "remember") as mock_remember:
            result = await router.handle(
                "Agent 1 — core migration complete", "U123", "C456"
            )
            assert "*core*" in result
            call_args = mock_remember.call_args
            assert call_args[1]["project"] == "core"


# --- LLM Fallback Diagnostic Tests ---


class TestLLMFallbackDiagnostics:
    """Tests for improved LLM error messages showing endpoint and error type."""

    @pytest.mark.asyncio
    async def test_timeout_shows_endpoint(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)

        with (
            patch.object(
                router, "_get_ecosystem", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(router.memory, "search", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=asyncio.TimeoutError()
            )
            router._llm_client = mock_client

            result = await router.handle("Tell me something", "U123", "C456")
            assert "timed out" in result
            assert self._get_base_url(router) in result
            assert "help" in result.lower()

    @pytest.mark.asyncio
    async def test_exception_shows_error_type(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)

        with (
            patch.object(
                router, "_get_ecosystem", new_callable=AsyncMock, return_value=[]
            ),
            patch.object(router.memory, "search", return_value=[]),
        ):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=ConnectionError("refused")
            )
            router._llm_client = mock_client

            result = await router.handle("Tell me something", "U123", "C456")
            assert "ConnectionError" in result
            assert self._get_base_url(router) in result
            assert "help" in result.lower()

    @staticmethod
    def _get_base_url(router: SlackCommandRouter) -> str:
        return router._llm_config.base_url


# --- LLM Health in Status Tests ---


class TestLLMHealthInStatus:
    """Tests for LLM health line in ecosystem status output."""

    @pytest.mark.asyncio
    async def test_status_includes_llm_health(self, tmp_path: Path) -> None:
        router = _make_router(tmp_path)
        with (
            patch(
                "nebulus_swarm.overlord.slack_commands.scan_ecosystem",
                return_value=[],
            ),
            patch.object(
                router,
                "_get_llm_health_line",
                new_callable=AsyncMock,
                return_value="LLM Fallback: ❌ unreachable (`http://localhost:5000/v1`)",
            ),
        ):
            result = await router.handle("status", "U123", "C456")
            assert "LLM Fallback" in result

    @pytest.mark.asyncio
    async def test_status_project_no_llm_health(self, tmp_path: Path) -> None:
        """Per-project status does NOT include LLM health line."""
        router = _make_router(tmp_path)
        mock_status = MagicMock()
        mock_status.name = "core"
        mock_status.issues = []
        mock_status.git = MagicMock(
            branch="develop", clean=True, last_commit="test", ahead=0
        )
        with patch(
            "nebulus_swarm.overlord.slack_commands.scan_project",
            return_value=mock_status,
        ):
            result = await router.handle("status core", "U123", "C456")
            assert "LLM Fallback" not in result


# --- Post Message Fix Tests ---


class TestPostMessageFix:
    """Tests for the post_message parameter fix."""

    @pytest.mark.asyncio
    async def test_investigation_posts_without_channel_kwarg(
        self, tmp_path: Path
    ) -> None:
        """_run_investigation calls post_message without channel= kwarg."""
        router = _make_router(tmp_path)
        mock_bot = AsyncMock()
        router.slack_bot = mock_bot

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = "Found the issue."
        mock_result.duration = 1.5

        mock_worker = MagicMock()
        mock_worker.execute.return_value = mock_result
        router._claude_worker = mock_worker

        await router._run_investigation(
            "test prompt", Path("/tmp"), "C456", "test query"
        )

        mock_bot.post_message.assert_called_once()
        call_args = mock_bot.post_message.call_args
        # Should NOT have channel= kwarg
        assert "channel" not in (call_args.kwargs or {})
