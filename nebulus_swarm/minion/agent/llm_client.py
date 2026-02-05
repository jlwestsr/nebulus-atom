"""LLM client wrapper for Minion agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from openai import OpenAI

if TYPE_CHECKING:
    from nebulus_swarm.overlord.llm_pool import LLMPool

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM client."""

    base_url: str
    model: str
    api_key: str = "not-needed"
    timeout: int = 600
    temperature: float = 0.3
    max_tokens: int = 4096


@dataclass
class LLMResponse:
    """Response from LLM."""

    content: str
    tool_calls: List[Dict[str, Any]]
    finish_reason: str
    usage: Optional[Dict[str, int]] = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


class LLMClient:
    """Wrapper around OpenAI SDK for Nebulus/local LLM servers."""

    def __init__(self, config: LLMConfig, pool: Optional[LLMPool] = None):
        """Initialize LLM client.

        Args:
            config: LLM configuration.
            pool: Optional LLM connection pool for concurrent access control.
        """
        self.config = config
        self._pool = pool
        if pool:
            self._client = pool.client
        else:
            self._client = OpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                timeout=config.timeout,
            )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: Conversation history.
            tools: Optional tool definitions.

        Returns:
            LLMResponse with content and/or tool calls.

        Raises:
            RuntimeError: If pool acquisition times out.
        """
        if self._pool:
            if not self._pool.acquire():
                raise RuntimeError("LLM pool: timed out waiting for slot")

        try:
            kwargs = {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            logger.debug(f"Sending chat request with {len(messages)} messages")

            response = self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message

            # Extract tool calls if present
            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    )

            # Extract usage info
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return LLMResponse(
                content=message.content or "",
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason,
                usage=usage,
            )
        except Exception:
            if self._pool:
                self._pool.record_error()
            raise
        finally:
            if self._pool:
                self._pool.release()

    def simple_chat(self, prompt: str, system: Optional[str] = None) -> str:
        """Simple single-turn chat without tools.

        Args:
            prompt: User prompt.
            system: Optional system message.

        Returns:
            Response content string.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.chat(messages)
        return response.content
