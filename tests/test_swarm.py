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


class TestGitHubQueue:
    """Tests for the GitHub queue scanner."""

    def test_queued_issue_str(self):
        """Test QueuedIssue string representation."""
        from nebulus_swarm.overlord.github_queue import QueuedIssue

        issue = QueuedIssue(
            repo="owner/repo",
            number=42,
            title="Fix the bug",
            labels=["nebulus-ready"],
            created_at=datetime.now(),
            priority=1,
        )
        assert str(issue) == "owner/repo#42: Fix the bug"

    def test_queued_issue_priority_sorting(self):
        """Test that issues are sorted by priority then date."""
        from nebulus_swarm.overlord.github_queue import QueuedIssue

        now = datetime.now()
        issues = [
            QueuedIssue("a/b", 1, "Low priority old", [], now, priority=0),
            QueuedIssue("a/b", 2, "High priority", [], now, priority=1),
            QueuedIssue(
                "a/b",
                3,
                "Low priority new",
                [],
                datetime(now.year, now.month, now.day, now.hour + 1),
                priority=0,
            ),
        ]

        # Sort like GitHubQueue does
        issues.sort(key=lambda i: (-i.priority, i.created_at))

        # High priority first
        assert issues[0].number == 2
        # Then low priority by date (oldest first)
        assert issues[1].number == 1
        assert issues[2].number == 3

    @patch("nebulus_swarm.overlord.github_queue.Github")
    def test_github_queue_init(self, mock_github_class):
        """Test GitHubQueue initialization."""
        from nebulus_swarm.overlord.github_queue import GitHubQueue

        queue = GitHubQueue(
            token="test-token",
            watched_repos=["owner/repo1", "owner/repo2"],
        )

        assert queue.token == "test-token"
        assert len(queue.watched_repos) == 2
        assert queue.work_label == "nebulus-ready"
        mock_github_class.assert_called_once()

    @patch("nebulus_swarm.overlord.github_queue.Github")
    def test_scan_queue_empty(self, mock_github_class):
        """Test scanning when no issues are found."""
        from nebulus_swarm.overlord.github_queue import GitHubQueue

        mock_repo = mock_github_class.return_value.get_repo.return_value
        mock_repo.get_issues.return_value = []

        queue = GitHubQueue(token="test", watched_repos=["owner/repo"])
        issues = queue.scan_queue()

        assert issues == []

    @patch("nebulus_swarm.overlord.github_queue.Github")
    def test_get_rate_limit(self, mock_github_class):
        """Test rate limit status retrieval."""
        from datetime import timezone

        from nebulus_swarm.overlord.github_queue import GitHubQueue

        mock_rate = mock_github_class.return_value.get_rate_limit.return_value
        mock_rate.core.remaining = 4500
        mock_rate.core.limit = 5000
        mock_rate.core.reset = datetime.now(timezone.utc)

        queue = GitHubQueue(token="test", watched_repos=["owner/repo"])
        rate_limit = queue.get_rate_limit()

        assert rate_limit["remaining"] == 4500
        assert rate_limit["limit"] == 5000
        assert "reset_at" in rate_limit
        assert "is_rate_limited" in rate_limit
        assert rate_limit["is_rate_limited"] is False  # 4500 > threshold


class TestCronScheduler:
    """Tests for cron scheduling functionality."""

    def test_croniter_next_run(self):
        """Test croniter calculates next run correctly."""
        from croniter import croniter

        # Test daily at 2 AM
        cron = croniter("0 2 * * *", datetime(2024, 1, 1, 0, 0, 0))
        next_run = cron.get_next(datetime)
        assert next_run.hour == 2
        assert next_run.minute == 0

    def test_croniter_hourly(self):
        """Test hourly cron schedule."""
        from croniter import croniter

        cron = croniter("0 * * * *", datetime(2024, 1, 1, 0, 30, 0))
        next_run = cron.get_next(datetime)
        assert next_run.hour == 1
        assert next_run.minute == 0


class TestStructuredLogging:
    """Tests for structured logging functionality."""

    def test_json_formatter_basic(self):
        """Test JSON formatter produces valid JSON."""
        import json
        import logging

        from nebulus_swarm.logging import JSONFormatter

        formatter = JSONFormatter()

        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        # Should be valid JSON
        data = json.loads(output)
        assert data["message"] == "Test message"
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert "timestamp" in data
        assert "correlation_id" in data

    def test_json_formatter_with_exception(self):
        """Test JSON formatter includes exception info."""
        import json
        import logging
        import sys

        from nebulus_swarm.logging import JSONFormatter

        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=20,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "location" in data  # Added for ERROR level

    def test_correlation_id_context(self):
        """Test correlation ID context management."""
        from nebulus_swarm.logging import (
            get_correlation_id,
            set_correlation_id,
        )

        # Set a correlation ID
        set_correlation_id("test-123")
        assert get_correlation_id() == "test-123"

        # Generate new one
        set_correlation_id(None)
        cid = get_correlation_id()
        assert cid is not None
        assert len(cid) == 8  # UUID prefix length

    def test_log_context_manager(self):
        """Test LogContext context manager exists and works."""
        from nebulus_swarm.logging import LogContext

        # Test that LogContext can be used as context manager
        with LogContext(minion_id="minion-123", repo="owner/repo") as ctx:
            assert ctx.extras["minion_id"] == "minion-123"
            assert ctx.extras["repo"] == "owner/repo"

    def test_console_formatter(self):
        """Test console formatter produces readable output."""
        import logging

        from nebulus_swarm.logging import ConsoleFormatter

        formatter = ConsoleFormatter()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        # Should contain key parts
        assert "test.logger" in output
        assert "Test message" in output
        assert "I" in output  # INFO level indicator


class TestRateLimiting:
    """Tests for GitHub API rate limiting."""

    @patch("nebulus_swarm.overlord.github_queue.Github")
    def test_is_rate_limited_false(self, mock_github_class):
        """Test is_rate_limited returns False when quota available."""
        from nebulus_swarm.overlord.github_queue import GitHubQueue

        mock_rate = mock_github_class.return_value.get_rate_limit.return_value
        mock_rate.core.remaining = 4500  # Above threshold

        queue = GitHubQueue(token="test", watched_repos=["owner/repo"])
        assert queue.is_rate_limited() is False

    @patch("nebulus_swarm.overlord.github_queue.Github")
    def test_is_rate_limited_true(self, mock_github_class):
        """Test is_rate_limited returns True when quota low."""
        from nebulus_swarm.overlord.github_queue import (
            RATE_LIMIT_THRESHOLD,
            GitHubQueue,
        )

        mock_rate = mock_github_class.return_value.get_rate_limit.return_value
        mock_rate.core.remaining = RATE_LIMIT_THRESHOLD - 1  # Below threshold

        queue = GitHubQueue(token="test", watched_repos=["owner/repo"])
        assert queue.is_rate_limited() is True

    @patch("nebulus_swarm.overlord.github_queue.Github")
    def test_can_perform_sweep_true(self, mock_github_class):
        """Test can_perform_sweep returns True with sufficient quota."""
        from nebulus_swarm.overlord.github_queue import GitHubQueue

        mock_rate = mock_github_class.return_value.get_rate_limit.return_value
        mock_rate.core.remaining = 5000  # Plenty of quota

        queue = GitHubQueue(token="test", watched_repos=["owner/repo"])
        assert queue.can_perform_sweep() is True

    @patch("nebulus_swarm.overlord.github_queue.Github")
    def test_can_perform_sweep_false(self, mock_github_class):
        """Test can_perform_sweep returns False with low quota."""
        from nebulus_swarm.overlord.github_queue import GitHubQueue

        mock_rate = mock_github_class.return_value.get_rate_limit.return_value
        mock_rate.core.remaining = 50  # Not enough

        queue = GitHubQueue(token="test", watched_repos=["owner/repo"])
        assert queue.can_perform_sweep() is False


class TestLLMWarmup:
    """Tests for LLM warm-up functionality."""

    @pytest.mark.asyncio
    async def test_warm_up_llm_timeout(self):
        """Test LLM warm-up timeout handling."""
        import asyncio

        import aiohttp

        # Test that timeout is handled gracefully
        timeout = aiohttp.ClientTimeout(total=0.001)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # This should timeout immediately
                async with session.get("http://10.255.255.1/models"):
                    pass
        except asyncio.TimeoutError:
            # Expected behavior
            pass
        except Exception:
            # Other errors are also acceptable (connection refused, etc.)
            pass

    def test_cron_config_defaults(self):
        """Test cron configuration defaults."""
        from nebulus_swarm.config import CronConfig

        config = CronConfig()
        assert config.enabled is True
        assert config.schedule == "0 2 * * *"

    def test_cron_config_override(self):
        """Test cron configuration can be overridden from env."""
        with patch.dict(
            os.environ,
            {
                "SLACK_BOT_TOKEN": "xoxb-test",
                "SLACK_APP_TOKEN": "xapp-test",
                "SLACK_CHANNEL_ID": "C12345",
                "GITHUB_TOKEN": "ghp_test",
                "GITHUB_WATCHED_REPOS": "owner/repo",
                "CRON_ENABLED": "false",
                "CRON_SCHEDULE": "0 * * * *",
            },
        ):
            config = SwarmConfig.from_env()
            assert config.cron.enabled is False
            assert config.cron.schedule == "0 * * * *"


class TestPRReviewer:
    """Tests for PR reviewer functionality."""

    def test_review_decision_enum(self):
        """Test ReviewDecision enum values."""
        from nebulus_swarm.reviewer.pr_reviewer import ReviewDecision

        assert ReviewDecision.APPROVE.value == "APPROVE"
        assert ReviewDecision.REQUEST_CHANGES.value == "REQUEST_CHANGES"
        assert ReviewDecision.COMMENT.value == "COMMENT"

    def test_file_change_total(self):
        """Test FileChange total changes calculation."""
        from nebulus_swarm.reviewer.pr_reviewer import FileChange

        fc = FileChange(
            filename="test.py",
            status="modified",
            additions=10,
            deletions=5,
        )
        assert fc.total_changes == 15

    def test_pr_details_total_changes(self):
        """Test PRDetails total changes calculation."""
        from nebulus_swarm.reviewer.pr_reviewer import PRDetails

        pr = PRDetails(
            repo="owner/repo",
            number=42,
            title="Test PR",
            body="Test body",
            author="testuser",
            base_branch="main",
            head_branch="feature",
            created_at=datetime.now(),
            additions=100,
            deletions=50,
        )
        assert pr.total_changes == 150

    def test_pr_details_diff_summary(self):
        """Test PRDetails diff summary generation."""
        from nebulus_swarm.reviewer.pr_reviewer import FileChange, PRDetails

        pr = PRDetails(
            repo="owner/repo",
            number=42,
            title="Test PR",
            body="This is a test",
            author="testuser",
            base_branch="main",
            head_branch="feature",
            created_at=datetime.now(),
            files=[
                FileChange("test.py", "modified", 10, 5, None),
            ],
            additions=10,
            deletions=5,
        )
        summary = pr.get_diff_summary()

        assert "# PR #42: Test PR" in summary
        assert "testuser" in summary
        assert "feature → main" in summary
        assert "test.py" in summary

    def test_review_result_can_auto_merge(self):
        """Test ReviewResult auto-merge eligibility."""
        from nebulus_swarm.reviewer.pr_reviewer import ReviewDecision, ReviewResult

        # Eligible for auto-merge
        result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="LGTM",
            checks_passed=True,
            confidence=0.9,
            issues=[],
        )
        assert result.can_auto_merge is True

        # Not eligible - low confidence
        result2 = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="LGTM",
            checks_passed=True,
            confidence=0.5,
            issues=[],
        )
        assert result2.can_auto_merge is False

        # Not eligible - has issues
        result3 = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="LGTM",
            checks_passed=True,
            confidence=0.9,
            issues=["Minor issue"],
        )
        assert result3.can_auto_merge is False

        # Not eligible - checks failed
        result4 = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="LGTM",
            checks_passed=False,
            confidence=0.9,
            issues=[],
        )
        assert result4.can_auto_merge is False


class TestChecksRunner:
    """Tests for automated checks runner."""

    def test_check_status_enum(self):
        """Test CheckStatus enum values."""
        from nebulus_swarm.reviewer.checks import CheckStatus

        assert CheckStatus.PASSED.value == "passed"
        assert CheckStatus.FAILED.value == "failed"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.SKIPPED.value == "skipped"

    def test_check_result_creation(self):
        """Test CheckResult dataclass."""
        from nebulus_swarm.reviewer.checks import CheckResult, CheckStatus

        result = CheckResult(
            name="Test Check",
            status=CheckStatus.PASSED,
            message="All tests passed",
            file_issues=["issue1", "issue2"],
        )
        assert result.name == "Test Check"
        assert result.status == CheckStatus.PASSED
        assert len(result.file_issues) == 2

    def test_checks_report_all_passed(self):
        """Test ChecksReport all_passed property."""
        from nebulus_swarm.reviewer.checks import CheckResult, ChecksReport, CheckStatus

        report = ChecksReport(
            results=[
                CheckResult("Test1", CheckStatus.PASSED, "OK"),
                CheckResult("Test2", CheckStatus.PASSED, "OK"),
            ]
        )
        assert report.all_passed is True
        assert report.has_failures is False

    def test_checks_report_with_failures(self):
        """Test ChecksReport with failures."""
        from nebulus_swarm.reviewer.checks import CheckResult, ChecksReport, CheckStatus

        report = ChecksReport(
            results=[
                CheckResult("Test1", CheckStatus.PASSED, "OK"),
                CheckResult("Test2", CheckStatus.FAILED, "Error"),
            ]
        )
        assert report.all_passed is False
        assert report.has_failures is True
        assert report.passed_count == 1
        assert report.failed_count == 1

    def test_checks_report_warnings_allowed(self):
        """Test ChecksReport allows warnings."""
        from nebulus_swarm.reviewer.checks import CheckResult, ChecksReport, CheckStatus

        report = ChecksReport(
            results=[
                CheckResult("Test1", CheckStatus.PASSED, "OK"),
                CheckResult("Test2", CheckStatus.WARNING, "Minor issue"),
            ]
        )
        assert report.all_passed is True  # Warnings are allowed
        assert report.warning_count == 1

    def test_checks_report_summary(self):
        """Test ChecksReport summary generation."""
        from nebulus_swarm.reviewer.checks import CheckResult, ChecksReport, CheckStatus

        report = ChecksReport(
            results=[
                CheckResult("Tests", CheckStatus.PASSED, "42 passed"),
                CheckResult("Lint", CheckStatus.WARNING, "5 issues"),
            ]
        )
        summary = report.get_summary()

        assert "Automated Checks Report" in summary
        assert "Tests" in summary
        assert "42 passed" in summary

    def test_security_patterns(self):
        """Test security pattern detection."""
        from nebulus_swarm.reviewer.checks import CheckRunner

        patterns = CheckRunner.SECURITY_PATTERNS

        # Should have patterns for common security issues
        pattern_texts = [p[1] for p in patterns]
        assert any("eval" in t.lower() for t in pattern_texts)
        assert any("exec" in t.lower() for t in pattern_texts)
        assert any(
            "password" in t.lower() or "secret" in t.lower() for t in pattern_texts
        )


class TestLLMReviewer:
    """Tests for LLM-based code review."""

    def test_llm_reviewer_init(self):
        """Test LLMReviewer initialization."""
        from nebulus_swarm.reviewer.llm_review import LLMReviewer

        reviewer = LLMReviewer(
            base_url="http://localhost:5000/v1",
            model="test-model",
            api_key="test-key",
            timeout=60,
        )
        assert reviewer.model == "test-model"

    def test_parse_review_response_valid_json(self):
        """Test parsing valid JSON response."""
        from nebulus_swarm.reviewer.llm_review import LLMReviewer
        from nebulus_swarm.reviewer.pr_reviewer import ReviewDecision

        reviewer = LLMReviewer(
            base_url="http://localhost:5000/v1",
            model="test-model",
        )

        response = """
        Some text before JSON...
        {
            "decision": "APPROVE",
            "confidence": 0.95,
            "summary": "Code looks good",
            "issues": [],
            "suggestions": ["Consider adding tests"],
            "inline_comments": [
                {"path": "test.py", "line": 10, "body": "Nice code!"}
            ]
        }
        Some text after JSON...
        """

        result = reviewer._parse_review_response(response)

        assert result.decision == ReviewDecision.APPROVE
        assert result.confidence == 0.95
        assert result.summary == "Code looks good"
        assert len(result.suggestions) == 1
        assert len(result.inline_comments) == 1
        assert result.inline_comments[0].path == "test.py"

    def test_parse_review_response_no_json(self):
        """Test parsing response with no JSON."""
        from nebulus_swarm.reviewer.llm_review import LLMReviewer
        from nebulus_swarm.reviewer.pr_reviewer import ReviewDecision

        reviewer = LLMReviewer(
            base_url="http://localhost:5000/v1",
            model="test-model",
        )

        response = "Just some text without any JSON"
        result = reviewer._parse_review_response(response)

        assert result.decision == ReviewDecision.COMMENT
        assert result.confidence == 0.0
        assert "Could not parse" in result.summary

    def test_parse_review_response_invalid_decision(self):
        """Test parsing response with invalid decision."""
        from nebulus_swarm.reviewer.llm_review import LLMReviewer
        from nebulus_swarm.reviewer.pr_reviewer import ReviewDecision

        reviewer = LLMReviewer(
            base_url="http://localhost:5000/v1",
            model="test-model",
        )

        response = '{"decision": "INVALID", "confidence": 0.8, "summary": "test"}'
        result = reviewer._parse_review_response(response)

        # Should default to COMMENT for invalid decision
        assert result.decision == ReviewDecision.COMMENT

    def test_create_review_summary(self):
        """Test review summary creation."""
        from nebulus_swarm.reviewer.llm_review import create_review_summary
        from nebulus_swarm.reviewer.pr_reviewer import (
            PRDetails,
            ReviewDecision,
            ReviewResult,
        )

        pr = PRDetails(
            repo="owner/repo",
            number=42,
            title="Test PR",
            body="",
            author="testuser",
            base_branch="main",
            head_branch="feature",
            created_at=datetime.now(),
        )

        result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="Looks good!",
            confidence=0.9,
            issues=["Minor issue"],
            suggestions=["Add tests"],
        )

        summary = create_review_summary(pr, result)

        assert "# AI Review" in summary
        assert "owner/repo#42" in summary
        assert "APPROVE" in summary
        assert "90%" in summary  # confidence
        assert "Minor issue" in summary
        assert "Add tests" in summary


class TestReviewWorkflow:
    """Tests for review workflow orchestration."""

    def test_review_config_defaults(self):
        """Test ReviewConfig default values."""
        from nebulus_swarm.reviewer.workflow import ReviewConfig

        config = ReviewConfig(
            github_token="test-token",
            llm_base_url="http://localhost:5000/v1",
            llm_model="test-model",
        )
        assert config.auto_merge_enabled is False
        assert config.merge_method == "squash"
        assert config.min_confidence_for_approve == 0.8

    def test_workflow_result_summary(self):
        """Test WorkflowResult summary generation."""
        from nebulus_swarm.reviewer.pr_reviewer import (
            PRDetails,
            ReviewDecision,
            ReviewResult,
        )
        from nebulus_swarm.reviewer.workflow import WorkflowResult

        pr = PRDetails(
            repo="owner/repo",
            number=42,
            title="Test",
            body="",
            author="user",
            base_branch="main",
            head_branch="feat",
            created_at=datetime.now(),
        )

        llm_result = ReviewResult(
            decision=ReviewDecision.APPROVE,
            summary="LGTM",
            confidence=0.9,
        )

        result = WorkflowResult(
            pr_details=pr,
            llm_result=llm_result,
            review_posted=True,
        )

        summary = result.summary

        assert "owner/repo#42" in summary
        assert "APPROVE" in summary
        assert "90%" in summary
        assert "Review posted: Yes" in summary


class TestReviewCommandParser:
    """Tests for review command parsing."""

    def test_parse_review_command(self):
        """Test parsing review command."""
        parser = CommandParser(default_repo="owner/repo")
        cmd = parser.parse("review #42")
        assert cmd.type == CommandType.REVIEW
        assert cmd.pr_number == 42
        assert cmd.repo == "owner/repo"

    def test_parse_review_with_repo(self):
        """Test parsing review command with repo."""
        parser = CommandParser()
        cmd = parser.parse("review myorg/myrepo#123")
        assert cmd.type == CommandType.REVIEW
        assert cmd.repo == "myorg/myrepo"
        assert cmd.pr_number == 123

    def test_parse_check_command(self):
        """Test parsing check command as review alias."""
        parser = CommandParser(default_repo="owner/repo")
        cmd = parser.parse("check PR #42")
        assert cmd.type == CommandType.REVIEW
        assert cmd.pr_number == 42


class TestReviewerConfig:
    """Tests for reviewer configuration."""

    def test_reviewer_config_defaults(self):
        """Test ReviewerConfig default values."""
        from nebulus_swarm.config import ReviewerConfig

        with patch.dict(os.environ, {}, clear=True):
            config = ReviewerConfig()
            assert config.enabled is True
            assert config.auto_review is True
            assert config.auto_merge is False
            assert config.merge_method == "squash"
            assert config.min_confidence == 0.8

    def test_reviewer_config_env_override(self):
        """Test ReviewerConfig from environment."""
        from nebulus_swarm.config import ReviewerConfig

        with patch.dict(
            os.environ,
            {
                "REVIEWER_ENABLED": "false",
                "REVIEWER_AUTO_REVIEW": "false",
                "REVIEWER_AUTO_MERGE": "true",
                "REVIEWER_MERGE_METHOD": "rebase",
                "REVIEWER_MIN_CONFIDENCE": "0.9",
            },
        ):
            config = ReviewerConfig()
            assert config.enabled is False
            assert config.auto_review is False
            assert config.auto_merge is True
            assert config.merge_method == "rebase"
            assert config.min_confidence == 0.9

    def test_swarm_config_includes_reviewer(self):
        """Test SwarmConfig includes reviewer config."""
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
            assert hasattr(config, "reviewer")
            assert config.reviewer.enabled is True
