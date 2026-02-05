import pytest
from nebulus_atom.services.response_parser import ResponseParser


@pytest.mark.asyncio
async def test_extract_json_with_thought():
    """Verify extract_tool_calls parses 'thought' field correctly."""

    parser = ResponseParser()

    # Case 1: Standard Reflection
    response_text = '{"thought": "I need to check files.", "name": "run_shell_command", "arguments": {"command": "ls"}}'
    results = parser.extract_tool_calls(response_text)

    assert len(results) == 1
    assert results[0]["thought"] == "I need to check files."
    assert results[0]["name"] == "run_shell_command"
    assert results[0]["arguments"]["command"] == "ls"

    # Case 2: Legacy (No thought) - Should still work
    response_text_legacy = (
        '{"name": "write_file", "arguments": {"path": "test.py", "content": "pass"}}'
    )
    results_legacy = parser.extract_tool_calls(response_text_legacy)

    assert len(results_legacy) == 1
    assert results_legacy[0].get("thought") is None
    assert results_legacy[0]["name"] == "write_file"

    # Case 3: List of tools (Mixed)
    response_list = '[{"thought": "Thinking...", "name": "tool_a", "arguments": {}}, {"name": "tool_b", "arguments": {}}]'
    results_list = parser.extract_tool_calls(response_list)
    assert len(results_list) == 2
    assert results_list[0]["thought"] == "Thinking..."
    assert results_list[1].get("thought") is None
