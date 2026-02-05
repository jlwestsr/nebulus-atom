"""Tests for the unified settings module."""

import os
from unittest.mock import patch


from nebulus_atom.settings import (
    LLMSettings,
    VectorStoreSettings,
    load_settings,
    load_yaml_config,
    get_settings,
    reset_settings,
)


# ---------------------------------------------------------------------------
# LLMSettings defaults
# ---------------------------------------------------------------------------


class TestLLMSettingsDefaults:
    def test_default_base_url(self):
        s = LLMSettings()
        assert s.base_url == "http://localhost:5000/v1"

    def test_default_model(self):
        s = LLMSettings()
        assert s.model == "Meta-Llama-3.1-8B-Instruct-exl2-8_0"

    def test_default_api_key(self):
        s = LLMSettings()
        assert s.api_key == "not-needed"

    def test_default_timeout(self):
        s = LLMSettings()
        assert s.timeout == 300.0

    def test_default_streaming(self):
        s = LLMSettings()
        assert s.streaming is True


# ---------------------------------------------------------------------------
# VectorStoreSettings defaults
# ---------------------------------------------------------------------------


class TestVectorStoreSettingsDefaults:
    def test_default_path(self):
        s = VectorStoreSettings()
        assert s.path == ".nebulus_atom/db"

    def test_default_collection(self):
        s = VectorStoreSettings()
        assert s.collection == "codebase"

    def test_default_embedding_model(self):
        s = VectorStoreSettings()
        assert s.embedding_model == "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# load_yaml_config
# ---------------------------------------------------------------------------


class TestLoadYamlConfig:
    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        result = load_yaml_config(tmp_path / "nonexistent.yml")
        assert result == {}

    def test_loads_valid_yaml(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text("llm:\n  base_url: http://example.com/v1\n")
        result = load_yaml_config(config_file)
        assert result["llm"]["base_url"] == "http://example.com/v1"

    def test_returns_empty_dict_for_non_dict_yaml(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text("just a string\n")
        result = load_yaml_config(config_file)
        assert result == {}

    def test_returns_empty_dict_for_empty_file(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text("")
        result = load_yaml_config(config_file)
        assert result == {}

    def test_loads_full_config(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            "llm:\n"
            "  base_url: http://myserver:8080/v1\n"
            "  model: my-model\n"
            "  api_key: sk-test\n"
            "  timeout: 60\n"
            "  streaming: false\n"
            "vector_store:\n"
            "  path: /data/vectors\n"
            "  collection: docs\n"
            "  embedding_model: custom-embed\n"
        )
        result = load_yaml_config(config_file)
        assert result["llm"]["base_url"] == "http://myserver:8080/v1"
        assert result["llm"]["model"] == "my-model"
        assert result["llm"]["api_key"] == "sk-test"
        assert result["llm"]["timeout"] == 60
        assert result["llm"]["streaming"] is False
        assert result["vector_store"]["path"] == "/data/vectors"
        assert result["vector_store"]["collection"] == "docs"
        assert result["vector_store"]["embedding_model"] == "custom-embed"


# ---------------------------------------------------------------------------
# load_settings — precedence
# ---------------------------------------------------------------------------


class TestLoadSettings:
    def _clean_env(self):
        """Return env vars to remove for clean testing."""
        return {
            k: ""
            for k in [
                "ATOM_LLM_BASE_URL",
                "ATOM_LLM_MODEL",
                "ATOM_LLM_API_KEY",
                "ATOM_LLM_TIMEOUT",
                "ATOM_LLM_STREAMING",
                "ATOM_VECTOR_STORE_PATH",
                "ATOM_VECTOR_STORE_COLLECTION",
                "ATOM_VECTOR_STORE_EMBEDDING_MODEL",
                "NEBULUS_BASE_URL",
                "NEBULUS_MODEL",
                "NEBULUS_API_KEY",
                "NEBULUS_TIMEOUT",
                "NEBULUS_STREAMING",
            ]
        }

    def test_defaults_with_no_config(self, tmp_path):
        with patch.dict(os.environ, self._clean_env(), clear=False):
            # Remove the env vars we just set to empty
            for key in self._clean_env():
                os.environ.pop(key, None)
            settings = load_settings(
                user_config_path=tmp_path / "nope.yml",
                project_config_path=tmp_path / "nope2.yml",
            )
        assert settings.llm.base_url == "http://localhost:5000/v1"
        assert settings.llm.model == "Meta-Llama-3.1-8B-Instruct-exl2-8_0"
        assert settings.llm.api_key == "not-needed"
        assert settings.llm.timeout == 300.0
        assert settings.llm.streaming is True

    def test_user_config_overrides_defaults(self, tmp_path):
        user_cfg = tmp_path / "user.yml"
        user_cfg.write_text("llm:\n  model: my-custom-model\n")
        with patch.dict(os.environ, self._clean_env(), clear=False):
            for key in self._clean_env():
                os.environ.pop(key, None)
            settings = load_settings(
                user_config_path=user_cfg,
                project_config_path=tmp_path / "nope.yml",
            )
        assert settings.llm.model == "my-custom-model"
        assert settings.llm.base_url == "http://localhost:5000/v1"

    def test_project_config_overrides_user_config(self, tmp_path):
        user_cfg = tmp_path / "user.yml"
        user_cfg.write_text(
            "llm:\n  model: user-model\n  base_url: http://user:5000/v1\n"
        )
        project_cfg = tmp_path / "project.yml"
        project_cfg.write_text("llm:\n  model: project-model\n")
        with patch.dict(os.environ, self._clean_env(), clear=False):
            for key in self._clean_env():
                os.environ.pop(key, None)
            settings = load_settings(
                user_config_path=user_cfg,
                project_config_path=project_cfg,
            )
        assert settings.llm.model == "project-model"
        assert settings.llm.base_url == "http://user:5000/v1"

    def test_env_vars_override_all(self, tmp_path):
        user_cfg = tmp_path / "user.yml"
        user_cfg.write_text("llm:\n  model: yaml-model\n")
        env = {**self._clean_env(), "ATOM_LLM_MODEL": "env-model"}
        with patch.dict(os.environ, env, clear=False):
            settings = load_settings(
                user_config_path=user_cfg,
                project_config_path=tmp_path / "nope.yml",
            )
        assert settings.llm.model == "env-model"

    def test_atom_env_preferred_over_nebulus(self, tmp_path):
        env = {
            **self._clean_env(),
            "ATOM_LLM_BASE_URL": "http://atom:5000/v1",
            "NEBULUS_BASE_URL": "http://nebulus:5000/v1",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = load_settings(
                user_config_path=tmp_path / "nope.yml",
                project_config_path=tmp_path / "nope.yml",
            )
        assert settings.llm.base_url == "http://atom:5000/v1"

    def test_nebulus_env_works_as_fallback(self, tmp_path):
        env = {**self._clean_env(), "NEBULUS_BASE_URL": "http://legacy:5000/v1"}
        with patch.dict(os.environ, env, clear=False):
            # Remove ATOM_LLM_BASE_URL so NEBULUS is used
            os.environ.pop("ATOM_LLM_BASE_URL", None)
            settings = load_settings(
                user_config_path=tmp_path / "nope.yml",
                project_config_path=tmp_path / "nope.yml",
            )
        assert settings.llm.base_url == "http://legacy:5000/v1"

    def test_all_atom_env_vars(self, tmp_path):
        env = {
            **self._clean_env(),
            "ATOM_LLM_BASE_URL": "http://env:8080/v1",
            "ATOM_LLM_MODEL": "env-model",
            "ATOM_LLM_API_KEY": "sk-env",
            "ATOM_LLM_TIMEOUT": "60",
            "ATOM_LLM_STREAMING": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = load_settings(
                user_config_path=tmp_path / "nope.yml",
                project_config_path=tmp_path / "nope.yml",
            )
        assert settings.llm.base_url == "http://env:8080/v1"
        assert settings.llm.model == "env-model"
        assert settings.llm.api_key == "sk-env"
        assert settings.llm.timeout == 60.0
        assert settings.llm.streaming is False

    def test_vector_store_from_yaml(self, tmp_path):
        user_cfg = tmp_path / "config.yml"
        user_cfg.write_text(
            "vector_store:\n  path: /custom/db\n  embedding_model: my-embed\n"
        )
        with patch.dict(os.environ, self._clean_env(), clear=False):
            for key in self._clean_env():
                os.environ.pop(key, None)
            settings = load_settings(
                user_config_path=user_cfg,
                project_config_path=tmp_path / "nope.yml",
            )
        assert settings.vector_store.path == "/custom/db"
        assert settings.vector_store.embedding_model == "my-embed"
        assert settings.vector_store.collection == "codebase"

    def test_vector_store_from_env(self, tmp_path):
        env = {
            **self._clean_env(),
            "ATOM_VECTOR_STORE_PATH": "/env/db",
            "ATOM_VECTOR_STORE_COLLECTION": "my-collection",
            "ATOM_VECTOR_STORE_EMBEDDING_MODEL": "env-embed",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = load_settings(
                user_config_path=tmp_path / "nope.yml",
                project_config_path=tmp_path / "nope.yml",
            )
        assert settings.vector_store.path == "/env/db"
        assert settings.vector_store.collection == "my-collection"
        assert settings.vector_store.embedding_model == "env-embed"

    def test_partial_yaml_preserves_other_defaults(self, tmp_path):
        user_cfg = tmp_path / "config.yml"
        user_cfg.write_text("llm:\n  model: only-model\n")
        with patch.dict(os.environ, self._clean_env(), clear=False):
            for key in self._clean_env():
                os.environ.pop(key, None)
            settings = load_settings(
                user_config_path=user_cfg,
                project_config_path=tmp_path / "nope.yml",
            )
        assert settings.llm.model == "only-model"
        assert settings.llm.base_url == "http://localhost:5000/v1"
        assert settings.llm.timeout == 300.0
        assert settings.vector_store.path == ".nebulus_atom/db"


# ---------------------------------------------------------------------------
# get_settings / reset_settings cache
# ---------------------------------------------------------------------------


class TestGetSettings:
    def test_returns_cached_instance(self):
        reset_settings()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        reset_settings()

    def test_reset_clears_cache(self):
        reset_settings()
        s1 = get_settings()
        reset_settings()
        s2 = get_settings()
        assert s1 is not s2
        reset_settings()
