import sqlite3
import json
import os
import time
import uuid
from typing import List, Dict, Any


class TelemetryService:
    def __init__(self, db_path: str = "mini_nebulus/data/telemetry.db"):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                timestamp REAL,
                event_type TEXT,
                content TEXT
            )
        """
        )
        conn.commit()
        conn.close()

    def log_event(self, session_id: str, event_type: str, content: Dict[str, Any]):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        event_id = str(uuid.uuid4())
        timestamp = time.time()

        cursor.execute(
            "INSERT INTO events (id, session_id, timestamp, event_type, content) VALUES (?, ?, ?, ?, ?)",
            (event_id, session_id, timestamp, event_type, json.dumps(content)),
        )
        conn.commit()
        conn.close()

    def log_thought(self, session_id: str, thought: str):
        self.log_event(session_id, "THOUGHT", {"text": thought})

    def log_tool_call(self, session_id: str, tool_name: str, args: Dict[str, Any]):
        self.log_event(session_id, "TOOL_CALL", {"tool": tool_name, "args": args})

    def log_tool_result(self, session_id: str, tool_name: str, result: str):
        self.log_event(session_id, "TOOL_RESULT", {"tool": tool_name, "result": result})

    def log_error(self, session_id: str, tool_name: str, error: str):
        self.log_event(session_id, "ERROR", {"tool": tool_name, "error": error})

    def get_trace(self, session_id: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        trace = []
        for row in rows:
            trace.append(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "type": row["event_type"],
                    "content": json.loads(row["content"]),
                }
            )
        return trace


class TelemetryServiceManager:
    def __init__(self):
        self.service = TelemetryService()

    def get_service(self, session_id: str = "default") -> TelemetryService:
        return self.service
