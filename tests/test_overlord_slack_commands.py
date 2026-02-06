"""Tests for Overlord Slack Command Router."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.slack_commands import (
    SlackCommandRouter,
    _format_ecosystem_status,
    _format_project_status,
    _format_scan_detail,
    _unknown_project,
)


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


def _make_router(tmp_path: Path) -> SlackCommandRouter:
    """Build a SlackCommandRouter with test config."""
    config = _make_config(tmp_path)
    return SlackCommandRouter(config)


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
        with patch("nebulus_swarm.overlord.slack_commands.scan_ecosystem") as mock_scan:
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

        with patch(
            "nebulus_swarm.overlord.slack_commands.scan_ecosystem",
            return_value=[mock_status],
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
        with patch("nebulus_swarm.overlord.slack_commands.scan_ecosystem") as mock_scan:
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
    async def test_llm_timeout_returns_graceful_error(self, tmp_path: Path) -> None:
        """LLM timeout returns a graceful fallback message."""
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
            assert "couldn't process that" in result
            assert "help" in result

    @pytest.mark.asyncio
    async def test_llm_exception_returns_graceful_error(self, tmp_path: Path) -> None:
        """LLM exception returns a graceful fallback message."""
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
            assert "couldn't process that" in result
            assert "help" in result

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

        with patch(
            "nebulus_swarm.overlord.slack_commands.scan_ecosystem",
            return_value=[],
        ):
            result = await router.handle("status", "U123", "C456")
            assert "Ecosystem Status" in result
            # LLM client should never have been initialized
            assert router._llm_client is None

    @pytest.mark.asyncio
    async def test_greeting_handled_without_llm(self, tmp_path: Path) -> None:
        """Greetings are pattern-matched, not sent to LLM."""
        router = _make_router(tmp_path)
        result = await router.handle("hello", "U123", "C456")
        assert "Overlord" in result
        assert router._llm_client is None
