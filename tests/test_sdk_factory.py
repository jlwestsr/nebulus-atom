"""Tests for the SDK factory module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from nebulus_swarm.overlord.workers.sdk_factory import (
    ANTHROPIC_MODEL_MAP,
    GOOGLE_MODEL_MAP,
    MODEL_PRICING,
    LLMResponse,
    estimate_cost,
    resolve_model,
)


# --- resolve_model ---


class TestResolveModel:
    """Tests for model alias resolution."""

    def test_anthropic_alias_sonnet(self) -> None:
        assert resolve_model("sonnet", "anthropic") == ANTHROPIC_MODEL_MAP["sonnet"]

    def test_anthropic_alias_opus(self) -> None:
        assert resolve_model("opus", "anthropic") == ANTHROPIC_MODEL_MAP["opus"]

    def test_anthropic_alias_haiku(self) -> None:
        assert resolve_model("haiku", "anthropic") == ANTHROPIC_MODEL_MAP["haiku"]

    def test_anthropic_passthrough(self) -> None:
        assert (
            resolve_model("claude-custom-model", "anthropic") == "claude-custom-model"
        )

    def test_google_alias(self) -> None:
        assert (
            resolve_model("gemini-2.5-pro", "google")
            == GOOGLE_MODEL_MAP["gemini-2.5-pro"]
        )

    def test_google_passthrough(self) -> None:
        assert resolve_model("custom-google-model", "google") == "custom-google-model"

    def test_unknown_provider(self) -> None:
        assert resolve_model("whatever", "openai") == "whatever"


# --- estimate_cost ---


class TestEstimateCost:
    """Tests for cost estimation."""

    def test_known_model(self) -> None:
        model = "claude-sonnet-4-20250514"
        cost = estimate_cost(1_000_000, 1_000_000, model)
        inp, out = MODEL_PRICING[model]
        expected = inp + out  # 1M tokens each
        assert abs(cost - expected) < 0.001

    def test_zero_tokens(self) -> None:
        assert estimate_cost(0, 0, "claude-sonnet-4-20250514") == 0.0

    def test_unknown_model(self) -> None:
        assert estimate_cost(1000, 500, "unknown-model") == 0.0

    def test_partial_tokens(self) -> None:
        model = "claude-haiku-4-20250514"
        cost = estimate_cost(500_000, 100_000, model)
        inp, out = MODEL_PRICING[model]
        expected = 500_000 * inp / 1_000_000 + 100_000 * out / 1_000_000
        assert abs(cost - expected) < 0.001

    def test_gemini_pricing(self) -> None:
        model = "gemini-2.5-flash"
        cost = estimate_cost(1_000_000, 1_000_000, model)
        inp, out = MODEL_PRICING[model]
        expected = inp + out
        assert abs(cost - expected) < 0.001


# --- call_anthropic ---


class TestCallAnthropic:
    """Tests for call_anthropic with mocked SDK."""

    def _make_mock_anthropic(self) -> MagicMock:
        """Create a mock anthropic module."""
        mock_mod = MagicMock()
        mock_mod.APIError = type("APIError", (Exception,), {})
        return mock_mod

    def test_successful_call(self) -> None:
        mock_anthropic = self._make_mock_anthropic()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Hello world"

        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50

        mock_message = MagicMock()
        mock_message.content = [mock_block]
        mock_message.usage = mock_usage
        mock_client.messages.create.return_value = mock_message

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from nebulus_swarm.overlord.workers.sdk_factory import call_anthropic

            response = call_anthropic(prompt="test", model="sonnet", api_key="test-key")

        assert isinstance(response, LLMResponse)
        assert response.content == "Hello world"
        assert response.tokens_input == 100
        assert response.tokens_output == 50
        assert response.provider == "anthropic"

    def test_missing_api_key(self) -> None:
        mock_anthropic = self._make_mock_anthropic()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with patch.dict("os.environ", {}, clear=True):
                from nebulus_swarm.overlord.workers.sdk_factory import call_anthropic

                with pytest.raises(ValueError, match="No Anthropic API key"):
                    call_anthropic("test", "sonnet")

    def test_api_error(self) -> None:
        mock_anthropic = self._make_mock_anthropic()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = mock_anthropic.APIError("fail")

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from nebulus_swarm.overlord.workers.sdk_factory import call_anthropic

            with pytest.raises(RuntimeError, match="Anthropic API error"):
                call_anthropic("test", "sonnet", api_key="key")

    def test_model_resolved(self) -> None:
        mock_anthropic = self._make_mock_anthropic()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_block = MagicMock(type="text", text="ok")
        mock_usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_message = MagicMock(content=[mock_block], usage=mock_usage)
        mock_client.messages.create.return_value = mock_message

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from nebulus_swarm.overlord.workers.sdk_factory import call_anthropic

            response = call_anthropic("test", "opus", api_key="key")

        assert response.model == ANTHROPIC_MODEL_MAP["opus"]
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == ANTHROPIC_MODEL_MAP["opus"]

    def test_multiple_text_blocks(self) -> None:
        mock_anthropic = self._make_mock_anthropic()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        block1 = MagicMock(type="text", text="Hello ")
        block2 = MagicMock(type="tool_use", text="")
        block3 = MagicMock(type="text", text="world")
        mock_usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_msg = MagicMock(content=[block1, block2, block3], usage=mock_usage)
        mock_client.messages.create.return_value = mock_msg

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from nebulus_swarm.overlord.workers.sdk_factory import call_anthropic

            response = call_anthropic("test", "sonnet", api_key="key")

        assert response.content == "Hello world"

    def test_timeout_passed(self) -> None:
        mock_anthropic = self._make_mock_anthropic()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_block = MagicMock(type="text", text="ok")
        mock_usage = MagicMock(input_tokens=1, output_tokens=1)
        mock_msg = MagicMock(content=[mock_block], usage=mock_usage)
        mock_client.messages.create.return_value = mock_msg

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from nebulus_swarm.overlord.workers.sdk_factory import call_anthropic

            call_anthropic("test", "sonnet", api_key="key", timeout=120)

        mock_anthropic.Anthropic.assert_called_once_with(api_key="key", timeout=120)


# --- call_google ---


class TestCallGoogle:
    """Tests for call_google with mocked SDK."""

    def _make_mock_genai(self) -> tuple[MagicMock, MagicMock]:
        """Create mock google.generativeai module and its parent."""
        mock_genai = MagicMock()
        mock_google = MagicMock()
        mock_google.generativeai = mock_genai
        return mock_genai, mock_google

    def test_successful_call(self) -> None:
        mock_genai, mock_google = self._make_mock_genai()
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 200
        mock_usage.candidates_token_count = 100

        mock_response = MagicMock()
        mock_response.text = "Generated text"
        mock_response.usage_metadata = mock_usage
        mock_model.generate_content.return_value = mock_response

        with patch.dict(
            sys.modules,
            {
                "google": mock_google,
                "google.generativeai": mock_genai,
            },
        ):
            from nebulus_swarm.overlord.workers.sdk_factory import call_google

            response = call_google(
                prompt="test", model="gemini-2.5-pro", api_key="test-key"
            )

        assert isinstance(response, LLMResponse)
        assert response.content == "Generated text"
        assert response.tokens_input == 200
        assert response.tokens_output == 100
        assert response.provider == "google"

    def test_missing_api_key(self) -> None:
        mock_genai, mock_google = self._make_mock_genai()
        with patch.dict(
            sys.modules,
            {
                "google": mock_google,
                "google.generativeai": mock_genai,
            },
        ):
            with patch.dict("os.environ", {}, clear=True):
                from nebulus_swarm.overlord.workers.sdk_factory import call_google

                with pytest.raises(ValueError, match="No Google API key"):
                    call_google("test", "gemini-2.5-pro")

    def test_api_error(self) -> None:
        mock_genai, mock_google = self._make_mock_genai()
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_model.generate_content.side_effect = Exception("Google error")

        with patch.dict(
            sys.modules,
            {
                "google": mock_google,
                "google.generativeai": mock_genai,
            },
        ):
            from nebulus_swarm.overlord.workers.sdk_factory import call_google

            with pytest.raises(RuntimeError, match="Google API error"):
                call_google("test", "gemini-2.5-pro", api_key="key")

    def test_no_usage_metadata(self) -> None:
        mock_genai, mock_google = self._make_mock_genai()
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        mock_response = MagicMock()
        mock_response.text = "output"
        mock_response.usage_metadata = None
        mock_model.generate_content.return_value = mock_response

        with patch.dict(
            sys.modules,
            {
                "google": mock_google,
                "google.generativeai": mock_genai,
            },
        ):
            from nebulus_swarm.overlord.workers.sdk_factory import call_google

            response = call_google("test", "gemini-2.5-pro", api_key="key")

        assert response.tokens_input == 0
        assert response.tokens_output == 0

    def test_empty_text(self) -> None:
        mock_genai, mock_google = self._make_mock_genai()
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        mock_response = MagicMock()
        mock_response.text = None
        mock_response.usage_metadata = None
        mock_model.generate_content.return_value = mock_response

        with patch.dict(
            sys.modules,
            {
                "google": mock_google,
                "google.generativeai": mock_genai,
            },
        ):
            from nebulus_swarm.overlord.workers.sdk_factory import call_google

            response = call_google("test", "gemini-2.5-pro", api_key="key")

        assert response.content == ""


# --- LLMResponse ---


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_creation(self) -> None:
        r = LLMResponse(
            content="hello",
            tokens_input=100,
            tokens_output=50,
            model="test-model",
            provider="anthropic",
        )
        assert r.content == "hello"
        assert r.tokens_input == 100
        assert r.tokens_output == 50
        assert r.model == "test-model"
        assert r.provider == "anthropic"
