import os
from dotenv import load_dotenv

# Explicitly load .env from current working directory
load_dotenv(os.path.join(os.getcwd(), ".env"))


class Config:
    # User config directory
    USER_CONFIG_DIR = os.path.expanduser("~/.nebulus_atom")
    HISTORY_FILE = os.path.join(USER_CONFIG_DIR, "history")

    NEBULUS_BASE_URL = os.getenv("NEBULUS_BASE_URL")
    NEBULUS_API_KEY = os.getenv("NEBULUS_API_KEY")
    NEBULUS_MODEL = os.getenv("NEBULUS_MODEL", "qwen3:30b-a3b")
    # Timeout in seconds for LLM requests (default 300s = 5 min for large models)
    NEBULUS_TIMEOUT = float(os.getenv("NEBULUS_TIMEOUT", "300"))
    # Enable/disable streaming (some MLX servers don't support SSE streaming)
    NEBULUS_STREAMING = os.getenv("NEBULUS_STREAMING", "true").lower() == "true"
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
