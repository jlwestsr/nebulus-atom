"""Tests for Minion clarifying questions feature."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nebulus_swarm.minion.agent.minion_agent import (
    AgentResult,
    AgentStatus,
    MinionAgent,
)
from nebulus_swarm.minion.reporter import EventType, Reporter

# Mock slack_bolt before importing Overlord modules (not installed in dev env)
sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("slack_bolt.adapter", MagicMock())
sys.modules.setdefault("slack_bolt.adapter.socket_mode", MagicMock())
sys.modules.setdefault("slack_bolt.adapter.socket_mode.async_handler", MagicMock())
sys.modules.setdefault("slack_bolt.async_app", MagicMock())


# ---------------------------------------------------------------------------
# Reporter: QUESTION event + poll_answer
# ---------------------------------------------------------------------------


class TestReporterQuestion:
    """Tests for Reporter question/poll_answer methods."""

    def test_question_event_type_exists(self):
        """QUESTION event type is defined."""
        assert EventType.QUESTION.value == "question"

    @pytest.mark.asyncio
    async def test_question_sends_report(self):
        """question() sends a QUESTION event to the Overlord."""
        reporter = Reporter(
            minion_id="m-123",
            issue_number=42,
            callback_url="http://overlord:8080/minion/report",
        )
        reporter._send_report = AsyncMock(return_value=True)

        result = await reporter.question(
            question_text="Which endpoint?",
            blocker_type="unclear_requirements",
            question_id="q-m-123-1",
        )

        assert result is True
        reporter._send_report.assert_called_once()
        payload = reporter._send_report.call_args[0][0]
        assert payload.event == EventType.QUESTION
        assert payload.message == "Which endpoint?"
        assert payload.data["blocker_type"] == "unclear_requirements"
        assert payload.data["question_id"] == "q-m-123-1"

    @pytest.mark.asyncio
    async def test_question_updates_status(self):
        """question() sets status to 'waiting for answer'."""
        reporter = Reporter(
            minion_id="m-123",
            issue_number=42,
            callback_url="http://overlord:8080/minion/report",
        )
        reporter._send_report = AsyncMock(return_value=True)

        await reporter.question("Q?", "unclear", "q-1")

        assert reporter._current_status == "waiting for answer"

    @pytest.mark.asyncio
    async def test_poll_answer_returns_answer(self):
        """poll_answer() returns the answer when available."""
        reporter = Reporter(
            minion_id="m-123",
            issue_number=42,
            callback_url="http://overlord:8080/minion/report",
        )

        # Mock the session to return an answered response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"answered": True, "answer": "Focus on /api/users"}
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        reporter._get_session = AsyncMock(return_value=mock_session)

        answer = await reporter.poll_answer("q-1", timeout=5, interval=1)

        assert answer == "Focus on /api/users"

    @pytest.mark.asyncio
    async def test_poll_answer_returns_none_on_timeout(self):
        """poll_answer() returns None after timeout with no answer."""
        reporter = Reporter(
            minion_id="m-123",
            issue_number=42,
            callback_url="http://overlord:8080/minion/report",
        )

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"answered": False})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        reporter._get_session = AsyncMock(return_value=mock_session)

        answer = await reporter.poll_answer("q-1", timeout=2, interval=1)

        assert answer is None

    @pytest.mark.asyncio
    async def test_poll_answer_derives_url_from_callback(self):
        """poll_answer() derives the answer URL from callback_url."""
        reporter = Reporter(
            minion_id="m-123",
            issue_number=42,
            callback_url="http://overlord:8080/minion/report",
        )

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"answered": True, "answer": "yes"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        reporter._get_session = AsyncMock(return_value=mock_session)

        await reporter.poll_answer("q-1", timeout=2, interval=1)

        # Check the URL used
        call_args = mock_session.get.call_args
        url = call_args[0][0]
        assert url == "http://overlord:8080/minion/answer/m-123"


# ---------------------------------------------------------------------------
# MinionAgent: inject_message + resume
# ---------------------------------------------------------------------------


class TestAgentInjectMessage:
    """Tests for MinionAgent.inject_message and resume behavior."""

    def _make_agent(self):
        """Create a minimal MinionAgent for testing."""
        from nebulus_swarm.minion.agent.llm_client import LLMConfig

        config = LLMConfig(
            base_url="http://localhost:5000/v1",
            model="test-model",
            timeout=10,
        )
        return MinionAgent(
            llm_config=config,
            system_prompt="Test prompt",
            tools=[],
            tool_executor=lambda name, args: None,
        )

    def test_inject_message_appends_to_history(self):
        """inject_message() appends a user message."""
        agent = self._make_agent()
        # Simulate having run first (creates messages list)
        agent._messages = [{"role": "system", "content": "Test prompt"}]

        agent.inject_message("Human response: use /api/users")

        assert len(agent._messages) == 2
        assert agent._messages[1]["role"] == "user"
        assert "Human response" in agent._messages[1]["content"]

    def test_inject_message_resets_completed(self):
        """inject_message() resets _completed so run() can continue."""
        agent = self._make_agent()
        agent._messages = [{"role": "system", "content": "Test prompt"}]
        agent._completed = True
        agent._result = AgentResult(
            status=AgentStatus.BLOCKED,
            summary="blocked",
            turns_used=1,
        )

        agent.inject_message("Answer")

        assert agent._completed is False
        assert agent._result is None

    def test_run_initializes_messages_only_once(self):
        """run() only creates the system message list on first call."""
        agent = self._make_agent()

        # Simulate messages already set (from prior run + inject)
        agent._messages = [
            {"role": "system", "content": "Test prompt"},
            {"role": "user", "content": "Injected answer"},
        ]
        agent._completed = True  # Will exit immediately

        agent.run()

        # Should NOT have reset messages
        assert len(agent._messages) >= 2
        assert agent._messages[1]["content"] == "Injected answer"


# ---------------------------------------------------------------------------
# Minion _do_work question loop
# ---------------------------------------------------------------------------


class TestMinionQuestionLoop:
    """Tests for the Minion._do_work question loop."""

    def _make_minion(self):
        """Create a Minion with mocked dependencies."""
        from nebulus_swarm.minion.main import Minion, MinionConfig

        config = MinionConfig(
            minion_id="m-test",
            repo="owner/repo",
            issue_number=42,
            github_token="ghp_test",
            overlord_callback_url="http://overlord:8080/minion/report",
            nebulus_base_url="http://localhost:5000/v1",
            nebulus_model="test-model",
            nebulus_timeout=60,
            nebulus_streaming=False,
            minion_timeout=1800,
        )
        minion = Minion(config)

        # Mock GitHub client
        minion.github = MagicMock()

        # Mock reporter
        minion.reporter = AsyncMock()
        minion.reporter.update_status = MagicMock()
        minion.reporter.question = AsyncMock(return_value=True)
        minion.reporter.poll_answer = AsyncMock(return_value=None)

        # Mock git ops
        minion.git = MagicMock()
        minion.git.repo_path = "/workspace"

        # Mock issue
        minion.issue = MagicMock()
        minion.issue.number = 42
        minion.issue.title = "Test issue"
        minion.issue.body = "Test body"
        minion.issue.labels = []
        minion.issue.author = "testuser"

        return minion

    @pytest.mark.asyncio
    async def test_completed_returns_true(self):
        """_do_work returns True when agent completes successfully."""
        minion = self._make_minion()

        with patch("nebulus_swarm.minion.main.MinionAgent") as MockAgent, patch(
            "nebulus_swarm.minion.main.ToolExecutor"
        ):
            mock_agent = MockAgent.return_value
            mock_agent.run.return_value = AgentResult(
                status=AgentStatus.COMPLETED,
                summary="Done",
                files_changed=["src/main.py"],
                turns_used=5,
            )

            result = await minion._do_work()

        assert result is True

    @pytest.mark.asyncio
    async def test_blocked_with_question_sends_and_polls(self):
        """_do_work sends question and polls for answer when agent is blocked."""
        minion = self._make_minion()

        call_count = 0

        def mock_run():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AgentResult(
                    status=AgentStatus.BLOCKED,
                    summary="Unclear",
                    blocker_type="unclear_requirements",
                    question="Which endpoint?",
                    turns_used=3,
                )
            return AgentResult(
                status=AgentStatus.COMPLETED,
                summary="Done",
                turns_used=5,
            )

        with patch("nebulus_swarm.minion.main.MinionAgent") as MockAgent, patch(
            "nebulus_swarm.minion.main.ToolExecutor"
        ):
            mock_agent = MockAgent.return_value
            mock_agent.run.side_effect = mock_run
            mock_agent.inject_message = MagicMock()

            minion.reporter.poll_answer = AsyncMock(return_value="Focus on /api/users")

            result = await minion._do_work()

        assert result is True
        minion.reporter.question.assert_called_once()
        minion.reporter.poll_answer.assert_called_once()
        mock_agent.inject_message.assert_called_once_with(
            "Human response: Focus on /api/users"
        )

    @pytest.mark.asyncio
    async def test_blocked_with_question_timeout_continues(self):
        """When poll_answer times out, agent gets 'use best judgment' message."""
        minion = self._make_minion()

        call_count = 0

        def mock_run():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AgentResult(
                    status=AgentStatus.BLOCKED,
                    summary="Unclear",
                    blocker_type="unclear_requirements",
                    question="Which endpoint?",
                    turns_used=3,
                )
            return AgentResult(
                status=AgentStatus.COMPLETED,
                summary="Done",
                turns_used=5,
            )

        with patch("nebulus_swarm.minion.main.MinionAgent") as MockAgent, patch(
            "nebulus_swarm.minion.main.ToolExecutor"
        ):
            mock_agent = MockAgent.return_value
            mock_agent.run.side_effect = mock_run
            mock_agent.inject_message = MagicMock()

            # poll_answer returns None (timeout)
            minion.reporter.poll_answer = AsyncMock(return_value=None)

            result = await minion._do_work()

        assert result is True
        inject_msg = mock_agent.inject_message.call_args[0][0]
        assert "best judgment" in inject_msg.lower()

    @pytest.mark.asyncio
    async def test_max_questions_cap(self):
        """After MAX_QUESTIONS, agent gets 'no more questions' message."""
        minion = self._make_minion()

        call_count = 0

        def mock_run():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:  # 3 questions + 1 after cap
                return AgentResult(
                    status=AgentStatus.BLOCKED,
                    summary="Unclear",
                    blocker_type="unclear_requirements",
                    question=f"Question {call_count}?",
                    turns_used=call_count,
                )
            return AgentResult(
                status=AgentStatus.COMPLETED,
                summary="Done",
                turns_used=5,
            )

        with patch("nebulus_swarm.minion.main.MinionAgent") as MockAgent, patch(
            "nebulus_swarm.minion.main.ToolExecutor"
        ):
            mock_agent = MockAgent.return_value
            mock_agent.run.side_effect = mock_run
            mock_agent.inject_message = MagicMock()

            minion.reporter.poll_answer = AsyncMock(return_value=None)

            result = await minion._do_work()

        assert result is True
        # 3 questions sent to reporter, 4th triggers the cap
        assert minion.reporter.question.call_count == 3
        # 4th inject_message should be "no more questions"
        last_inject = mock_agent.inject_message.call_args_list[3][0][0]
        assert "no more questions" in last_inject.lower()

    @pytest.mark.asyncio
    async def test_blocked_without_question_fails(self):
        """_do_work returns False when agent is blocked without a question."""
        minion = self._make_minion()

        with patch("nebulus_swarm.minion.main.MinionAgent") as MockAgent, patch(
            "nebulus_swarm.minion.main.ToolExecutor"
        ):
            mock_agent = MockAgent.return_value
            mock_agent.run.return_value = AgentResult(
                status=AgentStatus.BLOCKED,
                summary="Cannot proceed",
                blocker_type="missing_dependency",
                turns_used=2,
            )

            result = await minion._do_work()

        assert result is False
        minion.reporter.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_status_fails(self):
        """_do_work returns False on ERROR status."""
        minion = self._make_minion()

        with patch("nebulus_swarm.minion.main.MinionAgent") as MockAgent, patch(
            "nebulus_swarm.minion.main.ToolExecutor"
        ):
            mock_agent = MockAgent.return_value
            mock_agent.run.return_value = AgentResult(
                status=AgentStatus.ERROR,
                summary="Too many errors",
                error="Connection refused",
                turns_used=1,
            )

            result = await minion._do_work()

        assert result is False

    @pytest.mark.asyncio
    async def test_reporter_send_failure_continues(self):
        """When reporter.question() fails, agent continues with best judgment."""
        minion = self._make_minion()

        call_count = 0

        def mock_run():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AgentResult(
                    status=AgentStatus.BLOCKED,
                    summary="Unclear",
                    blocker_type="unclear_requirements",
                    question="Which endpoint?",
                    turns_used=3,
                )
            return AgentResult(
                status=AgentStatus.COMPLETED,
                summary="Done",
                turns_used=5,
            )

        with patch("nebulus_swarm.minion.main.MinionAgent") as MockAgent, patch(
            "nebulus_swarm.minion.main.ToolExecutor"
        ):
            mock_agent = MockAgent.return_value
            mock_agent.run.side_effect = mock_run
            mock_agent.inject_message = MagicMock()

            # reporter.question returns False (failed to send)
            minion.reporter.question = AsyncMock(return_value=False)

            result = await minion._do_work()

        assert result is True
        inject_msg = mock_agent.inject_message.call_args[0][0]
        assert "best judgment" in inject_msg.lower()
        # poll_answer should NOT have been called
        minion.reporter.poll_answer.assert_not_called()


# ---------------------------------------------------------------------------
# Overlord: PendingQuestion + answer endpoint + thread matching
# ---------------------------------------------------------------------------


class TestOverlordPendingQuestion:
    """Tests for PendingQuestion dataclass."""

    def test_pending_question_creation(self):
        """PendingQuestion can be created with required fields."""
        from nebulus_swarm.overlord.main import PendingQuestion

        pq = PendingQuestion(
            minion_id="m-123",
            question_id="q-m-123-1",
            issue_number=42,
            repo="owner/repo",
            question_text="Which endpoint?",
            thread_ts="1234567890.123456",
        )

        assert pq.minion_id == "m-123"
        assert pq.answered is False
        assert pq.answer is None

    def test_pending_question_answer(self):
        """PendingQuestion can be answered."""
        from nebulus_swarm.overlord.main import PendingQuestion

        pq = PendingQuestion(
            minion_id="m-123",
            question_id="q-1",
            issue_number=42,
            repo="owner/repo",
            question_text="Q?",
            thread_ts="ts-1",
        )

        pq.answer = "Use /api/users"
        pq.answered = True

        assert pq.answered is True
        assert pq.answer == "Use /api/users"


class TestOverlordThreadReply:
    """Tests for Overlord thread reply matching."""

    def test_thread_reply_matches_pending_question(self):
        """Thread reply matching finds and answers the right question."""
        from nebulus_swarm.overlord.main import Overlord, PendingQuestion

        # Create Overlord with minimal config
        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._pending_questions = {}

        pq = PendingQuestion(
            minion_id="m-123",
            question_id="q-1",
            issue_number=42,
            repo="owner/repo",
            question_text="Q?",
            thread_ts="ts-match",
        )
        overlord._pending_questions["m-123"] = pq

        overlord._handle_thread_reply("ts-match", "Use /api/users")

        assert pq.answered is True
        assert pq.answer == "Use /api/users"

    def test_thread_reply_ignores_unmatched(self):
        """Thread reply does nothing for unmatched thread_ts."""
        from nebulus_swarm.overlord.main import Overlord, PendingQuestion

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._pending_questions = {}

        pq = PendingQuestion(
            minion_id="m-123",
            question_id="q-1",
            issue_number=42,
            repo="owner/repo",
            question_text="Q?",
            thread_ts="ts-123",
        )
        overlord._pending_questions["m-123"] = pq

        overlord._handle_thread_reply("ts-wrong", "Answer")

        assert pq.answered is False

    def test_thread_reply_ignores_already_answered(self):
        """Thread reply ignores questions that are already answered."""
        from nebulus_swarm.overlord.main import Overlord, PendingQuestion

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._pending_questions = {}

        pq = PendingQuestion(
            minion_id="m-123",
            question_id="q-1",
            issue_number=42,
            repo="owner/repo",
            question_text="Q?",
            thread_ts="ts-123",
        )
        pq.answered = True
        pq.answer = "First answer"
        overlord._pending_questions["m-123"] = pq

        overlord._handle_thread_reply("ts-123", "Second answer")

        assert pq.answer == "First answer"  # Not overwritten


class TestOverlordAnswerEndpoint:
    """Tests for the answer HTTP endpoint."""

    def _mock_request(self, minion_id: str):
        """Create a mock request with match_info."""
        request = MagicMock()
        request.match_info = {"minion_id": minion_id}
        return request

    @pytest.mark.asyncio
    async def test_answer_returns_false_when_not_answered(self):
        """GET /minion/answer/<id> returns answered=false when pending."""
        import json

        from nebulus_swarm.overlord.main import Overlord, PendingQuestion

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._pending_questions = {}

        pq = PendingQuestion(
            minion_id="m-123",
            question_id="q-1",
            issue_number=42,
            repo="owner/repo",
            question_text="Q?",
            thread_ts="ts-1",
        )
        overlord._pending_questions["m-123"] = pq

        request = self._mock_request("m-123")
        response = await overlord._answer_handler(request)
        body = json.loads(response.body)
        assert body["answered"] is False

    @pytest.mark.asyncio
    async def test_answer_returns_true_when_answered(self):
        """GET /minion/answer/<id> returns the answer when available."""
        import json

        from nebulus_swarm.overlord.main import Overlord, PendingQuestion

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._pending_questions = {}

        pq = PendingQuestion(
            minion_id="m-123",
            question_id="q-1",
            issue_number=42,
            repo="owner/repo",
            question_text="Q?",
            thread_ts="ts-1",
        )
        pq.answered = True
        pq.answer = "Use /api/users"
        overlord._pending_questions["m-123"] = pq

        request = self._mock_request("m-123")
        response = await overlord._answer_handler(request)
        body = json.loads(response.body)
        assert body["answered"] is True
        assert body["answer"] == "Use /api/users"

    @pytest.mark.asyncio
    async def test_answer_returns_false_for_unknown_minion(self):
        """GET /minion/answer/<id> returns answered=false for unknown minion."""
        import json

        from nebulus_swarm.overlord.main import Overlord

        with patch.object(Overlord, "__init__", lambda self, *a, **kw: None):
            overlord = Overlord.__new__(Overlord)
            overlord._pending_questions = {}

        request = self._mock_request("m-unknown")
        response = await overlord._answer_handler(request)
        body = json.loads(response.body)
        assert body["answered"] is False


# ---------------------------------------------------------------------------
# SlackBot: post_question
# ---------------------------------------------------------------------------


class TestSlackBotPostQuestion:
    """Tests for SlackBot.post_question method."""

    @pytest.mark.asyncio
    async def test_post_question_format(self):
        """post_question() sends correctly formatted message."""
        from nebulus_swarm.overlord.slack_bot import SlackBot

        with patch.object(SlackBot, "__init__", lambda self, *a, **kw: None):
            bot = SlackBot.__new__(SlackBot)
            bot.channel_id = "C12345"

            mock_client = AsyncMock()
            mock_client.chat_postMessage = AsyncMock(
                return_value={"ts": "1234567890.123"}
            )

            mock_app = MagicMock()
            mock_app.client = mock_client
            bot.app = mock_app

            thread_ts = await bot.post_question(
                minion_id="m-123",
                issue_number=42,
                question_text="Which endpoint should I optimize?",
                timeout_minutes=10,
            )

        assert thread_ts == "1234567890.123"
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C12345"
        assert "m-123" in call_kwargs["text"]
        assert "#42" in call_kwargs["text"]
        assert "Which endpoint" in call_kwargs["text"]
        assert "10 minutes" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_post_question_returns_none_on_failure(self):
        """post_question() returns None when Slack API fails."""
        from nebulus_swarm.overlord.slack_bot import SlackBot

        with patch.object(SlackBot, "__init__", lambda self, *a, **kw: None):
            bot = SlackBot.__new__(SlackBot)
            bot.channel_id = "C12345"

            mock_client = AsyncMock()
            mock_client.chat_postMessage = AsyncMock(side_effect=Exception("API error"))

            mock_app = MagicMock()
            mock_app.client = mock_client
            bot.app = mock_app

            thread_ts = await bot.post_question(
                minion_id="m-123",
                issue_number=42,
                question_text="Q?",
            )

        assert thread_ts is None
