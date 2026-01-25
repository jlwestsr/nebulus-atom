import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    NEBULUS_BASE_URL = os.getenv("NEBULUS_BASE_URL")
    NEBULUS_API_KEY = os.getenv("NEBULUS_API_KEY")
    NEBULUS_MODEL = os.getenv("NEBULUS_MODEL", "qwen2.5-coder:latest")
    EXIT_COMMANDS = ["exit", "quit", "/exit", "/quit"]
