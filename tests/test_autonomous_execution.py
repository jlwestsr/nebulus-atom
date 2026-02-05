import pytest

pytest.importorskip("openai")
pytest.importorskip("chromadb")

from unittest.mock import MagicMock, AsyncMock
from nebulus_atom.controllers.agent_controller import AgentController
from nebulus_atom.models.task import Task, TaskStatus, Plan
from nebulus_atom.services.tool_executor import ToolExecutor
from nebulus_atom.views.cli_view import CLIView


@pytest.mark.asyncio
async def test_autonomous_execution_loop():
    # Setup mocks
    mock_view = MagicMock(spec=CLIView)
    mock_view.console = MagicMock()
    mock_view.prompt_user.return_value = "/exit"

    # Mock services
    mock_task_service = MagicMock()
    ToolExecutor.task_manager.get_service = MagicMock(return_value=mock_task_service)

    # Create a plan with 2 tasks
    plan = Plan(goal="Test Auto Execution")
    task1 = Task(description="Task 1")
    task2 = Task(description="Task 2")
    plan.tasks = [task1, task2]
    mock_task_service.current_plan = plan

    def get_task_side_effect(tid):
        if tid == task1.id:
            return task1
        if tid == task2.id:
            return task2
        return None

    mock_task_service.get_task.side_effect = get_task_side_effect

    def update_status_side_effect(tid, status, result=""):
        t = get_task_side_effect(tid)
        if t:
            t.status = status

    mock_task_service.update_task_status.side_effect = update_status_side_effect

    controller = AgentController(view=mock_view)
    controller.auto_mode = True

    # Mock process_turn to simulate task completion
    async def mock_process_turn(session_id="default"):
        # Simulate the agent marking the current task as completed
        current_task = None
        for t in plan.tasks:
            if t.status == TaskStatus.IN_PROGRESS:
                current_task = t
                break

        if current_task:
            current_task.status = TaskStatus.COMPLETED

    controller.process_turn = AsyncMock(side_effect=mock_process_turn)

    await controller.chat_loop()

    assert task1.status == TaskStatus.COMPLETED
    assert task2.status == TaskStatus.COMPLETED
    assert not controller.auto_mode
    assert mock_view.console.print.call_count > 0


@pytest.mark.asyncio
async def test_auto_execution_stops_on_failure():
    # Setup mocks
    mock_view = MagicMock(spec=CLIView)
    mock_view.console = MagicMock()
    mock_view.prompt_user.return_value = "/exit"

    mock_task_service = MagicMock()
    ToolExecutor.task_manager.get_service = MagicMock(return_value=mock_task_service)

    plan = Plan(goal="Test Failure")
    task1 = Task(description="Task 1")
    plan.tasks = [task1]
    mock_task_service.current_plan = plan
    mock_task_service.get_task.return_value = task1

    def update_status_side_effect(tid, status, result=""):
        task1.status = status

    mock_task_service.update_task_status.side_effect = update_status_side_effect

    controller = AgentController(view=mock_view)
    controller.auto_mode = True

    async def mock_process_turn(session_id="default"):
        # Simulate failure
        task1.status = TaskStatus.FAILED

    controller.process_turn = AsyncMock(side_effect=mock_process_turn)

    await controller.chat_loop()

    assert task1.status == TaskStatus.FAILED
    assert not controller.auto_mode
    mock_view.console.print.assert_any_call(
        "Task failed. Stopping auto-execution.", style="bold red"
    )
