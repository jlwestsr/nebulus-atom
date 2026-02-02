"""
Tool registry service for managing tool definitions.

Centralizes base tool definitions and provides merging with dynamic skills
and MCP tools.
"""

from typing import List, Dict, Any, Optional

from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class ToolRegistry:
    """Manages tool definitions and provides merged tool lists."""

    def __init__(self) -> None:
        """Initialize with base tool definitions."""
        self._base_tools: List[Dict[str, Any]] = self._build_base_tools()

    def _build_base_tools(self) -> List[Dict[str, Any]]:
        """Build the list of base tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_shell_command",
                    "description": "Run shell cmd.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_plan",
                    "description": "Init plan.",
                    "parameters": {
                        "type": "object",
                        "properties": {"goal": {"type": "string"}},
                        "required": ["goal"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_plan",
                    "description": "Auto-execute plan.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_context",
                    "description": "List pinned files.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "pin_file",
                    "description": "Pin file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_memory",
                    "description": "Search past conversation history.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge",
                    "description": "Search indexed codebase.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_skill",
                    "description": "Create a reusable Python skill (tool). The code must define a function.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "code": {"type": "string"},
                        },
                        "required": ["name", "code"],
                    },
                },
            },
        ]

    @property
    def base_tools(self) -> List[Dict[str, Any]]:
        """Get the base tool definitions."""
        return self._base_tools

    def get_all_tools(
        self,
        skill_service: Optional[Any] = None,
        mcp_service: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Merge base tools with dynamic skills and MCP tools.

        Deduplicates by tool name, keeping first occurrence (base tools priority).

        Args:
            skill_service: Optional skill service for dynamic skill definitions.
            mcp_service: Optional MCP service for MCP tool definitions.

        Returns:
            List of unique tool definitions.
        """
        all_tools = list(self._base_tools)

        try:
            if skill_service:
                skill_defs = skill_service.get_tool_definitions()
                all_tools.extend(skill_defs)

            if mcp_service:
                mcp_defs = mcp_service.get_tools()
                all_tools.extend(mcp_defs)
        except Exception as e:
            logger.warning(f"Error loading dynamic tools: {e}")

        return self._deduplicate_tools(all_tools)

    def _deduplicate_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate tools by name, keeping first occurrence.

        Args:
            tools: List of tool definitions.

        Returns:
            List of unique tool definitions.
        """
        seen: set[str] = set()
        unique_tools: List[Dict[str, Any]] = []

        for tool in tools:
            name = tool["function"]["name"]
            if name not in seen:
                seen.add(name)
                unique_tools.append(tool)

        return unique_tools

    def get_tool_list_string(
        self,
        tools: Optional[List[Dict[str, Any]]] = None,
        skill_service: Optional[Any] = None,
        mcp_service: Optional[Any] = None,
    ) -> str:
        """
        Generate a compact string listing all available tools.

        Args:
            tools: Optional pre-computed tool list. If None, will compute from services.
            skill_service: Optional skill service (used if tools is None).
            mcp_service: Optional MCP service (used if tools is None).

        Returns:
            Formatted string with tool names and descriptions.
        """
        if tools is None:
            tools = self.get_all_tools(skill_service, mcp_service)

        return "\n".join(
            f"- {t['function']['name']}: {t['function'].get('description', 'No description')}"
            for t in tools
        )
