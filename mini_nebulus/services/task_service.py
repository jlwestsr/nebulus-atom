from typing import Optional, Dict, List
from mini_nebulus.models.task import Plan, Task, TaskStatus


class TaskService:
    def __init__(self):
        self.current_plan: Optional[Plan] = None

    def create_plan(self, goal: str) -> Plan:
        self.current_plan = Plan(goal=goal)
        return self.current_plan

    def add_task(self, description: str, dependencies: List[str] = None) -> Task:
        if not self.current_plan:
            raise ValueError("No active plan. Create a plan first.")
        return self.current_plan.add_task(description, dependencies)

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

        summary = [f"Goal: {data["goal"]}"]
        for i, task in enumerate(data["tasks"]):
            icon = " "
            if task["status"] == "completed":
                icon = "x"
            elif task["status"] == "in_progress":
                icon = ">"
            elif task["status"] == "failed":
                icon = "!"

            deps = (
                f" [Deps: {", ".join(task["dependencies"])}]"
                if task["dependencies"]
                else ""
            )
            summary.append(
                f"{i+1}. [{icon}] {task["description"]} (ID: {task["id"]}){deps}"
            )
        return "\n".join(summary)


class TaskServiceManager:
    """Manages separate TaskService instances per session."""

    def __init__(self):
        self.sessions: Dict[str, TaskService] = {}

    def get_service(self, session_id: str) -> TaskService:
        if session_id not in self.sessions:
            self.sessions[session_id] = TaskService()
        return self.sessions[session_id]
