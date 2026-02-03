"""Minion agent - the autonomous coding brain."""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from nebulus_swarm.minion.agent.llm_client import LLMClient, LLMConfig, LLMResponse
from nebulus_swarm.minion.agent.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Status of agent execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ERROR = "error"
    TURN_LIMIT = "turn_limit"


@dataclass
class AgentResult:
    """Result of agent execution."""

    status: AgentStatus
    summary: str
    files_changed: List[str] = field(default_factory=list)
    error: Optional[str] = None
    blocker_type: Optional[str] = None
    question: Optional[str] = None
    turns_used: int = 0


@dataclass
class ToolResult:
    """Result of a tool execution."""

    tool_call_id: str
    name: str
    success: bool
    output: str
    error: Optional[str] = None


# Type alias for tool executor function
ToolExecutorFn = Callable[[str, Dict[str, Any]], ToolResult]


class MinionAgent:
    """Autonomous agent that works on GitHub issues."""

    # Default limits
    DEFAULT_TURN_LIMIT = 50
    DEFAULT_ERROR_THRESHOLD = 3

    def __init__(
        self,
        llm_config: LLMConfig,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        tool_executor: ToolExecutorFn,
        turn_limit: int = DEFAULT_TURN_LIMIT,
        error_threshold: int = DEFAULT_ERROR_THRESHOLD,
    ):
        """Initialize the Minion agent.

        Args:
            llm_config: Configuration for LLM client.
            system_prompt: System prompt with issue context and skills.
            tools: List of tool definitions in OpenAI format.
            tool_executor: Function to execute tools.
            turn_limit: Maximum number of turns before stopping.
            error_threshold: Consecutive errors before stopping.
        """
        self.llm = LLMClient(llm_config)
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_executor = tool_executor
        self.turn_limit = turn_limit
        self.error_threshold = error_threshold

        # Response parser for JSON fallback (when LLM doesn't support tool calling)
        self._parser = ResponseParser()

        # Conversation history
        self._messages: List[Dict[str, Any]] = []
        self._turn_count = 0
        self._consecutive_errors = 0

        # Completion tracking
        self._completed = False
        self._result: Optional[AgentResult] = None

    def run(self) -> AgentResult:
        """Run the agent loop until completion or limit.

        Returns:
            AgentResult with status and details.
        """
        logger.info("Starting agent loop")

        # Initialize with system prompt
        self._messages = [{"role": "system", "content": self.system_prompt}]

        while not self._completed and self._turn_count < self.turn_limit:
            self._turn_count += 1
            logger.info(f"Agent turn {self._turn_count}/{self.turn_limit}")

            try:
                # Get LLM response
                response = self.llm.chat(self._messages, self.tools)

                # Process response
                result = self._process_response(response)
                if result:
                    return result

            except Exception as e:
                logger.exception(f"Error in agent turn: {e}")
                self._consecutive_errors += 1

                if self._consecutive_errors >= self.error_threshold:
                    return AgentResult(
                        status=AgentStatus.ERROR,
                        summary=f"Too many consecutive errors: {e}",
                        error=str(e),
                        turns_used=self._turn_count,
                    )

        # Hit turn limit
        if not self._completed:
            logger.warning(f"Agent hit turn limit ({self.turn_limit})")
            return AgentResult(
                status=AgentStatus.TURN_LIMIT,
                summary=f"Reached turn limit of {self.turn_limit}",
                turns_used=self._turn_count,
            )

        return self._result or AgentResult(
            status=AgentStatus.ERROR,
            summary="Agent completed without result",
            turns_used=self._turn_count,
        )

    def _process_response(self, response: LLMResponse) -> Optional[AgentResult]:
        """Process LLM response and execute tools.

        Args:
            response: LLM response.

        Returns:
            AgentResult if agent is done, None to continue.
        """
        if response.content:
            logger.debug(f"Assistant: {response.content[:200]}...")

        # Get tool calls - either from API or extracted from content
        tool_calls = response.tool_calls

        # If no tool calls from API, try to extract from content (JSON fallback)
        if not tool_calls and response.content:
            logger.debug(
                f"No API tool calls, trying JSON extraction from: {response.content[:300]}..."
            )
            extracted = self._parser.extract_tool_calls(response.content)
            if extracted:
                tool_calls = self._parser.normalize_all(extracted)
                logger.info(f"Extracted {len(tool_calls)} tool calls from content")

        # Build assistant message with whatever tool calls we found
        assistant_message: Dict[str, Any] = {"role": "assistant"}
        if response.content:
            assistant_message["content"] = response.content

        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in tool_calls
            ]

        self._messages.append(assistant_message)

        # If no tool calls, prompt to continue
        if not tool_calls:
            logger.debug("No tool calls found, prompting to continue")
            self._messages.append(
                {
                    "role": "user",
                    "content": "Please continue with the task. Use tools to make progress, or call task_complete when done. Output your tool call as a JSON object with 'name' and 'arguments' fields.",
                }
            )
            return None

        # Execute tool calls
        for tool_call in tool_calls:
            result = self._execute_tool_call(tool_call)

            # Check for completion tools
            if result.name == "task_complete":
                return self._handle_task_complete(tool_call, result)
            elif result.name == "task_blocked":
                return self._handle_task_blocked(tool_call, result)

            # Add tool result to history
            self._messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": result.output
                    if result.success
                    else f"Error: {result.error}",
                }
            )

            # Track errors
            if not result.success:
                self._consecutive_errors += 1
                if self._consecutive_errors >= self.error_threshold:
                    return AgentResult(
                        status=AgentStatus.ERROR,
                        summary="Too many consecutive tool errors",
                        error=result.error,
                        turns_used=self._turn_count,
                    )
            else:
                self._consecutive_errors = 0

        return None

    def _execute_tool_call(self, tool_call: Dict[str, Any]) -> ToolResult:
        """Execute a single tool call.

        Args:
            tool_call: Tool call from LLM.

        Returns:
            ToolResult with execution outcome.
        """
        name = tool_call["name"]
        tool_call_id = tool_call["id"]

        try:
            arguments = json.loads(tool_call["arguments"])
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in tool arguments: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                success=False,
                output="",
                error=f"Invalid JSON arguments: {e}",
            )

        logger.info(f"Executing tool: {name}")
        logger.debug(f"Arguments: {arguments}")

        return self.tool_executor(name, arguments)

    def _handle_task_complete(
        self, tool_call: Dict[str, Any], result: ToolResult
    ) -> AgentResult:
        """Handle task_complete tool call.

        Args:
            tool_call: The tool call.
            result: Tool execution result.

        Returns:
            AgentResult indicating completion.
        """
        self._completed = True

        try:
            args = json.loads(tool_call["arguments"])
            summary = args.get("summary", "Task completed")
            files_changed = args.get("files_changed", [])
        except (json.JSONDecodeError, KeyError):
            summary = "Task completed"
            files_changed = []

        logger.info(f"Agent completed: {summary}")

        return AgentResult(
            status=AgentStatus.COMPLETED,
            summary=summary,
            files_changed=files_changed,
            turns_used=self._turn_count,
        )

    def _handle_task_blocked(
        self, tool_call: Dict[str, Any], result: ToolResult
    ) -> AgentResult:
        """Handle task_blocked tool call.

        Args:
            tool_call: The tool call.
            result: Tool execution result.

        Returns:
            AgentResult indicating blocked state.
        """
        self._completed = True

        try:
            args = json.loads(tool_call["arguments"])
            reason = args.get("reason", "Task blocked")
            blocker_type = args.get("blocker_type", "unknown")
            question = args.get("question")
        except (json.JSONDecodeError, KeyError):
            reason = "Task blocked"
            blocker_type = "unknown"
            question = None

        logger.warning(f"Agent blocked: {reason}")

        return AgentResult(
            status=AgentStatus.BLOCKED,
            summary=reason,
            blocker_type=blocker_type,
            question=question,
            turns_used=self._turn_count,
        )

    @property
    def turn_count(self) -> int:
        """Get current turn count."""
        return self._turn_count

    @property
    def message_count(self) -> int:
        """Get current message count."""
        return len(self._messages)
