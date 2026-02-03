import os
import datetime
from nebulus_atom.utils.logger import setup_logger
from nebulus_atom.services.task_service import TaskService
from nebulus_atom.models.history import History

logger = setup_logger(__name__)


class JournalService:
    def __init__(self, journal_dir: str = ".nebulus_atom/journals"):
        self.journal_dir = os.path.join(os.getcwd(), journal_dir)
        if not os.path.exists(self.journal_dir):
            os.makedirs(self.journal_dir, exist_ok=True)

    def generate_journal(
        self, session_id: str, task_service: TaskService, history: History
    ) -> str:
        """Generates a markdown journal for the session."""

        today = datetime.date.today().strftime("%Y-%m-%d")
        filename = f"{today}_session_{session_id}.md"
        filepath = os.path.join(self.journal_dir, filename)

        plan_data = task_service.get_plan_data()
        messages = history.get()

        journal_content = [
            f"# Session Journal - {today}",
            f"**Session ID**: {session_id}",
            "",
            "## 🎯 Goal",
            f"{plan_data.get('goal', 'No explicit goal set.') if plan_data else 'No active plan.'}",
            "",
            "## ✅ Completed Tasks",
        ]

        if plan_data:
            completed_tasks = [
                t for t in plan_data["tasks"] if t["status"] == "completed"
            ]
            if completed_tasks:
                for t in completed_tasks:
                    journal_content.append(f"- [x] {t['description']}")
            else:
                journal_content.append("_No tasks completed yet._")
        else:
            journal_content.append("_No active plan._")

        journal_content.append("")
        journal_content.append("## 📝 Activity Log")

        # Simple extraction of key events from history
        # We skip system messages
        for msg in messages:
            role = msg.get("role")
            if role == "user":
                content = msg.get("content", "").strip()
                if content:
                    journal_content.append(
                        f"- **User**: {content[:100]}..."
                        if len(content) > 100
                        else f"- **User**: {content}"
                    )
            elif role == "tool":
                # Check for specific tool outputs if tool_name was available (it isnt stored in msg directly easily)
                # But we can look at content.
                content = msg.get("content", "").strip()
                if content:
                    # Heuristic to find interesting tool outputs
                    if (
                        "File written" in content
                        or "Task added" in content
                        or "Plan created" in content
                    ):
                        journal_content.append(
                            f"  - *System*: {content.splitlines()[0]}"
                        )

        # Save to file
        try:
            with open(filepath, "w") as f:
                f.write("\n".join(journal_content))
            logger.info(f"Journal generated at {filepath}")
            return f"Journal generated: {filepath}"
        except Exception as e:
            logger.error(f"Failed to save journal: {e}")
            return f"Error generating journal: {e}"


class JournalServiceManager:
    def __init__(self):
        self.service = JournalService()

    def get_service(self, session_id: str = "default") -> JournalService:
        return self.service
