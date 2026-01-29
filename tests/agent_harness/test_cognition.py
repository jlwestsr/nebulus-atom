import pytest
from mini_nebulus.controllers.agent_controller import AgentController


@pytest.mark.asyncio
async def test_extract_json_with_thought():
    """Verify extract_json parses 'thought' field correctly."""

    controller = AgentController()

    # Case 1: Standard Reflection
    response_text = '{"thought": "I need to check files.", "name": "run_shell_command", "arguments": {"command": "ls"}}'
    results = controller.extract_json(response_text)

    assert len(results) == 1
    assert results[0]["thought"] == "I need to check files."
    assert results[0]["name"] == "run_shell_command"
    assert results[0]["arguments"]["command"] == "ls"

    # Case 2: Legacy (No thought) - Should still work
    response_text_legacy = (
        '{"name": "write_file", "arguments": {"path": "test.py", "content": "pass"}}'
    )
    results_legacy = controller.extract_json(response_text_legacy)

    assert len(results_legacy) == 1
    assert results_legacy[0].get("thought") is None
    assert results_legacy[0]["name"] == "write_file"

    # Case 3: List of tools (Mixed)
    response_list = '[{"thought": "Thinking...", "name": "tool_a", "arguments": {}}, {"name": "tool_b", "arguments": {}}]'
    results_list = controller.extract_json(response_list)
    assert len(results_list) == 2
    assert results_list[0]["thought"] == "Thinking..."
    assert results_list[1].get("thought") is None
