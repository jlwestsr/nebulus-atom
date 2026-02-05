import os
from dotenv import load_dotenv

# Explicitly load .env from current working directory
load_dotenv(os.path.join(os.getcwd(), ".env"))

# Load unified settings (after dotenv so env vars are available)
from nebulus_atom.settings import get_settings as _get_settings  # noqa: E402

_s = _get_settings()


class Config:
    # User config directory
    USER_CONFIG_DIR = os.path.expanduser("~/.nebulus_atom")
    HISTORY_FILE = os.path.join(USER_CONFIG_DIR, "history")

    # LLM settings — sourced from ~/.atom/config.yml, .atom.yml, or env vars
    NEBULUS_BASE_URL = _s.llm.base_url
    NEBULUS_API_KEY = _s.llm.api_key
    NEBULUS_MODEL = _s.llm.model
    NEBULUS_TIMEOUT = _s.llm.timeout
    NEBULUS_STREAMING = _s.llm.streaming

    EXIT_COMMANDS = ["exit", "quit", "/exit", "/quit"]
    SANDBOX_MODE = os.getenv("SANDBOX_MODE", "false").lower() == "true"
    GLOBAL_SKILLS_PATH = os.path.join(USER_CONFIG_DIR, "skills")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

    @classmethod
    def ensure_config_dir(cls):
        """Ensure the user config directory and subdirectories exist."""
        os.makedirs(cls.USER_CONFIG_DIR, exist_ok=True)
        os.makedirs(cls.GLOBAL_SKILLS_PATH, exist_ok=True)

    # Logging Configuration
    LOG_DIR = os.path.join(os.getcwd(), "logs")
    LOG_FILE = os.path.join(LOG_DIR, "nebulus_atom.log")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
