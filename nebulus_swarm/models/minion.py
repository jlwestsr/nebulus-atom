"""Minion data model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class MinionStatus(Enum):
    """Status of a Minion worker."""

    STARTING = "starting"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class Minion:
    """Represents a Minion worker instance."""

    id: str
    container_id: Optional[str] = None
    repo: str = ""
    issue_number: int = 0
    status: MinionStatus = MinionStatus.STARTING
    started_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: Optional[datetime] = None
    pr_number: Optional[int] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "container_id": self.container_id,
            "repo": self.repo,
            "issue_number": self.issue_number,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat()
            if self.last_heartbeat
            else None,
            "pr_number": self.pr_number,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Minion":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            container_id=data.get("container_id"),
            repo=data.get("repo", ""),
            issue_number=data.get("issue_number", 0),
            status=MinionStatus(data.get("status", "starting")),
            started_at=datetime.fromisoformat(data["started_at"])
            if data.get("started_at")
            else datetime.now(),
            last_heartbeat=datetime.fromisoformat(data["last_heartbeat"])
            if data.get("last_heartbeat")
            else None,
            pr_number=data.get("pr_number"),
            error_message=data.get("error_message"),
        )
