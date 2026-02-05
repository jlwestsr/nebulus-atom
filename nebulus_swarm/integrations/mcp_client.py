"""Optional MCP client for Nebulus appliance integration.

When ATOM_MCP_URL is configured, this client connects to an MCP server
and provides additional tools. When not configured, Atom works standalone.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30


@dataclass
class MCPTool:
    """A tool provided by the MCP server."""

    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPConfig:
    """Configuration for MCP client."""

    url: Optional[str] = None
    timeout: int = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls) -> "MCPConfig":
        """Load config from environment."""
        return cls(
            url=os.environ.get("ATOM_MCP_URL"),
            timeout=int(os.environ.get("ATOM_MCP_TIMEOUT", str(DEFAULT_TIMEOUT))),
        )

    @property
    def enabled(self) -> bool:
        """Check if MCP is configured."""
        return bool(self.url)


class MCPClient:
    """Client for connecting to an MCP server.

    This client is optional — when MCP is not configured or unavailable,
    it gracefully degrades and returns empty tool lists.
    """

    def __init__(self, config: Optional[MCPConfig] = None):
        """Initialize MCP client.

        Args:
            config: MCP configuration. If None, loads from environment.
        """
        self.config = config or MCPConfig.from_env()
        self._tools: List[MCPTool] = []
        self._available = False

        if self.config.enabled:
            self._check_availability()

    def _check_availability(self) -> None:
        """Check if MCP server is available."""
        if not self.config.url:
            return

        try:
            # Simple health check - try to list tools
            response = requests.post(
                f"{self.config.url}",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                timeout=self.config.timeout,
            )
            if response.status_code == 200:
                self._available = True
                data = response.json()
                if "result" in data and "tools" in data["result"]:
                    self._tools = [
                        MCPTool(
                            name=t.get("name", ""),
                            description=t.get("description", ""),
                            input_schema=t.get("inputSchema", {}),
                        )
                        for t in data["result"]["tools"]
                    ]
                logger.info(f"MCP server available with {len(self._tools)} tools")
            else:
                logger.warning(f"MCP server returned {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"MCP server unavailable: {e}")
            self._available = False

    @property
    def available(self) -> bool:
        """Check if MCP server is available."""
        return self._available

    @property
    def tools(self) -> List[MCPTool]:
        """Get list of available MCP tools."""
        return self._tools.copy()

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Optional[Any]:
        """Call an MCP tool.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result, or None if unavailable/error.
        """
        if not self._available or not self.config.url:
            logger.debug(f"MCP not available, skipping tool call: {name}")
            return None

        try:
            response = requests.post(
                f"{self.config.url}",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                    "id": 1,
                },
                timeout=self.config.timeout,
            )
            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                    return data["result"]
                if "error" in data:
                    logger.warning(f"MCP tool error: {data['error']}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"MCP tool call failed: {e}")
            return None

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions in OpenAI function format.

        Returns:
            List of tool definitions compatible with OpenAI's tools parameter.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": f"mcp_{tool.name}",  # Prefix to avoid conflicts
                    "description": tool.description,
                    "parameters": tool.input_schema
                    or {"type": "object", "properties": {}},
                },
            }
            for tool in self._tools
        ]


def get_mcp_client() -> MCPClient:
    """Get a cached MCP client instance."""
    global _mcp_client
    if "_mcp_client" not in globals() or _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


def reset_mcp_client() -> None:
    """Reset cached MCP client (for testing)."""
    global _mcp_client
    _mcp_client = None
