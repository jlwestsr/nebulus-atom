"""Tests for MCP client integration."""

from unittest.mock import MagicMock, patch

from nebulus_swarm.integrations.mcp_client import (
    MCPClient,
    MCPConfig,
    MCPTool,
    get_mcp_client,
    reset_mcp_client,
)


class TestMCPConfig:
    def test_default_disabled(self):
        """Config with no URL is disabled."""
        config = MCPConfig()
        assert config.enabled is False
        assert config.url is None

    def test_enabled_when_url_set(self):
        """Config with URL is enabled."""
        config = MCPConfig(url="http://localhost:8000/mcp")
        assert config.enabled is True

    def test_from_env_no_vars(self, monkeypatch):
        """from_env returns disabled config when no env vars."""
        monkeypatch.delenv("ATOM_MCP_URL", raising=False)
        monkeypatch.delenv("ATOM_MCP_TIMEOUT", raising=False)
        config = MCPConfig.from_env()
        assert config.enabled is False
        assert config.timeout == 30

    def test_from_env_with_vars(self, monkeypatch):
        """from_env reads env vars."""
        monkeypatch.setenv("ATOM_MCP_URL", "http://mcp:8000")
        monkeypatch.setenv("ATOM_MCP_TIMEOUT", "60")
        config = MCPConfig.from_env()
        assert config.url == "http://mcp:8000"
        assert config.timeout == 60


class TestMCPTool:
    def test_tool_fields(self):
        """MCPTool has expected fields."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert "properties" in tool.input_schema


class TestMCPClientDisabled:
    def test_disabled_by_default(self):
        """Client is not available when MCP not configured."""
        config = MCPConfig()  # No URL
        client = MCPClient(config)
        assert client.available is False
        assert client.tools == []

    def test_disabled_tool_definitions_empty(self):
        """Disabled client returns empty tool definitions."""
        config = MCPConfig()
        client = MCPClient(config)
        assert client.get_tool_definitions() == []

    def test_disabled_call_tool_returns_none(self):
        """Disabled client returns None for tool calls."""
        config = MCPConfig()
        client = MCPClient(config)
        result = client.call_tool("any_tool", {"arg": "value"})
        assert result is None


class TestMCPClientUnavailable:
    def test_graceful_degradation_connection_error(self):
        """Client handles connection errors gracefully."""
        config = MCPConfig(url="http://nonexistent:9999/mcp")
        with patch("nebulus_swarm.integrations.mcp_client.requests.post") as mock_post:
            import requests

            mock_post.side_effect = requests.exceptions.ConnectionError(
                "Connection refused"
            )
            client = MCPClient(config)
            assert client.available is False
            assert client.tools == []

    def test_graceful_degradation_http_error(self):
        """Client handles HTTP errors gracefully."""
        config = MCPConfig(url="http://localhost:8000/mcp")
        with patch("nebulus_swarm.integrations.mcp_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_post.return_value = mock_response
            client = MCPClient(config)
            assert client.available is False


class TestMCPClientAvailable:
    def test_available_with_tools(self):
        """Client parses tools from server response."""
        config = MCPConfig(url="http://localhost:8000/mcp")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "tools": [
                    {"name": "ltm_search", "description": "Search long-term memory"},
                    {
                        "name": "doc_parse",
                        "description": "Parse documents",
                        "inputSchema": {"type": "object"},
                    },
                ]
            }
        }

        with patch("nebulus_swarm.integrations.mcp_client.requests.post") as mock_post:
            mock_post.return_value = mock_response
            client = MCPClient(config)

            assert client.available is True
            assert len(client.tools) == 2
            assert client.tools[0].name == "ltm_search"
            assert client.tools[1].name == "doc_parse"

    def test_tool_definitions_format(self):
        """get_tool_definitions returns OpenAI-compatible format."""
        config = MCPConfig(url="http://localhost:8000/mcp")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "tools": [
                    {
                        "name": "ltm_search",
                        "description": "Search memory",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    },
                ]
            }
        }

        with patch("nebulus_swarm.integrations.mcp_client.requests.post") as mock_post:
            mock_post.return_value = mock_response
            client = MCPClient(config)

            defs = client.get_tool_definitions()
            assert len(defs) == 1
            assert defs[0]["type"] == "function"
            assert defs[0]["function"]["name"] == "mcp_ltm_search"  # Prefixed
            assert defs[0]["function"]["description"] == "Search memory"

    def test_call_tool_success(self):
        """call_tool returns result on success."""
        config = MCPConfig(url="http://localhost:8000/mcp")

        # First call for initialization
        init_response = MagicMock()
        init_response.status_code = 200
        init_response.json.return_value = {"result": {"tools": []}}

        # Second call for tool call
        call_response = MagicMock()
        call_response.status_code = 200
        call_response.json.return_value = {"result": {"content": "found it"}}

        with patch("nebulus_swarm.integrations.mcp_client.requests.post") as mock_post:
            mock_post.side_effect = [init_response, call_response]
            client = MCPClient(config)

            result = client.call_tool("ltm_search", {"query": "test"})
            assert result == {"content": "found it"}

    def test_call_tool_error_response(self):
        """call_tool handles error responses."""
        config = MCPConfig(url="http://localhost:8000/mcp")

        init_response = MagicMock()
        init_response.status_code = 200
        init_response.json.return_value = {"result": {"tools": []}}

        error_response = MagicMock()
        error_response.status_code = 200
        error_response.json.return_value = {
            "error": {"code": -32600, "message": "Invalid"}
        }

        with patch("nebulus_swarm.integrations.mcp_client.requests.post") as mock_post:
            mock_post.side_effect = [init_response, error_response]
            client = MCPClient(config)

            result = client.call_tool("bad_tool", {})
            assert result is None


class TestMCPClientCache:
    def test_get_mcp_client_singleton(self, monkeypatch):
        """get_mcp_client returns same instance."""
        monkeypatch.delenv("ATOM_MCP_URL", raising=False)
        reset_mcp_client()

        client1 = get_mcp_client()
        client2 = get_mcp_client()
        assert client1 is client2

    def test_reset_clears_cache(self, monkeypatch):
        """reset_mcp_client clears cached instance."""
        monkeypatch.delenv("ATOM_MCP_URL", raising=False)
        reset_mcp_client()

        client1 = get_mcp_client()
        reset_mcp_client()
        client2 = get_mcp_client()
        assert client1 is not client2
