"""Tests for TurnProcessor - the core conversation turn handler."""

import json
import pytest

pytest.importorskip("openai")

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from nebulus_atom.controllers.turn_processor import (
    TurnProcessor,
    TurnCallbacks,
    TurnResult,
)
from nebulus_atom.models.cognition import TaskComplexity, CognitionResult


# ---------------------------------------------------------------------------
# Dataclass Tests
# ---------------------------------------------------------------------------


class TestTurnCallbacks:
    def test_defaults_are_none(self):
        cb = TurnCallbacks()
        assert cb.on_tdd_start is None
        assert cb.on_auto_mode_start is None
        assert cb.on_cognition_analysis is None


class TestTurnResult:
    def test_defaults(self):
        r = TurnResult()
        assert r.finished is True
        assert r.started_tdd is False
        assert r.started_auto_mode is False
        assert r.tdd_goal is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_processor():
    """Create a TurnProcessor with mocked dependencies."""
    openai_svc = MagicMock()
    view = MagicMock()
    view.print_agent_response = AsyncMock()
    view.print_error = AsyncMock()
    view.print_tool_output = AsyncMock()
    view.print_plan = AsyncMock()
    view.print_telemetry = AsyncMock()
    view.print_stream_start = MagicMock()
    view.print_stream_chunk = MagicMock()
    view.print_stream_end = MagicMock()
    view.print_thought = MagicMock()
    view.print_cognition = AsyncMock()
    view.ask_user_input = AsyncMock(return_value="user answer")
    view.create_spinner = MagicMock()
    # Make the spinner context manager work
    spinner_ctx = MagicMock()
    spinner_ctx.__enter__ = MagicMock(return_value=spinner_ctx)
    spinner_ctx.__exit__ = MagicMock(return_value=False)
    view.create_spinner.return_value = spinner_ctx

    parser = MagicMock()
    parser.extract_tool_calls = MagicMock(return_value=[])
    parser.normalize_tool_call = MagicMock()
    parser.clean_response_text = MagicMock(side_effect=lambda x: x.strip())

    proc = TurnProcessor(openai_svc, view, parser)
    return proc, openai_svc, view, parser


def _make_chunk(content=None, tool_calls=None, finish_reason=None):
    """Create a streaming chunk SimpleNamespace."""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _make_history(messages=None):
    """Create a mock history manager."""
    history = MagicMock()
    history.get.return_value = messages or []
    history.add = MagicMock()
    return history


# ---------------------------------------------------------------------------
# Init Tests
# ---------------------------------------------------------------------------


class TestTurnProcessorInit:
    def test_creates_default_parser(self):
        openai_svc = MagicMock()
        view = MagicMock()
        proc = TurnProcessor(openai_svc, view)
        assert proc._parser is not None

    def test_uses_provided_parser(self):
        openai_svc = MagicMock()
        view = MagicMock()
        parser = MagicMock()
        proc = TurnProcessor(openai_svc, view, parser)
        assert proc._parser is parser


# ---------------------------------------------------------------------------
# Spinner Text Tests
# ---------------------------------------------------------------------------


class TestGetSpinnerText:
    def test_tool_role(self):
        proc, *_ = _make_processor()
        assert proc._get_spinner_text("tool") == "Analyzing Tool Output..."

    def test_user_role(self):
        proc, *_ = _make_processor()
        assert proc._get_spinner_text("user") == "Processing Request..."

    def test_other_role(self):
        proc, *_ = _make_processor()
        assert proc._get_spinner_text("assistant") == "Thinking..."


# ---------------------------------------------------------------------------
# Delta Tool Call Processing Tests
# ---------------------------------------------------------------------------


class TestProcessDeltaToolCalls:
    def test_creates_new_entry(self):
        proc, *_ = _make_processor()
        delta_tc = SimpleNamespace(
            index=0,
            id="call_123",
            function=SimpleNamespace(name="read_file", arguments='{"path":'),
        )
        result = proc._process_delta_tool_calls([delta_tc], {})
        assert 0 in result
        assert result[0]["function"]["name"] == "read_file"
        assert result[0]["function"]["arguments"] == '{"path":'
        assert result[0]["id"] == "call_123"

    def test_appends_to_existing(self):
        proc, *_ = _make_processor()
        existing = {
            0: {
                "id": "call_123",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":'},
            }
        }
        delta_tc = SimpleNamespace(
            index=0,
            id=None,
            function=SimpleNamespace(name="", arguments='"foo"}'),
        )
        result = proc._process_delta_tool_calls([delta_tc], existing)
        assert result[0]["function"]["arguments"] == '{"path":"foo"}'

    def test_multiple_tool_calls(self):
        proc, *_ = _make_processor()
        deltas = [
            SimpleNamespace(
                index=0,
                id="call_1",
                function=SimpleNamespace(name="read_file", arguments="{}"),
            ),
            SimpleNamespace(
                index=1,
                id="call_2",
                function=SimpleNamespace(name="write_file", arguments="{}"),
            ),
        ]
        result = proc._process_delta_tool_calls(deltas, {})
        assert len(result) == 2
        assert result[0]["function"]["name"] == "read_file"
        assert result[1]["function"]["name"] == "write_file"


# ---------------------------------------------------------------------------
# Execute Single Tool Tests
# ---------------------------------------------------------------------------


class TestExecuteSingleTool:
    @pytest.mark.asyncio
    async def test_ask_user_with_question(self):
        proc, _, view, _ = _make_processor()
        view.ask_user_input = AsyncMock(return_value="yes")
        output, action = await proc._execute_single_tool(
            "ask_user", {"question": "Continue?"}, "sess", TurnCallbacks()
        )
        assert output == "yes"
        assert action is None
        view.ask_user_input.assert_called_once_with("Continue?")

    @pytest.mark.asyncio
    async def test_ask_user_no_question(self):
        proc, *_ = _make_processor()
        output, action = await proc._execute_single_tool(
            "ask_user", {}, "sess", TurnCallbacks()
        )
        assert "Error" in output
        assert action is None

    @pytest.mark.asyncio
    async def test_start_tdd(self):
        cb = TurnCallbacks(on_tdd_start=MagicMock())
        proc, *_ = _make_processor()
        output, action = await proc._execute_single_tool(
            "start_tdd", {"goal": "fix tests"}, "sess", cb
        )
        assert action == "tdd"
        assert "fix tests" in output
        cb.on_tdd_start.assert_called_once_with("fix tests")

    @pytest.mark.asyncio
    async def test_start_tdd_no_callback(self):
        proc, *_ = _make_processor()
        output, action = await proc._execute_single_tool(
            "start_tdd", {"goal": "fix"}, "sess", TurnCallbacks()
        )
        assert action == "tdd"

    @pytest.mark.asyncio
    async def test_execute_plan(self):
        cb = TurnCallbacks(on_auto_mode_start=MagicMock())
        proc, *_ = _make_processor()
        output, action = await proc._execute_single_tool("execute_plan", {}, "sess", cb)
        assert action == "auto_mode"
        cb.on_auto_mode_start.assert_called_once()

    @pytest.mark.asyncio
    @patch("nebulus_atom.controllers.turn_processor.ToolExecutor")
    async def test_regular_tool_dispatch(self, mock_executor):
        mock_executor.dispatch = AsyncMock(return_value="file contents here")
        proc, *_ = _make_processor()
        output, action = await proc._execute_single_tool(
            "read_file", {"path": "foo.py"}, "sess", TurnCallbacks()
        )
        assert output == "file contents here"
        assert action is None
        mock_executor.dispatch.assert_called_once_with(
            "read_file", {"path": "foo.py"}, session_id="sess"
        )


# ---------------------------------------------------------------------------
# Handle Text Response Tests
# ---------------------------------------------------------------------------


class TestHandleTextResponse:
    @pytest.mark.asyncio
    @patch("nebulus_atom.controllers.turn_processor.ToolExecutor")
    async def test_text_response_printed_when_not_streamed(self, mock_executor):
        mock_rag = MagicMock()
        mock_rag.index_history = AsyncMock()
        mock_rag_mgr = MagicMock()
        mock_rag_mgr.get_service.return_value = mock_rag
        mock_executor.rag_manager = mock_rag_mgr

        proc, openai_svc, view, parser = _make_processor()

        result = await proc._handle_text_response(
            "Hello there!", False, _make_history(), "sess"
        )

        assert result["finished"] is True
        view.print_agent_response.assert_called_once()
        view.print_telemetry.assert_called_once()

    @pytest.mark.asyncio
    @patch("nebulus_atom.controllers.turn_processor.ToolExecutor")
    async def test_text_response_not_printed_when_streamed(self, mock_executor):
        mock_rag = MagicMock()
        mock_rag.index_history = AsyncMock()
        mock_rag_mgr = MagicMock()
        mock_rag_mgr.get_service.return_value = mock_rag
        mock_executor.rag_manager = mock_rag_mgr

        proc, openai_svc, view, parser = _make_processor()

        result = await proc._handle_text_response(
            "Hello there!", True, _make_history(), "sess"
        )

        assert result["finished"] is True
        view.print_agent_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_response_returns_finished(self):
        proc, *_ = _make_processor()
        result = await proc._handle_text_response("   ", False, _make_history(), "sess")
        assert result["finished"] is True


# ---------------------------------------------------------------------------
# Handle Tool Calls Tests
# ---------------------------------------------------------------------------


class TestHandleToolCalls:
    @pytest.mark.asyncio
    @patch("nebulus_atom.controllers.turn_processor.ToolExecutor")
    async def test_executes_tool_and_records_history(self, mock_executor):
        mock_executor.dispatch = AsyncMock(return_value="done")
        proc, _, view, _ = _make_processor()
        history = _make_history()

        tool_calls = [
            {
                "function": {"name": "read_file", "arguments": '{"path": "x.py"}'},
                "id": "call_1",
                "type": "function",
            }
        ]

        result = await proc._handle_tool_calls(
            tool_calls, "", False, history, "sess", TurnCallbacks()
        )

        assert result["finished"] is True
        # History should have assistant message + tool output
        assert history.add.call_count == 2
        view.print_tool_output.assert_called_once()

    @pytest.mark.asyncio
    async def test_bad_json_args_records_error(self):
        proc, *_ = _make_processor()
        history = _make_history()

        tool_calls = [
            {
                "function": {"name": "read_file", "arguments": "not json"},
                "id": "call_1",
                "type": "function",
            }
        ]

        await proc._handle_tool_calls(
            tool_calls, "", False, history, "sess", TurnCallbacks()
        )

        # Should record error in history (called with positional "user" + keyword content=)
        error_call = history.add.call_args_list[-1]
        content = error_call.kwargs.get("content", "")
        assert "Error" in content

    @pytest.mark.asyncio
    @patch("nebulus_atom.controllers.turn_processor.ToolExecutor")
    async def test_tdd_tool_sets_flags(self, mock_executor):
        proc, *_ = _make_processor()
        history = _make_history()
        cb = TurnCallbacks(on_tdd_start=MagicMock())

        tool_calls = [
            {
                "function": {
                    "name": "start_tdd",
                    "arguments": json.dumps({"goal": "test coverage"}),
                },
                "id": "call_1",
                "type": "function",
            }
        ]

        result = await proc._handle_tool_calls(
            tool_calls, "", False, history, "sess", cb
        )

        assert result["started_tdd"] is True
        assert result["tdd_goal"] == "test coverage"

    @pytest.mark.asyncio
    @patch("nebulus_atom.controllers.turn_processor.ToolExecutor")
    async def test_dict_output_printed_as_plan(self, mock_executor):
        mock_executor.dispatch = AsyncMock(return_value={"goal": "fix", "tasks": []})
        proc, _, view, _ = _make_processor()
        history = _make_history()

        tool_calls = [
            {
                "function": {"name": "create_plan", "arguments": "{}"},
                "id": "call_1",
                "type": "function",
            }
        ]

        await proc._handle_tool_calls(
            tool_calls, "", False, history, "sess", TurnCallbacks()
        )

        view.print_plan.assert_called_once()


# ---------------------------------------------------------------------------
# Normalize Extracted Calls Tests
# ---------------------------------------------------------------------------


class TestNormalizeExtractedCalls:
    @patch("nebulus_atom.controllers.turn_processor.ToolExecutor")
    def test_normalizes_and_extracts_thoughts(self, mock_executor):
        proc, _, view, parser = _make_processor()

        parser.normalize_tool_call.return_value = {
            "function": {"name": "read_file", "arguments": "{}"},
            "id": "call_0",
            "type": "function",
            "thought": "I should read the file first",
        }

        mock_telemetry = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.get_service.return_value = mock_telemetry
        mock_executor.telemetry_manager = mock_mgr

        result = proc._normalize_extracted_calls(
            [{"tool": "read_file", "args": {}}], "sess"
        )

        assert len(result) == 1
        assert "thought" not in result[0]
        view.print_thought.assert_called_once_with("I should read the file first")


# ---------------------------------------------------------------------------
# Process (integration) Tests
# ---------------------------------------------------------------------------


class TestProcess:
    @pytest.mark.asyncio
    @patch("nebulus_atom.controllers.turn_processor.ToolExecutor")
    async def test_process_text_response(self, mock_executor):
        mock_rag = MagicMock()
        mock_rag.index_history = AsyncMock()
        mock_rag_mgr = MagicMock()
        mock_rag_mgr.get_service.return_value = mock_rag
        mock_executor.rag_manager = mock_rag_mgr

        proc, openai_svc, view, parser = _make_processor()

        async def mock_stream(*args, **kwargs):
            yield _make_chunk(content="Hello from the LLM!")

        openai_svc.create_chat_completion = mock_stream

        history = _make_history([{"role": "user", "content": "hi"}])

        result = await proc.process(history, "sess", enable_cognition=False)

        assert result.finished is True
        assert result.started_tdd is False

    @pytest.mark.asyncio
    async def test_process_error_is_caught(self):
        proc, openai_svc, view, _ = _make_processor()

        async def failing_stream(*args, **kwargs):
            raise RuntimeError("LLM down")
            yield  # noqa: F811 - unreachable yield makes this an async generator

        openai_svc.create_chat_completion = failing_stream

        history = _make_history([{"role": "user", "content": "hi"}])

        result = await proc.process(history, "sess", enable_cognition=False)

        assert result.finished is True
        view.print_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_injects_pinned_content(self):
        proc, openai_svc, view, parser = _make_processor()

        captured_messages = []

        async def capture_stream(messages, **kwargs):
            captured_messages.extend(messages)
            yield _make_chunk(content="ok")

        openai_svc.create_chat_completion = capture_stream

        # Need to make _handle_text_response not fail
        with patch.object(
            proc, "_handle_text_response", new_callable=AsyncMock
        ) as mock_handle:
            mock_handle.return_value = {"finished": True}

            history = _make_history([{"role": "user", "content": "hi"}])

            await proc.process(
                history, "sess", pinned_content="pinned context", enable_cognition=False
            )

        # The pinned content should appear in messages
        system_msgs = [m for m in captured_messages if m["role"] == "system"]
        assert any("pinned context" in m["content"] for m in system_msgs)


# ---------------------------------------------------------------------------
# Display Cognition Tests
# ---------------------------------------------------------------------------


class TestDisplayCognition:
    @pytest.mark.asyncio
    async def test_skips_simple_high_confidence(self):
        proc, _, view, _ = _make_processor()
        result = CognitionResult(
            task_complexity=TaskComplexity.SIMPLE,
            confidence=0.9,
            reasoning_chain=[],
            recommended_approach="direct",
            clarification_needed=False,
            clarification_questions=[],
            potential_risks=[],
        )
        cb = TurnCallbacks(on_cognition_analysis=MagicMock())

        await proc._display_cognition(result, cb)

        cb.on_cognition_analysis.assert_not_called()

    @pytest.mark.asyncio
    async def test_displays_complex_task(self):
        proc, _, view, _ = _make_processor()
        result = CognitionResult(
            task_complexity=TaskComplexity.COMPLEX,
            confidence=0.6,
            reasoning_chain=[],
            recommended_approach="multi-step",
            clarification_needed=True,
            clarification_questions=["What approach?"],
            potential_risks=["May break API"],
        )
        cb = TurnCallbacks(on_cognition_analysis=MagicMock())

        await proc._display_cognition(result, cb)

        cb.on_cognition_analysis.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_displays_low_confidence_simple(self):
        proc, _, view, _ = _make_processor()
        result = CognitionResult(
            task_complexity=TaskComplexity.SIMPLE,
            confidence=0.5,
            reasoning_chain=[],
            recommended_approach="direct",
            clarification_needed=False,
            clarification_questions=[],
            potential_risks=[],
        )
        cb = TurnCallbacks(on_cognition_analysis=MagicMock())

        await proc._display_cognition(result, cb)

        cb.on_cognition_analysis.assert_called_once()
