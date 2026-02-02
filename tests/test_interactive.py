import pytest
from unittest.mock import MagicMock, AsyncMock
from nebulus_atom.controllers.agent_controller import AgentController
from nebulus_atom.views.cli_view import CLIView


@pytest.mark.asyncio
async def test_interactive_clarification():
    mock_view = MagicMock(spec=CLIView)
    mock_view.ask_user_input = AsyncMock(return_value="My name is User")
    mock_view.print_agent_response = AsyncMock()
    mock_view.print_tool_output = AsyncMock()
    mock_view.print_plan = AsyncMock()
    mock_view.print_error = AsyncMock()

    # Add console mock
    mock_view.console = MagicMock()

    # Context manager mock for spinner
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = None
    mock_view.create_spinner.return_value = cm

    controller = AgentController(view=mock_view)

    # Mock OpenAI response to call ask_user
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.delta.content = None

    mock_tool_call = MagicMock()
    mock_tool_call.index = 0
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "ask_user"
    mock_tool_call.function.arguments = '{"question": "What is your name?"}'

    mock_choice.delta.tool_calls = [mock_tool_call]
    mock_response.choices = [mock_choice]

    mock_response_2 = MagicMock()
    mock_choice_2 = MagicMock()
    mock_choice_2.delta.content = "Hello User"
    mock_choice_2.delta.tool_calls = None
    mock_response_2.choices = [mock_choice_2]

    # Synchronous generator
    async def mock_stream_sequence(*args, **kwargs):
        if controller._openai.create_chat_completion.call_count == 1:
            yield mock_response
        else:
            yield mock_response_2

    controller._openai.create_chat_completion = MagicMock(
        side_effect=mock_stream_sequence
    )

    # Initialize a session
    controller.history_manager.get_session("default").add("user", "Hello")

    # Run the controller
    await controller.process_turn("default")

    # Verify ask_user_input was called
    mock_view.ask_user_input.assert_called_with("What is your name?")

    # Verify history has the tool output (stored as user message with Tool prefix)
    history = controller.history_manager.get_session("default").get()

    # Find user message containing tool output
    tool_msg = next(
        (
            m
            for m in history
            if m["role"] == "user" and "Tool 'ask_user'" in m.get("content", "")
        ),
        None,
    )
    assert tool_msg is not None, f"Tool message not found in history: {history}"
    assert "My name is User" in tool_msg["content"]
