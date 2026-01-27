import os
from contextlib import AsyncExitStack
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mini_nebulus.utils.logger import setup_logger

logger = setup_logger(__name__)


class MCPService:
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.tools: List[Dict[str, Any]] = []

    async def connect_server(
        self,
        name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
    ):
        """
        Connects to an MCP server via stdio.
        """
        logger.info(f"Connecting to MCP server '{name}' with command: {command} {args}")

        server_params = StdioServerParameters(
            command=command, args=args, env=env or os.environ.copy()
        )

        try:
            # We use the stdio_client context manager
            # Since we need persistent connections, we use AsyncExitStack to keep them alive
            # until the service is shutdown (or we explicitly close them).

            read, write = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )

            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )

            await session.initialize()

            self.sessions[name] = session

            # Discover tools
            response = await session.list_tools()
            for tool in response.tools:
                # We prefix tool names to avoid collisions: "mcp__<server>__<tool>"
                tool_name = f"mcp__{name}__{tool.name}"

                tool_def = {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool.description or f"MCP Tool from {name}",
                        "parameters": tool.inputSchema or {},
                    },
                }
                self.tools.append(tool_def)
                logger.info(f"Registered MCP tool: {tool_name}")

            return f"Connected to MCP server '{name}' and registered {len(response.tools)} tools."

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {name}: {e}", exc_info=True)
            return f"Error connecting to {name}: {str(e)}"

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """
        Calls a tool on a connected MCP server.
        Expects name format: mcp__<server>__<tool>
        """
        parts = name.split("__")
        if len(parts) < 3:
            raise ValueError(f"Invalid MCP tool name format: {name}")

        server_name = parts[1]
        tool_name = "__".join(parts[2:])  # In case tool name has underscores

        # Actually, the real tool name on the server is just the suffix.
        # But we need to handle if the server tool name had underscores.
        # Re-joining parts[2:] is correct if we split by exactly "__".

        # Wait, the tool name on the server is just "tool.name".
        # If tool.name was "get_weather", our internal name is "mcp__weather_server__get_weather".
        # Splitting by "__" gives ["mcp", "weather_server", "get_weather"].

        if server_name not in self.sessions:
            raise ValueError(f"MCP server '{server_name}' not connected.")

        session = self.sessions[server_name]

        logger.info(f"Calling MCP tool '{tool_name}' on server '{server_name}'")
        result = await session.call_tool(tool_name, arguments)

        # Result is CallToolResult
        # We need to extract the text content
        output = []
        if result.content:
            for item in result.content:
                if item.type == "text":
                    output.append(item.text)
                # Handle other types if needed (images, etc - for now just text)

        return "\n".join(output)

    def get_tools(self) -> List[Dict[str, Any]]:
        return self.tools

    async def shutdown(self):
        """Closes all connections."""
        await self.exit_stack.aclose()
        self.sessions.clear()
        self.tools.clear()
