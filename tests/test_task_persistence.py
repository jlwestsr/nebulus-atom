import os
import shutil
import pytest
from nebulus_atom.services.task_service import TaskService, TaskServiceManager
from nebulus_atom.models.task import TaskStatus


@pytest.fixture
def clean_storage():
    """Ensures a clean .nebulus_atom directory for tests."""
    path = os.path.join(os.getcwd(), ".nebulus_atom", "sessions", "test_session")
    if os.path.exists(path):
        shutil.rmtree(path)
    yield
    if os.path.exists(path):
        shutil.rmtree(path)


def test_task_persistence(clean_storage):
    session_id = "test_session"

    # 1. Create a service and a plan
    service1 = TaskService(session_id)
    service1.create_plan(goal="World Domination")
    task = service1.add_task(description="Buy cat food")
    service1.update_task_status(task.id, TaskStatus.IN_PROGRESS)

    # Verify file exists
    assert os.path.exists(service1.storage_path)

    # 2. Re-instantiate service (simulating restart)
    service2 = TaskService(session_id)

    # Verify plan loaded
    assert service2.current_plan is not None
    assert service2.current_plan.goal == "World Domination"
    assert len(service2.current_plan.tasks) == 1

    loaded_task = service2.current_plan.tasks[0]
    assert loaded_task.description == "Buy cat food"
    assert loaded_task.status == TaskStatus.IN_PROGRESS
    assert loaded_task.id == task.id


def test_manager_session_isolation(clean_storage):
    manager = TaskServiceManager()
    s1 = manager.get_service("test_session_1")
    s2 = manager.get_service("test_session_2")

    s1.create_plan("Plan 1")
    s2.create_plan("Plan 2")

    assert s1.current_plan.goal == "Plan 1"
    assert s2.current_plan.goal == "Plan 2"
    assert s1.storage_path != s2.storage_path
