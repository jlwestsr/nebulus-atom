"""Tests for CLI features added during UX improvements."""

import pytest
from unittest.mock import MagicMock, patch
from nebulus_atom.views.cli_view import CLIView


class TestSlashCommands:
    """Test slash command handling in CLI view."""

    @pytest.fixture
    def cli_view(self):
        """Create a CLIView with mocked console."""
        with patch("nebulus_atom.views.cli_view.PromptSession"):
            view = CLIView()
            view.console = MagicMock()
            return view

    @pytest.mark.asyncio
    async def test_clear_command(self, cli_view):
        """Test /clear command clears console."""
        result = await cli_view._handle_slash_command("/clear")
        assert result is True
        cli_view.console.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_cls_command(self, cli_view):
        """Test /cls command (alias for clear)."""
        result = await cli_view._handle_slash_command("/cls")
        assert result is True
        cli_view.console.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_help_command(self, cli_view):
        """Test /help command prints help."""
        result = await cli_view._handle_slash_command("/help")
        assert result is True
        cli_view.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_model_command(self, cli_view):
        """Test /model command shows model info."""
        result = await cli_view._handle_slash_command("/model")
        assert result is True
        cli_view.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_unknown_command(self, cli_view):
        """Test unknown command returns True and prints warning."""
        result = await cli_view._handle_slash_command("/unknown")
        assert result is True
        # Should print warning about unknown command
        calls = [str(call) for call in cli_view.console.print.call_args_list]
        assert any("Unknown command" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_exit_command_exits(self, cli_view):
        """Test /exit command exits the application."""
        with pytest.raises(SystemExit):
            await cli_view._handle_slash_command("/exit")


class TestToolDeduplication:
    """Test tool deduplication in ToolRegistry."""

    def test_get_current_tools_deduplicates(self):
        """Test that duplicate tools are removed."""
        from nebulus_atom.services.tool_registry import ToolRegistry

        registry = ToolRegistry()

        # Create a mock skill service that returns a duplicate tool
        mock_skill_service = MagicMock()
        mock_skill_service.get_tool_definitions.return_value = [
            {
                "type": "function",
                "function": {"name": "read_file", "description": "Duplicate read file"},
            }
        ]

        # Get tools with the mock skill service
        tools = registry.get_all_tools(skill_service=mock_skill_service)

        # Should have deduplicated - only one read_file (the base one takes priority)
        names = [t["function"]["name"] for t in tools]
        assert names.count("read_file") == 1
        # Verify it kept the base tool (first occurrence)
        read_file_tool = next(t for t in tools if t["function"]["name"] == "read_file")
        assert read_file_tool["function"]["description"] == "Read file."


class TestPromptMessage:
    """Test prompt message generation."""

    @pytest.fixture
    def cli_view(self):
        """Create a CLIView with mocked console."""
        with patch("nebulus_atom.views.cli_view.PromptSession"):
            view = CLIView()
            view.console = MagicMock()
            return view

    def test_standard_prompt(self, cli_view):
        """Test standard prompt shows cyan arrow."""
        cli_view.input_future = None
        cli_view.is_thinking = False
        prompt = cli_view.get_prompt_message()
        assert "ansicyan" in str(prompt)
        assert "❯" in str(prompt)

    def test_thinking_prompt(self, cli_view):
        """Test thinking state shows grey dots."""
        cli_view.input_future = None
        cli_view.is_thinking = True
        prompt = cli_view.get_prompt_message()
        assert "ansigray" in str(prompt)
        assert "..." in str(prompt)

    def test_input_prompt(self, cli_view):
        """Test input awaiting state shows magenta question mark."""
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            cli_view.input_future = loop.create_future()
            cli_view.is_thinking = False
            prompt = cli_view.get_prompt_message()
            assert "ansimagenta" in str(prompt)
            assert "?" in str(prompt)
        finally:
            loop.close()


class TestStreamingOutput:
    """Test streaming output methods."""

    @pytest.fixture
    def cli_view(self):
        """Create a CLIView with mocked console."""
        with patch("nebulus_atom.views.cli_view.PromptSession"):
            view = CLIView()
            view.console = MagicMock()
            return view

    def test_stream_start(self, cli_view):
        """Test stream start prints agent prefix."""
        cli_view.print_stream_start()
        cli_view.console.print.assert_called_once()
        call_args = str(cli_view.console.print.call_args)
        assert "Agent" in call_args

    def test_stream_chunk(self, cli_view):
        """Test stream chunk prints without newline."""
        cli_view.print_stream_chunk("Hello")
        cli_view.console.print.assert_called_with("Hello", end="", highlight=False)

    def test_stream_end(self, cli_view):
        """Test stream end prints newline."""
        cli_view.print_stream_end()
        cli_view.console.print.assert_called_once_with()
