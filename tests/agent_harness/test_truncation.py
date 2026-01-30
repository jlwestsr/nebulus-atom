from nebulus_atom.services.tool_executor import ToolExecutor


def test_truncation_logic():
    """Verify truncate_output limits text correctly."""
    short_text = "Hello World"
    assert ToolExecutor.truncate_output(short_text) == short_text

    long_text = "A" * 3000
    truncated = ToolExecutor.truncate_output(long_text, max_length=2000)

    assert len(truncated) < 3000
    assert "Truncated" in truncated
    assert len(truncated.split("\n")[0]) == 2000
