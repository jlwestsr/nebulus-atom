"""Standalone smoke tests — verify Atom works without any running LLM backend.

These tests confirm:
- Config loads with sensible defaults
- Env var overrides work (ATOM_* and NEBULUS_*)
- YAML config files are respected
- CLI entry point is importable
- No nebulus-core imports anywhere
- Key modules import without error
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from nebulus_atom.settings import (
    load_settings,
    reset_settings,
)


# ---------------------------------------------------------------------------
# Config loads with sensible defaults
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_llm_defaults_are_sensible(self):
        reset_settings()
        settings = load_settings(
            user_config_path=Path("/nonexistent/user.yml"),
            project_config_path=Path("/nonexistent/project.yml"),
        )
        assert settings.llm.base_url.startswith("http")
        assert settings.llm.model  # non-empty
        assert settings.llm.timeout > 0
        reset_settings()

    def test_vector_store_defaults_are_sensible(self):
        settings = load_settings(
            user_config_path=Path("/nonexistent/user.yml"),
            project_config_path=Path("/nonexistent/project.yml"),
        )
        assert settings.vector_store.path  # non-empty
        assert settings.vector_store.collection  # non-empty
        assert settings.vector_store.embedding_model  # non-empty


# ---------------------------------------------------------------------------
# Env var overrides
# ---------------------------------------------------------------------------


class TestEnvVarOverrides:
    def test_atom_env_overrides_defaults(self, tmp_path):
        env = {
            "ATOM_LLM_BASE_URL": "http://test:9999/v1",
            "ATOM_LLM_MODEL": "test-model",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            settings = load_settings(
                user_config_path=tmp_path / "nope.yml",
                project_config_path=tmp_path / "nope.yml",
            )
            reset_settings()
        assert settings.llm.base_url == "http://test:9999/v1"
        assert settings.llm.model == "test-model"

    def test_nebulus_legacy_env_overrides_defaults(self, tmp_path):
        env = {"NEBULUS_BASE_URL": "http://legacy:5000/v1"}
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            # Remove ATOM variant so NEBULUS is used
            os.environ.pop("ATOM_LLM_BASE_URL", None)
            settings = load_settings(
                user_config_path=tmp_path / "nope.yml",
                project_config_path=tmp_path / "nope.yml",
            )
            reset_settings()
        assert settings.llm.base_url == "http://legacy:5000/v1"


# ---------------------------------------------------------------------------
# YAML config
# ---------------------------------------------------------------------------


class TestYamlConfig:
    def test_user_yaml_is_respected(self, tmp_path):
        config = tmp_path / "config.yml"
        config.write_text("llm:\n  model: yaml-model\n")
        with patch.dict(os.environ, {}, clear=False):
            # Remove any env overrides
            os.environ.pop("ATOM_LLM_MODEL", None)
            os.environ.pop("NEBULUS_MODEL", None)
            reset_settings()
            settings = load_settings(
                user_config_path=config,
                project_config_path=tmp_path / "nope.yml",
            )
            reset_settings()
        assert settings.llm.model == "yaml-model"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestCLIEntryPoint:
    def test_typer_app_importable(self):
        from nebulus_atom.main import app

        assert app is not None

    def test_app_has_expected_commands(self):
        from nebulus_atom.main import app

        # Typer uses callback name when cmd.name is None
        registered = {
            cmd.name or (cmd.callback.__name__ if cmd.callback else None)
            for cmd in app.registered_commands
        }
        assert "start" in registered
        assert "docs" in registered
        assert "review_pr" in registered or "review-pr" in registered
        assert "dashboard" in registered


# ---------------------------------------------------------------------------
# No nebulus-core dependency
# ---------------------------------------------------------------------------


class TestNoCoreImports:
    def test_no_nebulus_core_in_atom_package(self):
        """Scan all Python files in nebulus_atom/ for nebulus_core imports."""
        atom_dir = Path(__file__).parent.parent / "nebulus_atom"
        for py_file in atom_dir.rglob("*.py"):
            content = py_file.read_text()
            assert "from nebulus_core" not in content, f"{py_file} imports nebulus_core"
            assert "import nebulus_core" not in content, (
                f"{py_file} imports nebulus_core"
            )

    def test_no_nebulus_core_in_swarm_package(self):
        """Scan all Python files in nebulus_swarm/ for nebulus_core imports."""
        swarm_dir = Path(__file__).parent.parent / "nebulus_swarm"
        if not swarm_dir.exists():
            pytest.skip("nebulus_swarm not present")
        for py_file in swarm_dir.rglob("*.py"):
            content = py_file.read_text()
            assert "from nebulus_core" not in content, f"{py_file} imports nebulus_core"
            assert "import nebulus_core" not in content, (
                f"{py_file} imports nebulus_core"
            )


# ---------------------------------------------------------------------------
# Key modules import without error
# ---------------------------------------------------------------------------


class TestKeyModuleImports:
    def test_settings_module(self):
        import nebulus_atom.settings

        assert hasattr(nebulus_atom.settings, "load_settings")

    def test_config_module(self):
        from nebulus_atom.config import Config

        assert Config.NEBULUS_BASE_URL is not None

    def test_review_pr_module(self):
        from nebulus_atom.commands.review_pr import (
            detect_repo_from_git,
            format_review_output,
            load_review_config,
        )

        assert callable(detect_repo_from_git)
        assert callable(format_review_output)
        assert callable(load_review_config)
