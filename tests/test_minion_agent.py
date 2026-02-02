"""Tests for Minion agent components."""

import tempfile
from pathlib import Path


from nebulus_swarm.minion.agent import (
    AgentResult,
    AgentStatus,
    LLMConfig,
    LLMResponse,
    ToolExecutor,
    ToolResult,
)
from nebulus_swarm.minion.agent.prompt_builder import (
    IssueContext,
    build_initial_message,
    build_system_prompt,
)
from nebulus_swarm.minion.agent.tools import (
    MINION_TOOLS,
    get_tool_by_name,
    get_tool_names,
)
from nebulus_swarm.minion.skills import (
    Skill,
    SkillLoader,
    SkillTriggers,
    SkillValidator,
    ValidationResult,
    is_skill_change,
)


class TestLLMClient:
    """Tests for LLM client."""

    def test_llm_config_defaults(self):
        """Test LLMConfig default values."""
        config = LLMConfig(
            base_url="http://localhost:5000/v1",
            model="test-model",
        )
        assert config.api_key == "not-needed"
        assert config.timeout == 600
        assert config.temperature == 0.3

    def test_llm_response_has_tool_calls(self):
        """Test LLMResponse.has_tool_calls property."""
        response = LLMResponse(
            content="Hello",
            tool_calls=[],
            finish_reason="stop",
        )
        assert response.has_tool_calls is False

        response_with_tools = LLMResponse(
            content="",
            tool_calls=[{"id": "1", "name": "test", "arguments": "{}"}],
            finish_reason="tool_calls",
        )
        assert response_with_tools.has_tool_calls is True


class TestToolExecutor:
    """Tests for tool executor."""

    def test_read_file(self):
        """Test read_file tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("Hello, World!")

            executor = ToolExecutor(workspace)
            result = executor.execute("read_file", {"path": "test.txt"})

            assert result.success is True
            assert result.output == "Hello, World!"

    def test_read_file_not_found(self):
        """Test read_file with non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            executor = ToolExecutor(workspace)
            result = executor.execute("read_file", {"path": "missing.txt"})

            assert result.success is False
            assert "not found" in result.error.lower()

    def test_write_file(self):
        """Test write_file tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            executor = ToolExecutor(workspace)

            result = executor.execute(
                "write_file", {"path": "new.txt", "content": "Test content"}
            )

            assert result.success is True
            assert (workspace / "new.txt").read_text() == "Test content"

    def test_edit_file(self):
        """Test edit_file tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("Hello, World!")

            executor = ToolExecutor(workspace)
            result = executor.execute(
                "edit_file",
                {"path": "test.txt", "old_text": "World", "new_text": "Python"},
            )

            assert result.success is True
            assert test_file.read_text() == "Hello, Python!"

    def test_list_directory(self):
        """Test list_directory tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "file1.txt").touch()
            (workspace / "file2.py").touch()
            (workspace / "subdir").mkdir()

            executor = ToolExecutor(workspace)
            result = executor.execute("list_directory", {"path": "."})

            assert result.success is True
            assert "file1.txt" in result.output
            assert "file2.py" in result.output
            assert "subdir" in result.output

    def test_glob_files(self):
        """Test glob_files tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "test1.py").touch()
            (workspace / "test2.py").touch()
            (workspace / "readme.md").touch()

            executor = ToolExecutor(workspace)
            result = executor.execute("glob_files", {"pattern": "*.py"})

            assert result.success is True
            assert "test1.py" in result.output
            assert "test2.py" in result.output
            assert "readme.md" not in result.output

    def test_run_command(self):
        """Test run_command tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            executor = ToolExecutor(workspace)

            result = executor.execute("run_command", {"command": "echo hello"})

            assert result.success is True
            assert "hello" in result.output

    def test_run_command_failure(self):
        """Test run_command with failing command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            executor = ToolExecutor(workspace)

            result = executor.execute("run_command", {"command": "exit 1"})

            assert result.success is False
            assert "Exit code: 1" in result.error

    def test_path_escape_prevention(self):
        """Test that paths cannot escape workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            executor = ToolExecutor(workspace)

            result = executor.execute("read_file", {"path": "../../../etc/passwd"})

            assert result.success is False
            assert "escapes workspace" in result.error.lower()

    def test_task_complete(self):
        """Test task_complete tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            executor = ToolExecutor(workspace)

            result = executor.execute("task_complete", {"summary": "All done!"})

            assert result.success is True
            assert "All done!" in result.output

    def test_task_blocked(self):
        """Test task_blocked tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            executor = ToolExecutor(workspace)

            result = executor.execute(
                "task_blocked",
                {"reason": "Missing info", "blocker_type": "missing_info"},
            )

            assert result.success is True


class TestTools:
    """Tests for tool definitions."""

    def test_get_tool_names(self):
        """Test get_tool_names returns all tools."""
        names = get_tool_names()
        assert "read_file" in names
        assert "write_file" in names
        assert "task_complete" in names
        assert len(names) == 11  # Total tools

    def test_get_tool_by_name(self):
        """Test get_tool_by_name."""
        tool = get_tool_by_name("read_file")
        assert tool is not None
        assert tool["function"]["name"] == "read_file"

        missing = get_tool_by_name("nonexistent")
        assert missing is None

    def test_minion_tools_structure(self):
        """Test MINION_TOOLS has correct structure."""
        for tool in MINION_TOOLS:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]


class TestPromptBuilder:
    """Tests for prompt builder."""

    def test_build_system_prompt(self):
        """Test system prompt generation."""
        issue = IssueContext(
            repo="owner/repo",
            number=42,
            title="Fix the bug",
            body="There is a bug in the login",
            labels=["bug", "urgent"],
            author="testuser",
        )

        prompt = build_system_prompt(issue)

        assert "#42" in prompt
        assert "owner/repo" in prompt
        assert "Fix the bug" in prompt
        assert "login" in prompt
        assert "bug, urgent" in prompt

    def test_build_initial_message(self):
        """Test initial message generation."""
        issue = IssueContext(
            repo="owner/repo",
            number=42,
            title="Add feature",
            body="",
            labels=[],
            author="testuser",
        )

        message = build_initial_message(issue)

        assert "#42" in message
        assert "Add feature" in message


class TestMinionAgent:
    """Tests for MinionAgent."""

    def test_agent_result_statuses(self):
        """Test AgentResult status values."""
        completed = AgentResult(
            status=AgentStatus.COMPLETED,
            summary="Done",
            files_changed=["test.py"],
            turns_used=5,
        )
        assert completed.status == AgentStatus.COMPLETED
        assert len(completed.files_changed) == 1

        blocked = AgentResult(
            status=AgentStatus.BLOCKED,
            summary="Need more info",
            blocker_type="missing_info",
            question="What should happen?",
            turns_used=3,
        )
        assert blocked.status == AgentStatus.BLOCKED
        assert blocked.question is not None

    def test_tool_result(self):
        """Test ToolResult dataclass."""
        result = ToolResult(
            tool_call_id="123",
            name="read_file",
            success=True,
            output="file content",
        )
        assert result.success is True
        assert result.error is None

        error_result = ToolResult(
            tool_call_id="456",
            name="read_file",
            success=False,
            output="",
            error="File not found",
        )
        assert error_result.success is False
        assert error_result.error == "File not found"


class TestSkillSchema:
    """Tests for skill schema."""

    def test_skill_creation(self):
        """Test Skill dataclass creation."""
        skill = Skill(
            name="test-skill",
            description="A test skill",
            instructions="Do the thing",
            version="1.0.0",
            tags=["test"],
        )
        assert skill.name == "test-skill"
        assert skill.version == "1.0.0"

    def test_skill_to_dict(self):
        """Test Skill.to_dict()."""
        skill = Skill(
            name="test",
            description="Test",
            instructions="Instructions",
            triggers=SkillTriggers(keywords=["test"]),
        )
        data = skill.to_dict()

        assert data["name"] == "test"
        assert data["triggers"]["keywords"] == ["test"]

    def test_skill_from_dict(self):
        """Test Skill.from_dict()."""
        data = {
            "name": "test",
            "description": "Test skill",
            "instructions": "Do stuff",
            "version": "2.0.0",
            "triggers": {"keywords": ["bug", "fix"]},
        }
        skill = Skill.from_dict(data)

        assert skill.name == "test"
        assert skill.version == "2.0.0"
        assert "bug" in skill.triggers.keywords

    def test_skill_matches_issue(self):
        """Test skill matching."""
        skill = Skill(
            name="bugfix",
            description="Fix bugs",
            instructions="",
            triggers=SkillTriggers(
                keywords=["bug", "error"],
                labels=["bugfix"],
            ),
        )

        # Match by keyword
        assert skill.matches_issue("Fix the bug", "", [], None) is True

        # Match by label
        assert skill.matches_issue("Something", "", ["bugfix"], None) is True

        # No match
        assert skill.matches_issue("Add feature", "", ["feature"], None) is False


class TestSkillValidator:
    """Tests for skill validator."""

    def test_validation_result(self):
        """Test ValidationResult dataclass."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.has_security_issues is False

        result.add_security_flag("Bad pattern found")
        assert result.valid is False
        assert result.has_security_issues is True

    def test_validate_skill_valid(self):
        """Test validating a valid skill."""
        validator = SkillValidator()
        skill = Skill(
            name="test-skill",
            description="Test",
            instructions="Do something safe",
        )
        result = validator.validate_skill(skill)
        assert result.valid is True

    def test_validate_skill_missing_fields(self):
        """Test validating skill with missing fields."""
        validator = SkillValidator()
        skill = Skill(
            name="",
            description="",
            instructions="",
        )
        result = validator.validate_skill(skill)
        assert result.valid is False
        assert len(result.errors) >= 3

    def test_validate_skill_forbidden_pattern(self):
        """Test detecting forbidden patterns."""
        validator = SkillValidator()
        skill = Skill(
            name="bad-skill",
            description="Bad skill",
            instructions="Run: rm -rf /important",
        )
        result = validator.validate_skill(skill)
        assert result.valid is False
        assert result.has_security_issues is True

    def test_is_skill_change(self):
        """Test is_skill_change detection."""
        assert is_skill_change([".nebulus/skills/new.yaml"]) is True
        assert is_skill_change(["src/main.py", ".nebulus/skills/test.yaml"]) is True
        assert is_skill_change(["src/main.py", "tests/test.py"]) is False


class TestSkillLoader:
    """Tests for skill loader."""

    def test_load_skills_no_directory(self):
        """Test loading when skills directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            loader = SkillLoader(workspace)
            loader.load_skills()
            assert loader.skill_count == 0

    def test_load_skills_from_yaml(self):
        """Test loading skills from YAML files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            skills_dir = workspace / ".nebulus" / "skills"
            skills_dir.mkdir(parents=True)

            # Create a skill file
            skill_file = skills_dir / "test-skill.yaml"
            skill_file.write_text(
                """
name: test-skill
description: A test skill
instructions: Do the test thing
version: 1.0.0
triggers:
  keywords:
    - test
"""
            )

            loader = SkillLoader(workspace)
            loader.load_skills()

            assert loader.skill_count == 1
            assert "test-skill" in loader.skill_names

            skill = loader.get_skill("test-skill")
            assert skill is not None
            assert skill.description == "A test skill"

    def test_get_skill_instructions(self):
        """Test getting skill instructions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            skills_dir = workspace / ".nebulus" / "skills"
            skills_dir.mkdir(parents=True)

            skill_file = skills_dir / "helper.yaml"
            skill_file.write_text(
                """
name: helper
description: Helper skill
instructions: |
  Step 1: Do this
  Step 2: Do that
"""
            )

            loader = SkillLoader(workspace)
            instructions = loader.get_skill_instructions("helper")

            assert instructions is not None
            assert "Step 1" in instructions
            assert "Step 2" in instructions

    def test_find_matching_skills(self):
        """Test finding skills that match an issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            skills_dir = workspace / ".nebulus" / "skills"
            skills_dir.mkdir(parents=True)

            # Create skills
            (skills_dir / "bugfix.yaml").write_text(
                """
name: bugfix
description: Fix bugs
instructions: Fix it
triggers:
  keywords: [bug, error]
"""
            )
            (skills_dir / "feature.yaml").write_text(
                """
name: feature
description: Add features
instructions: Add it
triggers:
  keywords: [feature, add]
"""
            )

            loader = SkillLoader(workspace)
            matches = loader.find_matching_skills(
                title="Fix the bug",
                body="There is an error",
                labels=[],
            )

            assert len(matches) == 1
            assert matches[0].name == "bugfix"
