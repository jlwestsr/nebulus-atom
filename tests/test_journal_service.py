import pytest
from unittest.mock import MagicMock
import datetime
from mini_nebulus.services.journal_service import JournalService
from mini_nebulus.services.task_service import TaskService
from mini_nebulus.models.history import History


@pytest.fixture
def mock_task_service():
    service = MagicMock(spec=TaskService)
    service.get_plan_data.return_value = {
        "goal": "Test Goal",
        "tasks": [
            {"description": "Task 1", "status": "completed"},
            {"description": "Task 2", "status": "in_progress"},
        ],
    }
    return service


@pytest.fixture
def mock_history():
    history = MagicMock(spec=History)
    history.get.return_value = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "Do work"},
        {"role": "tool", "content": "File written: test.txt"},
    ]
    return history


def test_generate_journal(tmp_path, mock_task_service, mock_history):
    journal_dir = tmp_path / "journals"
    service = JournalService(journal_dir=str(journal_dir))

    result = service.generate_journal("test_session", mock_task_service, mock_history)

    today = datetime.date.today().strftime("%Y-%m-%d")
    expected_file = journal_dir / f"{today}_session_test_session.md"

    assert str(expected_file) in result
    assert expected_file.exists()

    content = expected_file.read_text()
    assert "# Session Journal" in content
    assert "**Session ID**: test_session" in content
    assert "## 🎯 Goal" in content
    assert "Test Goal" in content
    assert "- [x] Task 1" in content
    assert "- **User**: Hello" in content
    assert "- *System*: File written: test.txt" in content
