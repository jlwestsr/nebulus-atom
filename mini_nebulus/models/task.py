from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import uuid


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    subtasks: List["Task"] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # List of Task IDs

    def mark_complete(self, result: str = ""):
        self.status = TaskStatus.COMPLETED
        self.result = result

    def mark_failed(self, error: str):
        self.status = TaskStatus.FAILED
        self.result = error

    def mark_in_progress(self):
        self.status = TaskStatus.IN_PROGRESS


@dataclass
class Plan:
    goal: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tasks: List[Task] = field(default_factory=list)

    def add_task(self, description: str, dependencies: List[str] = None) -> Task:
        task = Task(description=description, dependencies=dependencies or [])
        self.tasks.append(task)
        return task
