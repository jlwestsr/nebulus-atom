"""Tests for CognitionService."""

import pytest

from nebulus_atom.services.cognition_service import (
    CognitionService,
    CognitionServiceManager,
)
from nebulus_atom.models.cognition import TaskComplexity


class TestCognitionService:
    """Test cases for CognitionService."""

    @pytest.fixture
    def service(self):
        """Create a CognitionService instance."""
        return CognitionService()

    # === Task Complexity Classification ===

    def test_simple_task_classification(self, service):
        """Simple tasks should be classified as SIMPLE."""
        simple_tasks = [
            "list files",
            "ls -la",
            "show me the readme",
            "what is in this directory",
            "read config.py",
            "cat main.py",
        ]

        for task in simple_tasks:
            result = service.analyze_task(task)
            assert result.task_complexity == TaskComplexity.SIMPLE, (
                f"'{task}' should be SIMPLE"
            )

    def test_moderate_task_classification(self, service):
        """Moderate tasks should be classified as MODERATE."""
        moderate_tasks = [
            "add a new function to utils.py",
            "fix the bug in the login handler",
            "create a test for the user model",
            "update the config file with new settings",
        ]

        for task in moderate_tasks:
            result = service.analyze_task(task)
            assert result.task_complexity in [
                TaskComplexity.MODERATE,
                TaskComplexity.COMPLEX,
            ], f"'{task}' should be at least MODERATE"

    def test_complex_task_classification(self, service):
        """Complex tasks should be classified as COMPLEX."""
        complex_tasks = [
            "refactor the authentication system to use JWT",
            "implement a new caching layer for the database",
            "build a REST API for user management",
            "add security headers and CSRF protection",
            "deploy the application to kubernetes",
        ]

        for task in complex_tasks:
            result = service.analyze_task(task)
            assert result.task_complexity == TaskComplexity.COMPLEX, (
                f"'{task}' should be COMPLEX"
            )

    # === Ambiguity Detection ===

    def test_ambiguous_task_detection(self, service):
        """Ambiguous tasks should have higher ambiguity scores."""
        ambiguous = "maybe add something like a login feature somehow"
        clear = "add a login_user function to auth.py that takes email and password"

        ambiguous_result = service.analyze_task(ambiguous)
        clear_result = service.analyze_task(clear)

        # Ambiguous should have lower confidence
        assert ambiguous_result.confidence < clear_result.confidence

    def test_clarification_questions_for_complex_tasks(self, service):
        """Complex tasks should generate clarification questions."""
        result = service.analyze_task("implement user authentication")

        assert result.task_complexity == TaskComplexity.COMPLEX
        # Complex tasks with ambiguity should suggest clarification
        assert len(result.reasoning_chain) > 2

    # === Reasoning Chain ===

    def test_reasoning_chain_generated(self, service):
        """All tasks should generate a reasoning chain."""
        result = service.analyze_task("list files in current directory")

        assert len(result.reasoning_chain) > 0
        assert result.reasoning_chain[0].step_number == 1

    def test_complex_task_has_longer_reasoning(self, service):
        """Complex tasks should have more reasoning steps."""
        simple_result = service.analyze_task("ls")
        complex_result = service.analyze_task("refactor the database layer")

        assert len(complex_result.reasoning_chain) > len(simple_result.reasoning_chain)

    # === Confidence Scoring ===

    def test_simple_task_high_confidence(self, service):
        """Simple tasks should have high confidence."""
        result = service.analyze_task("list files")
        assert result.confidence > 0.8

    def test_complex_ambiguous_task_lower_confidence(self, service):
        """Complex ambiguous tasks should have lower confidence."""
        result = service.analyze_task("maybe refactor something in the codebase")
        assert result.confidence < 0.7

    # === Risk Identification ===

    def test_destructive_operation_risk(self, service):
        """Destructive operations should be flagged as risky."""
        result = service.analyze_task("delete all log files")
        assert any("destructive" in risk.lower() for risk in result.potential_risks)

    def test_security_operation_risk(self, service):
        """Security-related tasks should flag security risks."""
        result = service.analyze_task("update the password hashing")
        assert any("security" in risk.lower() for risk in result.potential_risks)

    def test_database_operation_risk(self, service):
        """Database operations should flag database risks."""
        result = service.analyze_task("run database migration")
        assert any("database" in risk.lower() for risk in result.potential_risks)

    # === Step Estimation ===

    def test_simple_task_few_steps(self, service):
        """Simple tasks should estimate few steps."""
        result = service.analyze_task("read file.txt")
        assert result.estimated_steps <= 2

    def test_multi_step_indicators_increase_estimate(self, service):
        """Tasks with multi-step indicators should estimate more steps."""
        single = service.analyze_task("create a function")
        multi = service.analyze_task(
            "first create a function, then add tests, and finally update docs"
        )

        assert multi.estimated_steps > single.estimated_steps

    # === Self-Critique ===

    def test_critique_success_output(self, service):
        """Successful outputs should pass critique."""
        result = service.critique_output(
            original_task="list files",
            tool_name="run_shell_command",
            tool_output="file1.py\nfile2.py\nREADME.md",
        )

        assert result.is_valid
        assert result.confidence > 0.8
        assert not result.should_retry

    def test_critique_error_output(self, service):
        """Error outputs should fail critique."""
        result = service.critique_output(
            original_task="read file",
            tool_name="read_file",
            tool_output="Error: File not found",
        )

        assert not result.is_valid
        assert len(result.issues_found) > 0
        assert result.should_retry

    def test_critique_empty_output(self, service):
        """Empty outputs should be flagged."""
        result = service.critique_output(
            original_task="do something",
            tool_name="some_tool",
            tool_output="",
        )

        assert not result.is_valid

    # === Thought Recording ===

    def test_record_thought(self, service):
        """Thoughts should be recorded and retrievable."""
        service.record_thought(
            session_id="test",
            thought_type="analysis",
            content="Testing thought recording",
            confidence=0.9,
        )

        history = service.get_thought_history("test")
        assert len(history) == 1
        assert history[0].content == "Testing thought recording"

    def test_thought_history_filtering(self, service):
        """Thought history should be filterable by session."""
        service.record_thought("session1", "analysis", "Thought 1")
        service.record_thought("session2", "reasoning", "Thought 2")

        session1_history = service.get_thought_history("session1")
        assert len(session1_history) == 1
        assert session1_history[0].session_id == "session1"

    def test_clear_thought_history(self, service):
        """Thought history should be clearable."""
        service.record_thought("test", "analysis", "Thought 1")
        service.record_thought("test", "reasoning", "Thought 2")

        service.clear_thought_history("test")

        assert len(service.get_thought_history("test")) == 0

    # === Decision Properties ===

    def test_should_proceed_high_confidence(self, service):
        """High confidence tasks should proceed."""
        result = service.analyze_task("list files")
        assert result.should_proceed

    def test_needs_planning_complex_tasks(self, service):
        """Complex tasks should need planning."""
        result = service.analyze_task("refactor the entire authentication system")
        assert result.needs_planning


class TestCognitionServiceManager:
    """Test cases for CognitionServiceManager."""

    def test_get_service_creates_new(self):
        """Manager should create new services per session."""
        manager = CognitionServiceManager()

        service1 = manager.get_service("session1")
        service2 = manager.get_service("session2")

        assert service1 is not service2

    def test_get_service_returns_same_instance(self):
        """Manager should return same service for same session."""
        manager = CognitionServiceManager()

        service1 = manager.get_service("session1")
        service2 = manager.get_service("session1")

        assert service1 is service2

    def test_default_session(self):
        """Manager should handle default session."""
        manager = CognitionServiceManager()

        service = manager.get_service()
        assert service is not None
