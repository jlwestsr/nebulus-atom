"""Tests for the GitHub issue sync module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nebulus_swarm.overlord.queue_sync import (
    _map_labels_to_priority,
    sync_github_issues,
)
from nebulus_swarm.overlord.registry import OverlordConfig, ProjectConfig
from nebulus_swarm.overlord.work_queue import WorkQueue


@pytest.fixture
def queue(tmp_path: Path) -> WorkQueue:
    return WorkQueue(db_path=tmp_path / "test_sync.db")


def _make_config(projects: dict[str, str]) -> OverlordConfig:
    """Build an OverlordConfig with project name -> remote mapping."""
    config = OverlordConfig()
    for name, remote in projects.items():
        config.projects[name] = ProjectConfig(
            name=name,
            path=Path(f"/fake/{name}"),
            remote=remote,
            role="library",
        )
    return config


def _gh_output(issues: list[dict]) -> MagicMock:
    """Create a mock CompletedProcess with JSON stdout."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = json.dumps(issues)
    mock.stderr = ""
    return mock


class TestSyncGithubIssues:
    @patch("nebulus_swarm.overlord.queue_sync.subprocess.run")
    def test_new_tasks_created(self, mock_run, queue: WorkQueue) -> None:
        """New issues create new tasks in backlog."""
        mock_run.return_value = _gh_output(
            [
                {"number": 1, "title": "Fix bug", "body": "Details", "labels": []},
                {"number": 2, "title": "Add feat", "body": "", "labels": []},
            ]
        )
        config = _make_config({"core": "jlwestsr/nebulus-core"})

        result = sync_github_issues(queue, config)

        assert result.new_count == 2
        assert result.updated_count == 0
        tasks = queue.list_tasks()
        assert len(tasks) == 2

    @patch("nebulus_swarm.overlord.queue_sync.subprocess.run")
    def test_existing_tasks_updated(self, mock_run, queue: WorkQueue) -> None:
        """Re-syncing updates title but not status."""
        mock_run.return_value = _gh_output(
            [
                {"number": 1, "title": "Fix bug", "body": "", "labels": []},
            ]
        )
        config = _make_config({"core": "jlwestsr/nebulus-core"})

        # First sync
        sync_github_issues(queue, config)
        # Transition to active
        tasks = queue.list_tasks()
        queue.transition(tasks[0].id, "active", "user")

        # Second sync with updated title
        mock_run.return_value = _gh_output(
            [
                {"number": 1, "title": "Fix bug v2", "body": "", "labels": []},
            ]
        )
        result = sync_github_issues(queue, config)

        assert result.updated_count == 1
        task = queue.list_tasks()[0]
        assert task.title == "Fix bug v2"
        assert task.status == "active"  # NOT reset

    @patch("nebulus_swarm.overlord.queue_sync.subprocess.run")
    def test_label_to_priority_mapping(self, mock_run, queue: WorkQueue) -> None:
        """Labels are mapped to priorities."""
        mock_run.return_value = _gh_output(
            [
                {
                    "number": 1,
                    "title": "Critical",
                    "body": "",
                    "labels": [{"name": "critical"}, {"name": "nebulus-ready"}],
                },
            ]
        )
        config = _make_config({"core": "jlwestsr/nebulus-core"})

        sync_github_issues(queue, config)
        task = queue.list_tasks()[0]
        assert task.priority == "critical"

    @patch("nebulus_swarm.overlord.queue_sync.subprocess.run")
    def test_project_filter(self, mock_run, queue: WorkQueue) -> None:
        """Project filter limits sync to one project."""
        mock_run.return_value = _gh_output(
            [
                {"number": 1, "title": "Task", "body": "", "labels": []},
            ]
        )
        config = _make_config(
            {
                "core": "jlwestsr/nebulus-core",
                "edge": "jlwestsr/nebulus-edge",
            }
        )

        result = sync_github_issues(queue, config, project_filter="core")

        assert result.new_count == 1
        # gh should only be called once (for core)
        assert mock_run.call_count == 1

    @patch("nebulus_swarm.overlord.queue_sync.subprocess.run")
    def test_gh_error_captured(self, mock_run, queue: WorkQueue) -> None:
        """gh CLI errors are captured in result.errors."""
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        mock.stderr = "auth required"
        mock_run.return_value = mock
        config = _make_config({"core": "jlwestsr/nebulus-core"})

        result = sync_github_issues(queue, config)

        assert len(result.errors) == 1
        assert "gh CLI error" in result.errors[0]

    @patch("nebulus_swarm.overlord.queue_sync.subprocess.run")
    def test_empty_response(self, mock_run, queue: WorkQueue) -> None:
        """Empty gh response is handled gracefully."""
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "[]"
        mock.stderr = ""
        mock_run.return_value = mock
        config = _make_config({"core": "jlwestsr/nebulus-core"})

        result = sync_github_issues(queue, config)

        assert result.new_count == 0
        assert result.updated_count == 0
        assert len(result.errors) == 0

    @patch("nebulus_swarm.overlord.queue_sync.subprocess.run")
    def test_external_source_format(self, mock_run, queue: WorkQueue) -> None:
        """External source follows 'github:{remote}' format."""
        mock_run.return_value = _gh_output(
            [
                {"number": 42, "title": "Test", "body": "", "labels": []},
            ]
        )
        config = _make_config({"core": "jlwestsr/nebulus-core"})

        sync_github_issues(queue, config)
        task = queue.list_tasks()[0]
        assert task.external_source == "github:jlwestsr/nebulus-core"
        assert task.external_id == "42"


class TestLabelMapping:
    def test_critical(self) -> None:
        assert _map_labels_to_priority(["critical"]) == "critical"

    def test_p0(self) -> None:
        assert _map_labels_to_priority(["p0", "bug"]) == "critical"

    def test_high(self) -> None:
        assert _map_labels_to_priority(["high-priority"]) == "high"

    def test_low(self) -> None:
        assert _map_labels_to_priority(["low-priority"]) == "low"

    def test_default_medium(self) -> None:
        assert _map_labels_to_priority(["enhancement"]) == "medium"
