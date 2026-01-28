import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from mini_nebulus.services.mcp_service import MCPService


@pytest.mark.asyncio
async def test_connect_server_env_merge():
    service = MCPService()

    with patch("mini_nebulus.services.mcp_service.StdioServerParameters") as MockParams:
        with patch("mini_nebulus.services.mcp_service.stdio_client") as mock_client:
            # Mock context manager
            mock_client.return_value.__aenter__.return_value = (
                MagicMock(),
                MagicMock(),
            )
            mock_client.return_value.__aexit__.return_value = None

            with patch(
                "mini_nebulus.services.mcp_service.ClientSession"
            ) as MockSession:
                session = AsyncMock()
                MockSession.return_value.__aenter__.return_value = session

                # Mock tool response
                tool = MagicMock()
                tool.name = "test_tool"
                tool.description = "Test"
                tool.inputSchema = {}
                session.list_tools.return_value.tools = [tool]

                # Call connect
                await service.connect_server("test", "echo", [], env={"MY_VAR": "123"})

                # Check StdioServerParameters call
                args, kwargs = MockParams.call_args
                passed_env = kwargs["env"]

                assert "MY_VAR" in passed_env
                assert passed_env["MY_VAR"] == "123"
                # Ensure system env is preserved (assuming PATH exists)
                import os

                if "PATH" in os.environ:
                    assert "PATH" in passed_env
