import pytest

pytest.importorskip("chromadb")

import os
from nebulus_atom.services.telemetry_service import TelemetryService
from nebulus_atom.services.tool_executor import ToolExecutor

TEST_DB_PATH = "nebulus_atom/data/test_telemetry.db"


@pytest.fixture
def clean_db():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    yield
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def test_event_logging(clean_db):
    """Verify raw logging capability."""
    service = TelemetryService(db_path=TEST_DB_PATH)

    # Log events
    service.log_thought("s1", "Thinking about life...")
    service.log_tool_call("s1", "ls", {"path": "."})

    # Retrieve
    trace = service.get_trace("s1")
    assert len(trace) == 2
    assert trace[0]["type"] == "THOUGHT"
    assert trace[0]["content"]["text"] == "Thinking about life..."
    assert trace[1]["type"] == "TOOL_CALL"
    assert trace[1]["content"]["tool"] == "ls"


@pytest.mark.asyncio
async def test_tool_executor_logging(clean_db):
    """Verify ToolExecutor integration."""

    # Initialize with test DB (Hack: we need to swap the manager's service)
    ToolExecutor.initialize()
    # Replace global service for test
    ToolExecutor.telemetry_manager.service = TelemetryService(db_path=TEST_DB_PATH)

    # Execute a tool
    await ToolExecutor.dispatch("read_file", {"path": "README.md"})

    # Verify trace
    service = ToolExecutor.telemetry_manager.get_service()
    trace = service.get_trace("default")

    # Expect: TOOL_CALL -> TOOL_RESULT (or ERROR if README missing)
    assert len(trace) >= 2
    assert trace[0]["type"] == "TOOL_CALL"
    assert trace[0]["content"]["tool"] == "read_file"
    assert trace[1]["type"] == "TOOL_RESULT" or trace[1]["type"] == "ERROR"
