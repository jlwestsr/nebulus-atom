import pytest
from unittest.mock import AsyncMock, patch
from nebulus_atom.swarm.agents.router_agent import RouterAgent
import json


@pytest.mark.asyncio
async def test_router_classification():
    """Verify RouterAgent returns valid JSON classification."""

    # Mock OpenAIService to avoid real calls
    with patch("nebulus_atom.swarm.agents.base_agent.OpenAIService") as MockService:
        mock_instance = MockService.return_value
        # Mock simple completion
        mock_instance.create_chat_completion_simple = AsyncMock(
            return_value=json.dumps({"agent": "coder", "reasoning": "Test reasoning"})
        )

        router = RouterAgent()
        response = await router.process_turn("default_session", "Write a python script")

        data = json.loads(response)
        assert data["agent"] == "coder"
        assert "reasoning" in data


@pytest.mark.asyncio
async def test_router_no_input():
    """Verify default behavior on empty input."""
    # Mock not needed as it short-circuits
    with patch("nebulus_atom.swarm.agents.base_agent.OpenAIService"):
        router = RouterAgent()
        response = await router.process_turn("default_session", "")

        data = json.loads(response)
        assert data["agent"] == "coder"
