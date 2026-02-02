"""Tests for ToolRegistry service."""

from unittest.mock import MagicMock

from nebulus_atom.services.tool_registry import ToolRegistry


class TestToolRegistry:
    """Test cases for ToolRegistry."""

    def test_init_creates_base_tools(self):
        """ToolRegistry should initialize with base tools."""
        registry = ToolRegistry()
        assert len(registry.base_tools) == 10

    def test_base_tools_have_required_structure(self):
        """Each base tool should have type and function keys."""
        registry = ToolRegistry()
        for tool in registry.base_tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_base_tool_names(self):
        """Base tools should include expected tool names."""
        registry = ToolRegistry()
        tool_names = {t["function"]["name"] for t in registry.base_tools}

        expected_names = {
            "run_shell_command",
            "read_file",
            "write_file",
            "create_plan",
            "execute_plan",
            "list_context",
            "pin_file",
            "search_memory",
            "search_knowledge",
            "create_skill",
        }
        assert tool_names == expected_names

    def test_get_all_tools_without_services(self):
        """get_all_tools should return base tools when no services provided."""
        registry = ToolRegistry()
        tools = registry.get_all_tools()
        assert len(tools) == 10

    def test_get_all_tools_with_skill_service(self):
        """get_all_tools should merge skill definitions."""
        registry = ToolRegistry()

        skill_service = MagicMock()
        skill_service.get_tool_definitions.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "custom_skill",
                    "description": "A custom skill",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        tools = registry.get_all_tools(skill_service=skill_service)
        tool_names = {t["function"]["name"] for t in tools}
        assert "custom_skill" in tool_names
        assert len(tools) == 11

    def test_get_all_tools_deduplicates_by_name(self):
        """get_all_tools should deduplicate tools by name."""
        registry = ToolRegistry()

        skill_service = MagicMock()
        skill_service.get_tool_definitions.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",  # Duplicate of base tool
                    "description": "Overridden description",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        tools = registry.get_all_tools(skill_service=skill_service)
        assert len(tools) == 10

        read_file_tool = next(t for t in tools if t["function"]["name"] == "read_file")
        assert read_file_tool["function"]["description"] == "Read file."

    def test_get_all_tools_with_mcp_service(self):
        """get_all_tools should merge MCP tools."""
        registry = ToolRegistry()

        mcp_service = MagicMock()
        mcp_service.get_tools.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "mcp_tool",
                    "description": "An MCP tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        tools = registry.get_all_tools(mcp_service=mcp_service)
        tool_names = {t["function"]["name"] for t in tools}
        assert "mcp_tool" in tool_names

    def test_get_all_tools_handles_service_errors(self):
        """get_all_tools should handle service errors gracefully."""
        registry = ToolRegistry()

        skill_service = MagicMock()
        skill_service.get_tool_definitions.side_effect = Exception("Service error")

        tools = registry.get_all_tools(skill_service=skill_service)
        assert len(tools) == 10

    def test_get_tool_list_string(self):
        """get_tool_list_string should format tools as readable list."""
        registry = ToolRegistry()
        tool_string = registry.get_tool_list_string()

        assert "- run_shell_command: Run shell cmd." in tool_string
        assert "- read_file: Read file." in tool_string
        assert "- write_file: Write file." in tool_string

    def test_get_tool_list_string_with_custom_tools(self):
        """get_tool_list_string should work with provided tool list."""
        registry = ToolRegistry()

        custom_tools = [
            {
                "type": "function",
                "function": {
                    "name": "custom_tool",
                    "description": "Custom description",
                    "parameters": {},
                },
            }
        ]

        tool_string = registry.get_tool_list_string(tools=custom_tools)
        assert "- custom_tool: Custom description" in tool_string
        assert "run_shell_command" not in tool_string

    def test_deduplicate_preserves_order(self):
        """_deduplicate_tools should preserve first occurrence order."""
        registry = ToolRegistry()

        tools = [
            {"function": {"name": "a"}},
            {"function": {"name": "b"}},
            {"function": {"name": "a"}},  # Duplicate
            {"function": {"name": "c"}},
        ]

        result = registry._deduplicate_tools(tools)
        names = [t["function"]["name"] for t in result]
        assert names == ["a", "b", "c"]
