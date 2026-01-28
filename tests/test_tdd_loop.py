import pytest
from unittest.mock import MagicMock, AsyncMock
from mini_nebulus.controllers.agent_controller import AgentController
from mini_nebulus.views.cli_view import CLIView


@pytest.mark.asyncio
async def test_run_tdd_cycle():
    mock_view = MagicMock(spec=CLIView)
    mock_view.print_agent_response = AsyncMock()
    mock_view.create_spinner.return_value.__enter__.return_value = None
    mock_view.create_spinner.return_value.__exit__.return_value = None

    controller = AgentController(view=mock_view)
    controller.process_turn = AsyncMock()  # Mock the actual processing

    # Run cycle
    await controller.run_tdd_cycle("Implement add(a,b)", "default")

    # Verify sequence
    assert controller.process_turn.call_count == 4

    # Check history additions
    history = controller.history_manager.get_session("default").get()
    # We started with empty/system.
    # 4 user prompts were added.
    user_msgs = [m for m in history if m["role"] == "user"]
    assert len(user_msgs) == 4
    assert "TDD Step 1" in user_msgs[0]["content"]
    assert "Now run the test" in user_msgs[1]["content"]
    assert "TDD Step 2" in user_msgs[2]["content"]
    assert "Now run the test again" in user_msgs[3]["content"]
