"""SDK factory for native Python API calls to Anthropic and Google.

Provides a unified interface for calling LLM APIs with token tracking,
replacing subprocess-based CLI execution. Lives in nebulus-atom (not
nebulus-core) since cloud SDKs are dispatch infrastructure, not platform
adapter concerns.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str
    tokens_input: int
    tokens_output: int
    model: str
    provider: str  # "anthropic" | "google" | "openai"


# Model alias → full model ID
ANTHROPIC_MODEL_MAP: dict[str, str] = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-0520",
    "haiku": "claude-haiku-4-20250514",
}

GOOGLE_MODEL_MAP: dict[str, str] = {
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
}

# Per-1M-token pricing (input_cost, output_cost)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-opus-4-0520": (15.0, 75.0),
    "claude-haiku-4-20250514": (0.80, 4.0),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.15, 0.60),
}


def resolve_model(alias: str, provider: str) -> str:
    """Resolve a model alias to its full model ID.

    Args:
        alias: Model alias or full model ID.
        provider: Provider name ("anthropic" or "google").

    Returns:
        Full model ID string.
    """
    if provider == "anthropic":
        return ANTHROPIC_MODEL_MAP.get(alias, alias)
    if provider == "google":
        return GOOGLE_MODEL_MAP.get(alias, alias)
    return alias


def call_anthropic(
    prompt: str,
    model: str,
    api_key: Optional[str] = None,
    max_tokens: int = 4096,
    timeout: int = 600,
) -> LLMResponse:
    """Call the Anthropic Messages API.

    Args:
        prompt: User message content.
        model: Model alias or full ID.
        api_key: API key (falls back to ANTHROPIC_API_KEY env var).
        max_tokens: Maximum output tokens.
        timeout: Request timeout in seconds.

    Returns:
        LLMResponse with content and token counts.

    Raises:
        ValueError: If no API key is available.
        RuntimeError: If the API call fails.
    """
    import anthropic  # noqa: F811 — imported here for lazy loading

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("No Anthropic API key — set ANTHROPIC_API_KEY or pass api_key")

    resolved = resolve_model(model, "anthropic")
    client = anthropic.Anthropic(api_key=key, timeout=timeout)

    try:
        message = client.messages.create(
            model=resolved,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API error: {e}") from e

    content = ""
    for block in message.content:
        if block.type == "text":
            content += block.text

    return LLMResponse(
        content=content,
        tokens_input=message.usage.input_tokens,
        tokens_output=message.usage.output_tokens,
        model=resolved,
        provider="anthropic",
    )


def call_google(
    prompt: str,
    model: str,
    api_key: Optional[str] = None,
    timeout: int = 600,
) -> LLMResponse:
    """Call the Google Generative AI API.

    Args:
        prompt: User message content.
        model: Model alias or full ID.
        api_key: API key (falls back to GOOGLE_API_KEY env var).
        timeout: Request timeout in seconds.

    Returns:
        LLMResponse with content and token counts.

    Raises:
        ValueError: If no API key is available.
        RuntimeError: If the API call fails.
    """
    import google.generativeai as genai  # noqa: F811 — imported here for lazy loading

    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("No Google API key — set GOOGLE_API_KEY or pass api_key")

    resolved = resolve_model(model, "google")
    genai.configure(api_key=key)
    gen_model = genai.GenerativeModel(resolved)

    try:
        response = gen_model.generate_content(
            prompt,
            request_options={"timeout": timeout},
        )
    except Exception as e:
        raise RuntimeError(f"Google API error: {e}") from e

    content = response.text or ""
    usage = getattr(response, "usage_metadata", None)
    tokens_in = getattr(usage, "prompt_token_count", 0) if usage else 0
    tokens_out = getattr(usage, "candidates_token_count", 0) if usage else 0

    return LLMResponse(
        content=content,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        model=resolved,
        provider="google",
    )


def estimate_cost(
    tokens_input: int,
    tokens_output: int,
    model: str,
) -> float:
    """Estimate the USD cost for a given token usage.

    Args:
        tokens_input: Number of input tokens.
        tokens_output: Number of output tokens.
        model: Full model ID (must be in MODEL_PRICING).

    Returns:
        Estimated cost in USD. Returns 0.0 for unknown models.
    """
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0

    input_cost_per_m, output_cost_per_m = pricing
    return (
        tokens_input * input_cost_per_m / 1_000_000
        + tokens_output * output_cost_per_m / 1_000_000
    )
