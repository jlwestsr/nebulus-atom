"""
Turn processor for handling single conversation turns.

Manages LLM streaming, response parsing, and tool execution dispatch.
Integrates cognitive analysis for complex task handling.
"""

import json
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable

from nebulus_atom.services.openai_service import OpenAIService
from nebulus_atom.services.response_parser import ResponseParser
from nebulus_atom.services.tool_executor import ToolExecutor
from nebulus_atom.models.cognition import TaskComplexity, CognitionResult
from nebulus_atom.views.base_view import BaseView
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class TurnCallbacks:
    """Callbacks for state changes during turn processing."""

    on_tdd_start: Optional[Callable[[str], None]] = None
    on_auto_mode_start: Optional[Callable[[], None]] = None
    on_cognition_analysis: Optional[Callable[[CognitionResult], None]] = None


@dataclass
class TurnResult:
    """Result of processing a turn."""

    finished: bool = True
    started_tdd: bool = False
    started_auto_mode: bool = False
    tdd_goal: Optional[str] = None


class TurnProcessor:
    """Processes single conversation turns with streaming and tool execution."""

    def __init__(
        self,
        openai_service: OpenAIService,
        view: BaseView,
        response_parser: Optional[ResponseParser] = None,
    ) -> None:
        """
        Initialize the turn processor.

        Args:
            openai_service: Service for LLM API calls.
            view: View for rendering output.
            response_parser: Parser for extracting tool calls from responses.
        """
        self._openai = openai_service
        self._view = view
        self._parser = response_parser or ResponseParser()

    async def process(
        self,
        history: Any,
        session_id: str,
        pinned_content: Optional[str] = None,
        callbacks: Optional[TurnCallbacks] = None,
        enable_cognition: bool = True,
    ) -> TurnResult:
        """
        Process a single conversation turn.

        Args:
            history: History manager for the session.
            session_id: Session identifier.
            pinned_content: Optional pinned context to inject.
            callbacks: Optional callbacks for state changes.
            enable_cognition: Whether to perform cognitive analysis.

        Returns:
            TurnResult indicating what happened during the turn.
        """
        callbacks = callbacks or TurnCallbacks()
        result = TurnResult(finished=False)

        messages = history.get()

        # Perform cognitive analysis on the last user message
        if enable_cognition and messages:
            cognition_result = await self._analyze_task(messages, session_id)
            if cognition_result:
                await self._display_cognition(cognition_result, callbacks)

        if pinned_content:
            messages = [m.copy() for m in messages]
            messages.append({"role": "system", "content": pinned_content})

        while not result.finished:
            try:
                turn_outcome = await self._process_single_iteration(
                    messages, history, session_id, callbacks
                )
                result.finished = turn_outcome.get("finished", True)
                result.started_tdd = turn_outcome.get("started_tdd", False)
                result.started_auto_mode = turn_outcome.get("started_auto_mode", False)
                result.tdd_goal = turn_outcome.get("tdd_goal")
            except Exception as e:
                logger.error(f"Error in process turn: {str(e)}", exc_info=True)
                await self._view.print_error(str(e))
                result.finished = True

        return result

    async def _analyze_task(
        self,
        messages: List[Dict[str, Any]],
        session_id: str,
    ) -> Optional[CognitionResult]:
        """
        Analyze the last user message for task complexity.

        Args:
            messages: Conversation messages.
            session_id: Session identifier.

        Returns:
            CognitionResult if analysis was performed, None otherwise.
        """
        # Find the last user message
        last_user_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # Skip tool output messages
                if not content.startswith("Tool '"):
                    last_user_msg = content
                    break

        if not last_user_msg:
            return None

        try:
            cognition_service = ToolExecutor.cognition_manager.get_service(session_id)
            result = cognition_service.analyze_task(last_user_msg)

            # Record the analysis as a thought
            cognition_service.record_thought(
                session_id=session_id,
                thought_type="analysis",
                content=f"Task complexity: {result.task_complexity.value}, "
                f"confidence: {result.confidence:.0%}",
                confidence=result.confidence,
            )

            return result
        except Exception as e:
            logger.warning(f"Cognition analysis failed: {e}")
            return None

    async def _display_cognition(
        self,
        result: CognitionResult,
        callbacks: TurnCallbacks,
    ) -> None:
        """
        Display cognitive analysis results for complex tasks.

        Args:
            result: The cognition analysis result.
            callbacks: Turn callbacks (may include cognition handler).
        """
        # Only display for complex tasks or low confidence
        if result.task_complexity == TaskComplexity.SIMPLE and result.confidence > 0.8:
            return

        # Notify via callback if provided
        if callbacks.on_cognition_analysis:
            callbacks.on_cognition_analysis(result)

        # Display reasoning for non-simple tasks
        if hasattr(self._view, "print_cognition"):
            await self._view.print_cognition(result)
        elif result.task_complexity != TaskComplexity.SIMPLE:
            # Fallback: print basic info via thought display
            complexity_emoji = {
                TaskComplexity.SIMPLE: "🟢",
                TaskComplexity.MODERATE: "🟡",
                TaskComplexity.COMPLEX: "🔴",
            }
            emoji = complexity_emoji.get(result.task_complexity, "⚪")

            if hasattr(self._view, "print_thought"):
                thought_msg = (
                    f"{emoji} Task Analysis: {result.task_complexity.value} "
                    f"(confidence: {result.confidence:.0%})"
                )
                self._view.print_thought(thought_msg)

                # Show risks if any
                if result.potential_risks:
                    for risk in result.potential_risks[:2]:
                        self._view.print_thought(f"⚠️ {risk}")

    async def _process_single_iteration(
        self,
        messages: List[Dict[str, Any]],
        history: Any,
        session_id: str,
        callbacks: TurnCallbacks,
    ) -> Dict[str, Any]:
        """
        Process a single iteration within a turn.

        Args:
            messages: Messages to send to LLM.
            history: History manager.
            session_id: Session identifier.
            callbacks: State change callbacks.

        Returns:
            Dictionary with turn outcome flags.
        """
        current_messages = history.get()
        last_role = current_messages[-1]["role"] if current_messages else "user"
        spinner_text = self._get_spinner_text(last_role)

        spinner_ctx = self._view.create_spinner(spinner_text)
        spinner_ctx.__enter__()
        spinner_active = True
        stream_started = False

        try:
            response_stream = self._openai.create_chat_completion(
                messages,
                tools=None,
            )
            full_response = ""
            tool_calls: List[Dict[str, Any]] = []
            tool_calls_map: Dict[int, Dict[str, Any]] = {}

            stream_buffer = ""
            stream_decision_made = False

            async for chunk in response_stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    content = delta.content
                    full_response += content

                    if spinner_active:
                        spinner_ctx.__exit__(None, None, None)
                        spinner_active = False

                    if not stream_decision_made:
                        stream_buffer += content
                        if len(stream_buffer) >= 20 or "{" in stream_buffer:
                            stream_decision_made = True
                            stripped = stream_buffer.strip()
                            if stripped.startswith("{") or '{"' in stripped:
                                stream_started = False
                            else:
                                self._view.print_stream_start()
                                self._view.print_stream_chunk(stream_buffer)
                                stream_started = True
                    elif stream_started:
                        self._view.print_stream_chunk(content)

                # Handle tool_calls (use getattr for non-streaming compatibility)
                delta_tool_calls = getattr(delta, "tool_calls", None)
                if delta_tool_calls:
                    tool_calls_map = self._process_delta_tool_calls(
                        delta_tool_calls, tool_calls_map
                    )

            if stream_started:
                self._view.print_stream_end()

        finally:
            if spinner_active:
                spinner_ctx.__exit__(None, None, None)

        tool_calls = list(tool_calls_map.values())

        if not tool_calls:
            logger.debug(
                f"Attempting to extract tool calls from: {full_response[:500]}..."
            )
            extracted_list = self._parser.extract_tool_calls(full_response)
            logger.debug(f"Extracted {len(extracted_list)} tool calls")
            if extracted_list:
                tool_calls = self._normalize_extracted_calls(extracted_list, session_id)
                full_response = ""

        if tool_calls:
            return await self._handle_tool_calls(
                tool_calls,
                full_response,
                stream_started,
                history,
                session_id,
                callbacks,
            )
        else:
            return await self._handle_text_response(
                full_response, stream_started, history, session_id
            )

    def _get_spinner_text(self, last_role: str) -> str:
        """Get appropriate spinner text based on context."""
        if last_role == "tool":
            return "Analyzing Tool Output..."
        elif last_role == "user":
            return "Processing Request..."
        return "Thinking..."

    def _process_delta_tool_calls(
        self,
        delta_tool_calls: List[Any],
        tool_calls_map: Dict[int, Dict[str, Any]],
    ) -> Dict[int, Dict[str, Any]]:
        """Process streaming tool call deltas."""
        for tc in delta_tool_calls:
            if tc.index not in tool_calls_map:
                tool_calls_map[tc.index] = {
                    "id": tc.id or f"call_{int(time.time())}",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                }
            if tc.function.name:
                tool_calls_map[tc.index]["function"]["name"] += tc.function.name
            if tc.function.arguments:
                tool_calls_map[tc.index]["function"]["arguments"] += (
                    tc.function.arguments
                )
        return tool_calls_map

    def _normalize_extracted_calls(
        self, extracted_list: List[Dict[str, Any]], session_id: str
    ) -> List[Dict[str, Any]]:
        """Normalize extracted tool calls and log thoughts."""
        tool_calls = []
        for i, extracted in enumerate(extracted_list):
            normalized = self._parser.normalize_tool_call(extracted, i)
            thought = normalized.pop("thought", None)

            if thought:
                self._log_thought(thought, session_id)
                if hasattr(self._view, "print_thought"):
                    self._view.print_thought(thought)

            tool_calls.append(normalized)
        return tool_calls

    def _log_thought(self, thought: str, session_id: str) -> None:
        """Log thought to telemetry."""
        try:
            telemetry_service = ToolExecutor.telemetry_manager.get_service(session_id)
            telemetry_service.log_thought(session_id, thought)
        except Exception:
            pass

    async def _handle_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        full_response: str,
        stream_started: bool,
        history: Any,
        session_id: str,
        callbacks: TurnCallbacks,
    ) -> Dict[str, Any]:
        """Handle tool call execution."""
        history.add(
            "assistant",
            content=full_response.strip() or None,
            tool_calls=tool_calls,
        )
        if full_response.strip() and not stream_started:
            await self._view.print_agent_response(full_response)

        result = {"finished": False, "started_tdd": False, "started_auto_mode": False}

        for tc in tool_calls:
            name = tc["function"]["name"]
            args_str = tc["function"]["arguments"]
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except Exception as e:
                output_str = f"Error parsing JSON arguments: {str(e)}"
                history.add(
                    "user",
                    content=f"System Error: {output_str}",
                    tool_call_id=None,
                )
                continue

            output, special_action = await self._execute_single_tool(
                name, args, session_id, callbacks
            )

            if special_action == "tdd":
                result["finished"] = True
                result["started_tdd"] = True
                result["tdd_goal"] = args.get("goal")
            elif special_action == "auto_mode":
                result["finished"] = True
                result["started_auto_mode"] = True
            else:
                result["finished"] = True

            if isinstance(output, dict):
                await self._view.print_plan(output)
                output_str = json.dumps(output)
            else:
                output_str = str(output)
                await self._view.print_tool_output(output_str, tool_name=name)

            history.add(
                "user",
                content=f"Tool '{name}' output:\n{output_str}",
                tool_call_id=None,
            )

        return result

    async def _execute_single_tool(
        self,
        name: str,
        args: Dict[str, Any],
        session_id: str,
        callbacks: TurnCallbacks,
    ) -> tuple[Any, Optional[str]]:
        """
        Execute a single tool and return output with any special action flag.

        Returns:
            Tuple of (output, special_action) where special_action is "tdd", "auto_mode", or None.
        """
        if name == "ask_user":
            question = args.get("question", "")
            if question:
                output = await self._view.ask_user_input(question)
            else:
                output = "Error: No question provided."
            return output, None

        elif name == "start_tdd":
            goal = args.get("goal")
            output = f"TDD Loop scheduled for: {goal}"
            if callbacks.on_tdd_start:
                callbacks.on_tdd_start(goal)
            return output, "tdd"

        elif name == "execute_plan":
            output = "Autonomous execution started. I will now proceed to execute tasks one by one."
            if callbacks.on_auto_mode_start:
                callbacks.on_auto_mode_start()
            return output, "auto_mode"

        else:
            with self._view.create_spinner(f"Executing {name}"):
                output = await ToolExecutor.dispatch(name, args, session_id=session_id)
            return output, None

    async def _handle_text_response(
        self,
        full_response: str,
        stream_started: bool,
        history: Any,
        session_id: str,
    ) -> Dict[str, Any]:
        """Handle a text-only response (no tool calls)."""
        if full_response.strip():
            cleaned = self._parser.clean_response_text(full_response)
            if cleaned and not stream_started:
                await self._view.print_agent_response(cleaned)
            await self._view.print_telemetry(
                getattr(self._openai, "last_telemetry", {})
            )
            history.add("assistant", cleaned)

            rag_service = ToolExecutor.rag_manager.get_service(session_id)
            with self._view.create_spinner("Updating Context..."):
                await rag_service.index_history("assistant", cleaned, session_id)

        return {"finished": True}
