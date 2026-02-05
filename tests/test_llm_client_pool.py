"""Tests for LLM client integration with connection pool."""

from unittest.mock import MagicMock, Mock, patch

import pytest

# Skip if openai not available
pytest.importorskip("openai")

from nebulus_swarm.minion.agent.llm_client import LLMClient, LLMConfig
from nebulus_swarm.overlord.llm_pool import LLMPool, PoolConfig


@pytest.fixture
def llm_config():
    """Create a standard LLM config for testing."""
    return LLMConfig(
        base_url="http://localhost:5000/v1",
        model="test-model",
        api_key="test-key",
        timeout=30,
    )


@pytest.fixture
def pool_config():
    """Create a standard pool config for testing."""
    return PoolConfig(
        base_url="http://localhost:5000/v1",
        model="test-model",
        api_key="test-key",
        timeout=30,
        max_concurrency=2,
        acquire_timeout=5.0,
    )


@pytest.fixture
def mock_pool(pool_config):
    """Create a mock pool for testing."""
    pool = Mock(spec=LLMPool)
    pool.config = pool_config
    pool.acquire = Mock(return_value=True)
    pool.release = Mock()
    pool.record_error = Mock()
    pool.record_retry = Mock()
    pool.client = MagicMock()  # Mock OpenAI client
    return pool


def test_standalone_mode_no_pool(llm_config):
    """Test that LLMClient with no pool creates its own client."""
    with patch("nebulus_swarm.minion.agent.llm_client.OpenAI") as mock_openai:
        client = LLMClient(llm_config)

        # Should create its own OpenAI client
        mock_openai.assert_called_once_with(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            timeout=llm_config.timeout,
        )

        # Should not have pool
        assert client._pool is None


def test_pool_mode_uses_pool_client(llm_config, mock_pool):
    """Test that LLMClient with pool uses pool.client."""
    client = LLMClient(llm_config, pool=mock_pool)

    # Should use pool's client
    assert client._client is mock_pool.client
    assert client._pool is mock_pool


def test_pool_acquire_release_on_chat(llm_config, mock_pool):
    """Test that pool.acquire is called before chat and pool.release after."""
    # Setup mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test response"
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_response.usage.total_tokens = 30

    mock_pool.client.chat.completions.create = Mock(return_value=mock_response)

    client = LLMClient(llm_config, pool=mock_pool)
    messages = [{"role": "user", "content": "test"}]

    response = client.chat(messages)

    # Verify acquire called before chat
    mock_pool.acquire.assert_called_once()

    # Verify release called after chat
    mock_pool.release.assert_called_once()

    # Verify response is correct
    assert response.content == "Test response"
    assert response.finish_reason == "stop"


def test_pool_acquire_timeout_raises(llm_config, mock_pool):
    """Test that RuntimeError is raised when pool.acquire times out."""
    # Mock acquire returning False (timeout)
    mock_pool.acquire.return_value = False

    client = LLMClient(llm_config, pool=mock_pool)
    messages = [{"role": "user", "content": "test"}]

    with pytest.raises(RuntimeError, match="LLM pool: timed out waiting for slot"):
        client.chat(messages)

    # Verify acquire was called
    mock_pool.acquire.assert_called_once()

    # Verify release was NOT called (since acquire failed)
    mock_pool.release.assert_not_called()


def test_pool_release_on_error(llm_config, mock_pool):
    """Test that pool.release is called even when chat raises an exception."""
    # Mock chat to raise an exception
    mock_pool.client.chat.completions.create = Mock(
        side_effect=Exception("Network error")
    )

    client = LLMClient(llm_config, pool=mock_pool)
    messages = [{"role": "user", "content": "test"}]

    with pytest.raises(Exception, match="Network error"):
        client.chat(messages)

    # Verify acquire was called
    mock_pool.acquire.assert_called_once()

    # Verify release was called in finally block
    mock_pool.release.assert_called_once()


def test_pool_record_error_on_exception(llm_config, mock_pool):
    """Test that pool.record_error is called when chat raises an exception."""
    # Mock chat to raise an exception
    mock_pool.client.chat.completions.create = Mock(
        side_effect=Exception("Network error")
    )

    client = LLMClient(llm_config, pool=mock_pool)
    messages = [{"role": "user", "content": "test"}]

    with pytest.raises(Exception, match="Network error"):
        client.chat(messages)

    # Verify record_error was called
    mock_pool.record_error.assert_called_once()


def test_standalone_mode_no_pool_interactions(llm_config):
    """Test that standalone mode doesn't interact with pool methods."""
    # Setup mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test response"
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage = None

    with patch("nebulus_swarm.minion.agent.llm_client.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create = Mock(return_value=mock_response)
        mock_openai.return_value = mock_client

        client = LLMClient(llm_config)
        messages = [{"role": "user", "content": "test"}]

        response = client.chat(messages)

        # Should work fine
        assert response.content == "Test response"

        # No pool, so client should be the mock_client
        assert client._client is mock_client


def test_simple_chat_uses_pool(llm_config, mock_pool):
    """Test that simple_chat also uses the pool (via chat)."""
    # Setup mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Simple response"
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage = None

    mock_pool.client.chat.completions.create = Mock(return_value=mock_response)

    client = LLMClient(llm_config, pool=mock_pool)

    result = client.simple_chat("test prompt", system="test system")

    # Verify pool methods called
    mock_pool.acquire.assert_called_once()
    mock_pool.release.assert_called_once()

    # Verify result
    assert result == "Simple response"


def test_chat_with_tools_uses_pool(llm_config, mock_pool):
    """Test that chat with tools also uses the pool correctly."""
    # Setup mock response with tool calls
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "test_tool"
    mock_tool_call.function.arguments = '{"arg": "value"}'

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = ""
    mock_response.choices[0].message.tool_calls = [mock_tool_call]
    mock_response.choices[0].finish_reason = "tool_calls"
    mock_response.usage = None

    mock_pool.client.chat.completions.create = Mock(return_value=mock_response)

    client = LLMClient(llm_config, pool=mock_pool)
    messages = [{"role": "user", "content": "test"}]
    tools = [{"type": "function", "function": {"name": "test_tool"}}]

    response = client.chat(messages, tools=tools)

    # Verify pool methods called
    mock_pool.acquire.assert_called_once()
    mock_pool.release.assert_called_once()

    # Verify response has tool calls
    assert response.has_tool_calls
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "test_tool"
