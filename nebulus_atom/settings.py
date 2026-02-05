"""Unified configuration for Nebulus Atom.

Loads settings from (in order of precedence, highest first):
1. Environment variables (ATOM_* preferred, NEBULUS_* legacy)
2. Project-local config (.atom.yml in cwd)
3. User config (~/.atom/config.yml)
4. Built-in defaults
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LLMSettings:
    """LLM backend configuration."""

    base_url: str = "http://localhost:5000/v1"
    model: str = "Meta-Llama-3.1-8B-Instruct-exl2-8_0"
    api_key: str = "not-needed"
    timeout: float = 300.0
    streaming: bool = True


@dataclass
class VectorStoreSettings:
    """Vector store configuration for RAG."""

    path: str = ".nebulus_atom/db"
    collection: str = "codebase"
    embedding_model: str = "all-MiniLM-L6-v2"


@dataclass
class AtomSettings:
    """Root configuration container."""

    llm: LLMSettings = field(default_factory=LLMSettings)
    vector_store: VectorStoreSettings = field(default_factory=VectorStoreSettings)


def load_yaml_config(path: Path) -> dict:
    """Load a YAML config file, returning empty dict if not found.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed dict, or empty dict on any failure.
    """
    if not path.exists():
        return {}
    try:
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _apply_dict_to_llm(settings: LLMSettings, data: dict) -> None:
    """Apply dict values to LLMSettings."""
    if "base_url" in data:
        settings.base_url = str(data["base_url"])
    if "model" in data:
        settings.model = str(data["model"])
    if "api_key" in data:
        settings.api_key = str(data["api_key"])
    if "timeout" in data:
        settings.timeout = float(data["timeout"])
    if "streaming" in data:
        val = data["streaming"]
        settings.streaming = (
            val if isinstance(val, bool) else str(val).lower() == "true"
        )


def _apply_dict_to_vector_store(settings: VectorStoreSettings, data: dict) -> None:
    """Apply dict values to VectorStoreSettings."""
    if "path" in data:
        settings.path = str(data["path"])
    if "collection" in data:
        settings.collection = str(data["collection"])
    if "embedding_model" in data:
        settings.embedding_model = str(data["embedding_model"])


def _apply_env_overrides(settings: AtomSettings) -> None:
    """Apply environment variable overrides.

    ATOM_* env vars take precedence over NEBULUS_* legacy vars.
    """
    # LLM settings
    base_url = os.environ.get("ATOM_LLM_BASE_URL") or os.environ.get("NEBULUS_BASE_URL")
    if base_url:
        settings.llm.base_url = base_url

    model = os.environ.get("ATOM_LLM_MODEL") or os.environ.get("NEBULUS_MODEL")
    if model:
        settings.llm.model = model

    api_key = os.environ.get("ATOM_LLM_API_KEY") or os.environ.get("NEBULUS_API_KEY")
    if api_key:
        settings.llm.api_key = api_key

    timeout = os.environ.get("ATOM_LLM_TIMEOUT") or os.environ.get("NEBULUS_TIMEOUT")
    if timeout:
        settings.llm.timeout = float(timeout)

    streaming = os.environ.get("ATOM_LLM_STREAMING") or os.environ.get(
        "NEBULUS_STREAMING"
    )
    if streaming:
        settings.llm.streaming = streaming.lower() == "true"

    # Vector store settings
    vs_path = os.environ.get("ATOM_VECTOR_STORE_PATH")
    if vs_path:
        settings.vector_store.path = vs_path

    vs_collection = os.environ.get("ATOM_VECTOR_STORE_COLLECTION")
    if vs_collection:
        settings.vector_store.collection = vs_collection

    vs_embedding = os.environ.get("ATOM_VECTOR_STORE_EMBEDDING_MODEL")
    if vs_embedding:
        settings.vector_store.embedding_model = vs_embedding


def load_settings(
    user_config_path: Optional[Path] = None,
    project_config_path: Optional[Path] = None,
) -> AtomSettings:
    """Load settings from config files and env vars.

    Precedence (highest first):
    1. Environment variables (ATOM_* preferred, NEBULUS_* legacy)
    2. Project-local config (.atom.yml in cwd)
    3. User config (~/.atom/config.yml)
    4. Built-in defaults

    Args:
        user_config_path: Override path for user config (testing).
        project_config_path: Override path for project config (testing).

    Returns:
        Fully resolved AtomSettings.
    """
    settings = AtomSettings()

    # User config (lowest precedence of overrides)
    user_path = user_config_path or (Path.home() / ".atom" / "config.yml")
    user_data = load_yaml_config(user_path)
    if "llm" in user_data:
        _apply_dict_to_llm(settings.llm, user_data["llm"])
    if "vector_store" in user_data:
        _apply_dict_to_vector_store(settings.vector_store, user_data["vector_store"])

    # Project config (overrides user config)
    project_path = project_config_path or (Path.cwd() / ".atom.yml")
    project_data = load_yaml_config(project_path)
    if "llm" in project_data:
        _apply_dict_to_llm(settings.llm, project_data["llm"])
    if "vector_store" in project_data:
        _apply_dict_to_vector_store(settings.vector_store, project_data["vector_store"])

    # Env vars (highest precedence)
    _apply_env_overrides(settings)

    return settings


# Module-level cached instance
_settings: Optional[AtomSettings] = None


def get_settings() -> AtomSettings:
    """Get cached settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Reset cached settings (for testing)."""
    global _settings
    _settings = None
