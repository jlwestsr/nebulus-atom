import os
from dotenv import load_dotenv

# Explicitly load .env from current working directory
load_dotenv(os.path.join(os.getcwd(), ".env"))


class Config:
    NEBULUS_BASE_URL = os.getenv("NEBULUS_BASE_URL")
    NEBULUS_API_KEY = os.getenv("NEBULUS_API_KEY")
    NEBULUS_MODEL = os.getenv("NEBULUS_MODEL", "qwen3:30b-a3b")
    EXIT_COMMANDS = ["exit", "quit", "/exit", "/quit"]
    SANDBOX_MODE = os.getenv("SANDBOX_MODE", "false").lower() == "true"
    GLOBAL_SKILLS_PATH = os.path.expanduser("~/.nebulus_atom/skills")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

    # Logging Configuration
    LOG_DIR = os.path.join(os.getcwd(), "logs")
    LOG_FILE = os.path.join(LOG_DIR, "nebulus_atom.log")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
