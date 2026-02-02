"""Tests for Nebulus Swarm Minion components."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nebulus_swarm.minion.github_client import GitHubClient, IssueDetails
from nebulus_swarm.minion.git_ops import GitOps, GitResult
from nebulus_swarm.minion.main import Minion, MinionConfig
from nebulus_swarm.minion.reporter import EventType, Reporter, ReportPayload


class TestIssueDetails:
    """Tests for IssueDetails dataclass."""

    def test_to_prompt_basic(self):
        issue = IssueDetails(
            number=42,
            title="Add multiply function",
            body="Please add a multiply function to the math module.",
            labels=["enhancement", "good-first-issue"],
            comments=[],
            author="testuser",
            state="open",
        )

        prompt = issue.to_prompt()

        assert "Issue #42" in prompt
        assert "Add multiply function" in prompt
        assert "Please add a multiply function" in prompt
        assert "enhancement, good-first-issue" in prompt

    def test_to_prompt_with_comments(self):
        issue = IssueDetails(
            number=1,
            title="Test issue",
            body="Description",
            labels=[],
            comments=["First comment", "Second comment"],
            author="user",
            state="open",
        )

        prompt = issue.to_prompt()

        assert "Comments" in prompt
        assert "First comment" in prompt
        assert "Second comment" in prompt

    def test_to_prompt_empty_body(self):
        issue = IssueDetails(
            number=1,
            title="Empty",
            body="",
            labels=[],
            comments=[],
            author="user",
            state="open",
        )

        prompt = issue.to_prompt()
        assert "No description provided" in prompt


class TestGitOps:
    """Tests for GitOps class."""

    @pytest.fixture
    def git_ops(self, tmp_path):
        """Create GitOps instance with temp workspace."""
        return GitOps(tmp_path, "owner/repo")

    def test_init(self, git_ops, tmp_path):
        assert git_ops.workspace == tmp_path
        assert git_ops.repo_name == "owner/repo"
        assert git_ops.repo_path == tmp_path / "repo"

    def test_run_git_success(self, git_ops, tmp_path):
        # Create a fake git repo
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="success output",
                stderr="",
            )

            result = git_ops._run_git(["status"])

            assert result.success
            assert result.output == "success output"
            assert result.return_code == 0

    def test_run_git_failure(self, git_ops, tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error message",
            )

            result = git_ops._run_git(["bad-command"])

            assert not result.success
            assert result.error == "error message"
            assert result.return_code == 1

    def test_get_current_branch(self, git_ops, tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="main\n",
                stderr="",
            )

            branch = git_ops.get_current_branch()
            assert branch == "main"

    def test_push_with_retry_success_first_try(self, git_ops, tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch.object(git_ops, "push") as mock_push:
            mock_push.return_value = GitResult(success=True, output="ok")

            result, rebased = git_ops.push_with_retry()

            assert result.success
            assert not rebased
            mock_push.assert_called_once()

    def test_push_with_retry_needs_rebase(self, git_ops, tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        call_count = 0

        def mock_push_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return GitResult(
                    success=False, output="", error="rejected non-fast-forward"
                )
            return GitResult(success=True, output="ok")

        with patch.object(git_ops, "push", side_effect=mock_push_side_effect):
            with patch.object(
                git_ops, "fetch", return_value=GitResult(success=True, output="")
            ):
                with patch.object(
                    git_ops, "rebase", return_value=GitResult(success=True, output="")
                ):
                    with patch.object(
                        git_ops, "get_current_branch", return_value="feature"
                    ):
                        result, rebased = git_ops.push_with_retry()

                        assert result.success
                        assert rebased


class TestReporter:
    """Tests for the Reporter class."""

    @pytest.fixture
    def reporter(self):
        return Reporter(
            minion_id="minion-test",
            issue_number=42,
            callback_url="http://overlord:8080/minion/report",
            heartbeat_interval=60,
        )

    def test_report_payload_to_dict(self):
        payload = ReportPayload(
            minion_id="minion-123",
            event=EventType.PROGRESS,
            issue=42,
            message="Working on it",
            data={"step": 3},
        )

        d = payload.to_dict()

        assert d["minion_id"] == "minion-123"
        assert d["event"] == "progress"
        assert d["issue"] == 42
        assert d["message"] == "Working on it"
        assert d["data"]["step"] == 3
        assert "timestamp" in d

    @pytest.mark.asyncio
    async def test_heartbeat_sends_request(self, reporter):
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            await reporter._get_session()
            result = await reporter.heartbeat("testing")

            assert result is True

    @pytest.mark.asyncio
    async def test_progress_updates_status(self, reporter):
        reporter._current_status = "idle"

        with patch.object(reporter, "_send_report", return_value=True) as mock_send:
            await reporter.progress("working hard")

            assert reporter._current_status == "working hard"
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_includes_pr_info(self, reporter):
        with patch.object(reporter, "_send_report", return_value=True) as mock_send:
            await reporter.complete(
                message="done",
                pr_number=100,
                pr_url="https://github.com/org/repo/pull/100",
                branch="feature-branch",
            )

            call_args = mock_send.call_args[0][0]
            assert call_args.event == EventType.COMPLETE
            assert call_args.data["pr_number"] == 100
            assert call_args.data["pr_url"] == "https://github.com/org/repo/pull/100"

    @pytest.mark.asyncio
    async def test_error_includes_details(self, reporter):
        with patch.object(reporter, "_send_report", return_value=True) as mock_send:
            await reporter.error(
                message="Something broke",
                error_type="git_error",
                details="Could not push",
            )

            call_args = mock_send.call_args[0][0]
            assert call_args.event == EventType.ERROR
            assert call_args.data["error_type"] == "git_error"
            assert call_args.data["details"] == "Could not push"


class TestMinionConfig:
    """Tests for MinionConfig."""

    def test_from_env(self):
        with patch.dict(
            os.environ,
            {
                "MINION_ID": "minion-abc",
                "GITHUB_REPO": "org/repo",
                "GITHUB_ISSUE": "42",
                "GITHUB_TOKEN": "ghp_test",
                "OVERLORD_CALLBACK_URL": "http://test:8080/report",
                "NEBULUS_BASE_URL": "http://llm:5000/v1",
                "NEBULUS_MODEL": "test-model",
                "NEBULUS_TIMEOUT": "300",
                "NEBULUS_STREAMING": "true",
                "MINION_TIMEOUT": "900",
            },
        ):
            config = MinionConfig.from_env()

            assert config.minion_id == "minion-abc"
            assert config.repo == "org/repo"
            assert config.issue_number == 42
            assert config.github_token == "ghp_test"
            assert config.nebulus_streaming is True
            assert config.minion_timeout == 900

    def test_validate_missing_required(self):
        config = MinionConfig(
            minion_id="test",
            repo="",
            issue_number=0,
            github_token="",
            overlord_callback_url="",
            nebulus_base_url="",
            nebulus_model="",
            nebulus_timeout=600,
            nebulus_streaming=False,
            minion_timeout=1800,
        )

        errors = config.validate()

        assert "GITHUB_REPO is required" in errors
        assert "GITHUB_ISSUE is required" in errors
        assert "GITHUB_TOKEN is required" in errors

    def test_validate_success(self):
        config = MinionConfig(
            minion_id="test",
            repo="org/repo",
            issue_number=1,
            github_token="token",
            overlord_callback_url="http://url",
            nebulus_base_url="http://llm",
            nebulus_model="model",
            nebulus_timeout=600,
            nebulus_streaming=False,
            minion_timeout=1800,
        )

        errors = config.validate()
        assert len(errors) == 0


class TestMinion:
    """Tests for the Minion orchestrator."""

    @pytest.fixture
    def config(self):
        return MinionConfig(
            minion_id="minion-test",
            repo="owner/repo",
            issue_number=42,
            github_token="ghp_test",
            overlord_callback_url="http://overlord:8080/report",
            nebulus_base_url="http://llm:5000/v1",
            nebulus_model="test-model",
            nebulus_timeout=600,
            nebulus_streaming=False,
            minion_timeout=1800,
        )

    def test_minion_init(self, config):
        minion = Minion(config)

        assert minion.config == config
        assert minion.github is not None
        assert minion.reporter is not None
        assert minion.git is None  # Not initialized until clone

    def test_generate_commit_message(self, config):
        minion = Minion(config)
        minion.issue = IssueDetails(
            number=42,
            title="Add new feature",
            body="Description",
            labels=[],
            comments=[],
            author="user",
            state="open",
        )

        message = minion._generate_commit_message()

        assert "Add new feature" in message
        assert "#42" in message
        assert "Minion-ID" in message

    def test_generate_commit_message_truncates_long_title(self, config):
        minion = Minion(config)
        minion.issue = IssueDetails(
            number=42,
            title="A" * 100,  # Very long title
            body="",
            labels=[],
            comments=[],
            author="user",
            state="open",
        )

        message = minion._generate_commit_message()

        # Title line should be truncated
        first_line = message.split("\n")[0]
        assert len(first_line) < 100
        assert "..." in first_line


class TestGitHubClient:
    """Tests for GitHubClient (with mocks)."""

    def test_get_clone_url_with_token(self):
        with patch("github.Github"):
            client = GitHubClient("test_token")

            mock_repo = MagicMock()
            mock_repo.clone_url = "https://github.com/owner/repo.git"

            with patch.object(client, "get_repo", return_value=mock_repo):
                url = client.get_clone_url("owner/repo")

                assert "x-access-token:test_token@" in url
                assert "github.com/owner/repo.git" in url

    def test_get_default_branch(self):
        with patch("github.Github"):
            client = GitHubClient("test_token")

            mock_repo = MagicMock()
            mock_repo.default_branch = "main"

            with patch.object(client, "get_repo", return_value=mock_repo):
                branch = client.get_default_branch("owner/repo")
                assert branch == "main"
