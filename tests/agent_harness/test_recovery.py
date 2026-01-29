import pytest
from mini_nebulus.services.tool_executor import ToolExecutor


@pytest.mark.asyncio
async def test_file_not_found_interception():
    """Verify that FileNotFoundError is intercepted and analyzed."""

    # Initialize services
    ToolExecutor.initialize()

    # Trigger error
    result = await ToolExecutor.dispatch(
        "read_file", {"path": "/path/to/non_existent_ghost_file.txt"}
    )

    # Assert
    assert "❌ **Tool Failure detected" in result
    assert "Error: `File not found" in result
    assert "💡 **Recovery Hint**: The file you tried to access does not exist" in result
