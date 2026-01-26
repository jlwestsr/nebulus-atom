import os
from dotenv import load_dotenv

# Explicitly load .env from current working directory
load_dotenv(os.path.join(os.getcwd(), ".env"))


class Config:
    NEBULUS_BASE_URL = os.getenv("NEBULUS_BASE_URL")
    NEBULUS_API_KEY = os.getenv("NEBULUS_API_KEY")
    NEBULUS_MODEL = os.getenv("NEBULUS_MODEL", "qwen3:30b-a3b")
    EXIT_COMMANDS = ["exit", "quit", "/exit", "/quit"]
    GLOBAL_SKILLS_PATH = os.path.expanduser("~/.mini_nebulus/skills")
