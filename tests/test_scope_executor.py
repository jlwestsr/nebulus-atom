# tests/test_scope_executor.py
"""Tests for scope enforcement in ToolExecutor."""

import pytest

# Guard against missing optional dependencies
pytest.importorskip("openai")

import os
from unittest.mock import patch

from nebulus_swarm.minion.agent.tool_executor import ToolExecutor
from nebulus_swarm.overlord.scope import ScopeConfig, ScopeMode


class TestScopedToolExecutor:
    def test_unrestricted_allows_write(self, tmp_path):
        executor = ToolExecutor(workspace=tmp_path)
        result = executor.execute("write_file", {"path": "foo.py", "content": "x = 1"})
        assert result.success

    def test_scoped_allows_write_in_scope(self, tmp_path):
        scope = ScopeConfig(mode=ScopeMode.DIRECTORY, allowed_patterns=["src/**"])
        executor = ToolExecutor(workspace=tmp_path, scope=scope)
        (tmp_path / "src").mkdir()
        result = executor.execute(
            "write_file", {"path": "src/app.py", "content": "x = 1"}
        )
        assert result.success

    def test_scoped_blocks_write_outside_scope(self, tmp_path):
        scope = ScopeConfig(mode=ScopeMode.DIRECTORY, allowed_patterns=["src/**"])
        executor = ToolExecutor(workspace=tmp_path, scope=scope)
        result = executor.execute("write_file", {"path": "README.md", "content": "hi"})
        assert not result.success
        assert "outside your assigned scope" in result.error

    def test_scoped_blocks_edit_outside_scope(self, tmp_path):
        scope = ScopeConfig(mode=ScopeMode.DIRECTORY, allowed_patterns=["src/**"])
        executor = ToolExecutor(workspace=tmp_path, scope=scope)
        # Create a file outside scope
        (tmp_path / "README.md").write_text("original")
        result = executor.execute(
            "edit_file",
            {
                "path": "README.md",
                "old_text": "original",
                "new_text": "modified",
            },
        )
        assert not result.success
        assert "outside your assigned scope" in result.error

    def test_scoped_allows_read_outside_scope(self, tmp_path):
        scope = ScopeConfig(mode=ScopeMode.DIRECTORY, allowed_patterns=["src/**"])
        executor = ToolExecutor(workspace=tmp_path, scope=scope)
        (tmp_path / "README.md").write_text("hello")
        result = executor.execute("read_file", {"path": "README.md"})
        assert result.success
        assert "hello" in result.output

    def test_default_scope_is_unrestricted(self, tmp_path):
        executor = ToolExecutor(workspace=tmp_path)
        result = executor.execute("write_file", {"path": "anywhere.py", "content": "x"})
        assert result.success


class TestMinionScopeLoading:
    def test_minion_config_loads_scope_from_env(self):
        from nebulus_swarm.minion.main import MinionConfig

        env = {
            "MINION_ID": "m-1",
            "GITHUB_REPO": "owner/repo",
            "GITHUB_ISSUE": "42",
            "GITHUB_TOKEN": "ghp_test",
            "MINION_SCOPE": '["src/**", "tests/**"]',
        }
        with patch.dict(os.environ, env, clear=True):
            config = MinionConfig.from_env()
        assert config.scope is not None
        assert config.scope.is_write_allowed("src/foo.py")
        assert not config.scope.is_write_allowed("README.md")

    def test_minion_config_no_scope_means_unrestricted(self):
        from nebulus_swarm.minion.main import MinionConfig

        env = {
            "MINION_ID": "m-1",
            "GITHUB_REPO": "owner/repo",
            "GITHUB_ISSUE": "42",
            "GITHUB_TOKEN": "ghp_test",
        }
        with patch.dict(os.environ, env, clear=True):
            config = MinionConfig.from_env()
        assert config.scope.is_write_allowed("any/file.py")
