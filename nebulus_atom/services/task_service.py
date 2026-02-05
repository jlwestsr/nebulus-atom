import os
import json
from typing import Optional, Dict, List
from nebulus_atom.models.task import Plan, Task, TaskStatus
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class TaskService:
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.storage_path = os.path.join(
            os.getcwd(), ".nebulus_atom", "sessions", session_id, "plan.json"
        )
        self.current_plan: Optional[Plan] = None
        self.load_plan()

    def load_plan(self):
        """Loads plan from disk if it exists."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.current_plan = Plan.from_dict(data)
                logger.info(f"Loaded existing plan for session {self.session_id}")
            except Exception as e:
                logger.error(f"Failed to load plan for session {self.session_id}: {e}")

    def save_plan(self):
        """Saves current plan to disk."""
        if not self.current_plan:
            return

        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(self.current_plan.to_dict(), f, indent=2)
            logger.info(f"Saved plan for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to save plan for session {self.session_id}: {e}")

    def create_plan(self, goal: str) -> Plan:
        self.current_plan = Plan(goal=goal)
        self.save_plan()
        return self.current_plan

    def add_task(self, description: str, dependencies: List[str] = None) -> Task:
        if not self.current_plan:
            raise ValueError("No active plan. Create a plan first.")
        if isinstance(dependencies, str):
            dependencies = [dependencies]
        task = self.current_plan.add_task(description, dependencies)
        self.save_plan()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        if not self.current_plan:
            return None
        for task in self.current_plan.tasks:
            if task.id == task_id:
                return task
            for sub in task.subtasks:
                if sub.id == task_id:
                    return sub
        return None

    def update_task_status(self, task_id: str, status: TaskStatus, result: str = ""):
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = status
        if result:
            task.result = result
        self.save_plan()

    def get_plan_data(self) -> Optional[Dict]:
        if not self.current_plan:
            return None
        return {
            "goal": self.current_plan.goal,
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "status": t.status.value,
                    "dependencies": t.dependencies,
                }
                for t in self.current_plan.tasks
            ],
        }

    def get_plan_summary(self) -> str:
        data = self.get_plan_data()
        if not data:
            return "No active plan."

        summary = [f"Goal: {data['goal']}"]
        for i, task in enumerate(data["tasks"]):
            icon = " "
            if task["status"] == "completed":
                icon = "x"
            elif task["status"] == "in_progress":
                icon = ">"
            elif task["status"] == "failed":
                icon = "!"

            deps = (
                f" [Deps: {', '.join(task['dependencies'])}]"
                if task["dependencies"]
                else ""
            )
            summary.append(
                f"{i + 1}. [{icon}] {task['description']} (ID: {task['id']}){deps}"
            )
        return "\n".join(summary)


class TaskServiceManager:
    """Manages separate TaskService instances per session."""

    def __init__(self):
        self.sessions: Dict[str, TaskService] = {}

    def get_service(self, session_id: str) -> TaskService:
        if session_id not in self.sessions:
            self.sessions[session_id] = TaskService(session_id)
        return self.sessions[session_id]
