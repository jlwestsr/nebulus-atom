"""Tests for Nebulus Swarm components."""

import os
from datetime import datetime
from unittest.mock import patch

import pytest

from nebulus_swarm.config import (
    LLMConfig,
    MinionConfig,
    SwarmConfig,
)
from nebulus_swarm.models.minion import Minion, MinionStatus
from nebulus_swarm.overlord.command_parser import CommandParser, CommandType
from nebulus_swarm.overlord.docker_manager import DockerManager
from nebulus_swarm.overlord.state import OverlordState


class TestCommandParser:
    """Tests for the command parser."""

    def test_parse_status_command(self):
        parser = CommandParser()
        cmd = parser.parse("status")
        assert cmd.type == CommandType.STATUS

    def test_parse_status_variants(self):
        parser = CommandParser()

        variants = [
            "status",
            "what's the status",
            "whats the status",
            "how's it going",
            "what are the minions doing",
            "show me status",
        ]

        for text in variants:
            cmd = parser.parse(text)
            assert cmd.type == CommandType.STATUS, f"Failed for: {text}"

    def test_parse_work_with_issue_number(self):
        parser = CommandParser(default_repo="owner/repo")
        cmd = parser.parse("work on #42")
        assert cmd.type == CommandType.WORK
        assert cmd.issue_number == 42
        assert cmd.repo == "owner/repo"

    def test_parse_work_with_repo_and_issue(self):
        parser = CommandParser()
        cmd = parser.parse("work on myorg/myrepo#123")
        assert cmd.type == CommandType.WORK
        assert cmd.repo == "myorg/myrepo"
        assert cmd.issue_number == 123

    def test_parse_stop_by_issue(self):
        parser = CommandParser()
        cmd = parser.parse("stop #42")
        assert cmd.type == CommandType.STOP
        assert cmd.issue_number == 42

    def test_parse_stop_by_minion_id(self):
        parser = CommandParser()
        cmd = parser.parse("kill minion-abc123")
        assert cmd.type == CommandType.STOP
        assert cmd.minion_id == "abc123"

    def test_parse_queue(self):
        parser = CommandParser()
        cmd = parser.parse("queue")
        assert cmd.type == CommandType.QUEUE

    def test_parse_pause(self):
        parser = CommandParser()
        cmd = parser.parse("pause")
        assert cmd.type == CommandType.PAUSE

    def test_parse_resume(self):
        parser = CommandParser()
        cmd = parser.parse("resume")
        assert cmd.type == CommandType.RESUME

    def test_parse_history(self):
        parser = CommandParser()
        cmd = parser.parse("history")
        assert cmd.type == CommandType.HISTORY

    def test_parse_help(self):
        parser = CommandParser()
        cmd = parser.parse("help")
        assert cmd.type == CommandType.HELP

    def test_parse_unknown(self):
        parser = CommandParser()
        cmd = parser.parse("gibberish command xyz")
        assert cmd.type == CommandType.UNKNOWN
        assert "gibberish" in cmd.raw_text

    def test_format_help(self):
        parser = CommandParser()
        help_text = parser.format_help()
        assert "Overlord Commands" in help_text
        assert "status" in help_text
        assert "work on" in help_text


class TestOverlordState:
    """Tests for SQLite state management."""

    @pytest.fixture
    def state(self, tmp_path):
        """Create a state manager with temporary database."""
        db_path = str(tmp_path / "test_state.db")
        return OverlordState(db_path=db_path)

    @pytest.fixture
    def sample_minion(self):
        """Create a sample minion for testing."""
        return Minion(
            id="minion-test123",
            container_id="container-abc",
            repo="owner/repo",
            issue_number=42,
            status=MinionStatus.STARTING,
            started_at=datetime.now(),
        )

    def test_add_and_get_minion(self, state, sample_minion):
        state.add_minion(sample_minion)
        retrieved = state.get_minion("minion-test123")

        assert retrieved is not None
        assert retrieved.id == sample_minion.id
        assert retrieved.repo == sample_minion.repo
        assert retrieved.issue_number == sample_minion.issue_number
        assert retrieved.status == MinionStatus.STARTING

    def test_update_minion_status(self, state, sample_minion):
        state.add_minion(sample_minion)
        state.update_minion("minion-test123", status=MinionStatus.WORKING)

        retrieved = state.get_minion("minion-test123")
        assert retrieved.status == MinionStatus.WORKING

    def test_get_active_minions(self, state, sample_minion):
        state.add_minion(sample_minion)

        # Add a second minion that's working
        working_minion = Minion(
            id="minion-working",
            repo="owner/repo",
            issue_number=43,
            status=MinionStatus.WORKING,
            started_at=datetime.now(),
        )
        state.add_minion(working_minion)

        active = state.get_active_minions()
        assert len(active) == 2

    def test_get_minion_by_issue(self, state, sample_minion):
        state.add_minion(sample_minion)

        found = state.get_minion_by_issue("owner/repo", 42)
        assert found is not None
        assert found.id == "minion-test123"

        not_found = state.get_minion_by_issue("owner/repo", 999)
        assert not_found is None

    def test_record_completion(self, state, sample_minion):
        state.add_minion(sample_minion)
        state.record_completion(
            sample_minion, MinionStatus.COMPLETED, pr_number=100, error_message=None
        )

        # Minion should be removed from active
        assert state.get_minion("minion-test123") is None

        # Should appear in history
        history = state.get_work_history()
        assert len(history) == 1
        assert history[0]["minion_id"] == "minion-test123"
        assert history[0]["pr_number"] == 100
        assert history[0]["status"] == "completed"

    def test_remove_minion(self, state, sample_minion):
        state.add_minion(sample_minion)
        state.remove_minion("minion-test123")
        assert state.get_minion("minion-test123") is None


class TestDockerManager:
    """Tests for Docker manager (stub mode)."""

    @pytest.fixture
    def docker_manager(self):
        """Create a Docker manager for testing in stub mode."""
        minion_config = MinionConfig()
        llm_config = LLMConfig()
        return DockerManager(
            minion_config=minion_config,
            llm_config=llm_config,
            github_token="test-token",
            overlord_callback_url="http://test:8080/minion/report",
            stub_mode=True,
        )

    def test_spawn_minion(self, docker_manager):
        minion_id = docker_manager.spawn_minion("owner/repo", 42)
        assert minion_id.startswith("minion-")
        assert minion_id in [m["minion_id"] for m in docker_manager.list_minions()]

    def test_spawn_minion_with_custom_id(self, docker_manager):
        minion_id = docker_manager.spawn_minion(
            "owner/repo", 42, minion_id="custom-minion"
        )
        assert minion_id == "custom-minion"

    def test_kill_minion(self, docker_manager):
        minion_id = docker_manager.spawn_minion("owner/repo", 42)
        result = docker_manager.kill_minion(minion_id)
        assert result is True
        assert minion_id not in [m["minion_id"] for m in docker_manager.list_minions()]

    def test_kill_nonexistent_minion(self, docker_manager):
        result = docker_manager.kill_minion("nonexistent")
        assert result is False

    def test_list_minions(self, docker_manager):
        docker_manager.spawn_minion("owner/repo", 1)
        docker_manager.spawn_minion("owner/repo", 2)
        minions = docker_manager.list_minions()
        assert len(minions) == 2

    def test_get_minion_logs(self, docker_manager):
        minion_id = docker_manager.spawn_minion("owner/repo", 42)
        logs = docker_manager.get_minion_logs(minion_id)
        assert logs is not None
        assert "stub" in logs.lower()

    def test_get_logs_nonexistent_minion(self, docker_manager):
        logs = docker_manager.get_minion_logs("nonexistent")
        assert logs is None

    def test_cleanup_dead_containers(self, docker_manager):
        cleaned = docker_manager.cleanup_dead_containers()
        assert cleaned == 0  # Stub always returns 0


class TestSwarmConfig:
    """Tests for configuration management."""

    def test_config_from_env(self):
        """Test config creation from environment."""
        with patch.dict(
            os.environ,
            {
                "SLACK_BOT_TOKEN": "xoxb-test",
                "SLACK_APP_TOKEN": "xapp-test",
                "SLACK_CHANNEL_ID": "C12345",
                "GITHUB_TOKEN": "ghp_test",
                "GITHUB_WATCHED_REPOS": "owner/repo1,owner/repo2",
                "NEBULUS_BASE_URL": "http://test:5000/v1",
            },
        ):
            config = SwarmConfig.from_env()

            assert config.slack.bot_token == "xoxb-test"
            assert config.slack.app_token == "xapp-test"
            assert config.slack.channel_id == "C12345"
            assert config.github.token == "ghp_test"
            assert len(config.github.watched_repos) == 2
            assert "owner/repo1" in config.github.watched_repos

    def test_config_validation_missing_required(self):
        """Test that validation catches missing required fields."""
        config = SwarmConfig()
        errors = config.validate()

        assert "SLACK_BOT_TOKEN is required" in errors
        assert "SLACK_APP_TOKEN is required (for Socket Mode)" in errors
        assert "SLACK_CHANNEL_ID is required" in errors
        assert "GITHUB_TOKEN is required" in errors

    def test_config_validation_success(self):
        """Test validation passes with all required fields."""
        with patch.dict(
            os.environ,
            {
                "SLACK_BOT_TOKEN": "xoxb-test",
                "SLACK_APP_TOKEN": "xapp-test",
                "SLACK_CHANNEL_ID": "C12345",
                "GITHUB_TOKEN": "ghp_test",
                "GITHUB_WATCHED_REPOS": "owner/repo",
            },
        ):
            config = SwarmConfig.from_env()
            errors = config.validate()
            assert len(errors) == 0


class TestMinionModel:
    """Tests for Minion data model."""

    def test_minion_creation(self):
        minion = Minion(
            id="minion-123",
            repo="owner/repo",
            issue_number=42,
            status=MinionStatus.STARTING,
            started_at=datetime.now(),
        )
        assert minion.id == "minion-123"
        assert minion.status == MinionStatus.STARTING

    def test_minion_to_dict(self):
        started_at = datetime.now()
        minion = Minion(
            id="minion-123",
            repo="owner/repo",
            issue_number=42,
            status=MinionStatus.WORKING,
            started_at=started_at,
            pr_number=100,
        )
        d = minion.to_dict()

        assert d["id"] == "minion-123"
        assert d["status"] == "working"
        assert d["pr_number"] == 100
        assert d["started_at"] == started_at.isoformat()

    def test_minion_from_dict(self):
        started_at = datetime.now()
        data = {
            "id": "minion-abc",
            "container_id": "container-xyz",
            "repo": "org/project",
            "issue_number": 99,
            "status": "completed",
            "started_at": started_at.isoformat(),
            "last_heartbeat": None,
            "pr_number": 50,
            "error_message": None,
        }
        minion = Minion.from_dict(data)

        assert minion.id == "minion-abc"
        assert minion.status == MinionStatus.COMPLETED
        assert minion.pr_number == 50
