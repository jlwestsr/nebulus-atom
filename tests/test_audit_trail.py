"""Tests for the hybrid audit trail."""

import json
from datetime import datetime

from nebulus_swarm.overlord.audit_trail import (
    AuditTrail,
    LogEvent,
    SemanticLog,
    generate_signing_key,
)


class TestSemanticLog:
    def test_create_log(self):
        log = SemanticLog(
            event=LogEvent.TASK_RECEIVED,
            task_id="task-123",
            timestamp=datetime.now(),
            data={"issue": 42},
            reasoning="New issue assigned",
        )
        assert log.event == LogEvent.TASK_RECEIVED
        assert log.task_id == "task-123"
        assert log.data["issue"] == 42

    def test_to_dict_and_back(self):
        log = SemanticLog(
            event=LogEvent.TASK_DISPATCHED,
            task_id="task-456",
            timestamp=datetime.now(),
            data={"worker": "minion-1"},
            reasoning="Worker available",
        )
        d = log.to_dict()
        restored = SemanticLog.from_dict(d)
        assert restored.event == log.event
        assert restored.task_id == log.task_id
        assert restored.data == log.data

    def test_compute_hash_deterministic(self):
        log = SemanticLog(
            event=LogEvent.TASK_COMPLETE,
            task_id="task-789",
            timestamp=datetime(2026, 2, 5, 12, 0, 0),
            data={},
        )
        hash1 = log.compute_hash()
        hash2 = log.compute_hash()
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex


class TestAuditTrail:
    def test_create_trail(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        assert trail is not None

    def test_log_event(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        log = trail.log(
            LogEvent.TASK_RECEIVED,
            task_id="task-001",
            data={"source": "github"},
            reasoning="Issue #42 assigned",
        )
        assert log.event == LogEvent.TASK_RECEIVED
        assert log.task_id == "task-001"

    def test_get_logs_for_task(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        trail.log(LogEvent.TASK_RECEIVED, "task-A", {"n": 1})
        trail.log(LogEvent.TASK_DISPATCHED, "task-A", {"n": 2})
        trail.log(LogEvent.TASK_RECEIVED, "task-B", {"n": 3})

        logs = trail.get_logs_for_task("task-A")
        assert len(logs) == 2
        assert all(log.task_id == "task-A" for log in logs)

    def test_hash_chain_linked(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        trail.log(LogEvent.TASK_RECEIVED, "task-1", {})
        trail.log(LogEvent.TASK_DISPATCHED, "task-1", {})

        # Second log should reference first log's hash
        logs = trail.get_all_logs()
        assert logs[0].previous_hash != ""


class TestIntegrity:
    def test_verify_empty_trail(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        is_valid, issues = trail.verify_integrity()
        assert is_valid is True
        assert issues == []

    def test_verify_valid_chain(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        trail.log(LogEvent.TASK_RECEIVED, "task-1", {"a": 1})
        trail.log(LogEvent.TASK_DISPATCHED, "task-1", {"b": 2})
        trail.log(LogEvent.TASK_COMPLETE, "task-1", {"c": 3})

        is_valid, issues = trail.verify_integrity()
        assert is_valid is True
        assert issues == []

    def test_detect_tampered_hash(self, tmp_path):
        import sqlite3

        trail = AuditTrail(str(tmp_path / "audit.db"))
        trail.log(LogEvent.TASK_RECEIVED, "task-1", {})
        trail.log(LogEvent.TASK_COMPLETE, "task-1", {})

        # Tamper with stored hash
        conn = sqlite3.connect(str(tmp_path / "audit.db"))
        conn.execute("UPDATE audit_logs SET entry_hash = 'tampered' WHERE rowid = 1")
        conn.commit()
        conn.close()

        is_valid, issues = trail.verify_integrity()
        assert is_valid is False
        assert len(issues) >= 1


class TestExport:
    def test_export_all(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        trail.log(LogEvent.TASK_RECEIVED, "task-1", {"x": 1})
        trail.log(LogEvent.TASK_COMPLETE, "task-1", {"y": 2})

        export = trail.export()
        assert export["log_count"] == 2
        assert export["integrity_valid"] is True
        assert len(export["logs"]) == 2

    def test_export_by_task(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        trail.log(LogEvent.TASK_RECEIVED, "task-A", {})
        trail.log(LogEvent.TASK_RECEIVED, "task-B", {})

        export = trail.export(task_id="task-A")
        assert export["log_count"] == 1
        assert export["logs"][0]["task_id"] == "task-A"

    def test_export_json_serializable(self, tmp_path):
        trail = AuditTrail(str(tmp_path / "audit.db"))
        trail.log(LogEvent.TASK_RECEIVED, "task-1", {"nested": {"data": [1, 2, 3]}})

        export = trail.export()
        # Should not raise
        json_str = json.dumps(export)
        assert "task-1" in json_str


class TestSigning:
    def test_generate_key(self):
        # May return empty if cryptography not installed
        key = generate_signing_key()
        if key:
            assert len(key) == 32  # Ed25519 key size

    def test_signing_optional(self, tmp_path):
        # Should work without signing key
        trail = AuditTrail(str(tmp_path / "audit.db"), signing_key=None)
        log = trail.log(LogEvent.TASK_RECEIVED, "task-1", {})
        # Signature may be empty without key
        assert log is not None
