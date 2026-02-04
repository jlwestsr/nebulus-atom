import pytest

pytest.importorskip("openai")
pytest.importorskip("chromadb")

from unittest.mock import AsyncMock, patch
from nebulus_atom.controllers.agent_controller import AgentController
from nebulus_atom.services.tool_executor import ToolExecutor


def test_rag_tools_exposed():
    """Verify search_memory and search_knowledge are in base_tools."""
    controller = AgentController()
    tools = controller.get_current_tools()

    tool_names = [t["function"]["name"] for t in tools]
    assert "search_memory" in tool_names
    assert "search_knowledge" in tool_names


@pytest.mark.asyncio
async def test_rag_dispatch():
    """Verify ToolExecutor correctly dispatches memory aliases."""

    # Mock RAG Manager and Service
    mock_rag = AsyncMock()
    mock_rag.search_history.return_value = [{"content": "found memory"}]
    mock_rag.search_code.return_value = [{"content": "found code"}]

    with patch(
        "nebulus_atom.services.tool_executor.ToolExecutor.rag_manager.get_service",
        return_value=mock_rag,
    ):
        # Test search_memory -> search_history
        result_mem = await ToolExecutor.dispatch("search_memory", {"query": "test"})
        mock_rag.search_history.assert_called_with("test")
        assert "found memory" in str(result_mem)

        # Test search_knowledge -> search_code
        result_know = await ToolExecutor.dispatch("search_knowledge", {"query": "code"})
        mock_rag.search_code.assert_called_with("code")
        assert "found code" in str(result_know)
