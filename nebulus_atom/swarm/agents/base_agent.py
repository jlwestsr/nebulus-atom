from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from nebulus_atom.services.openai_service import OpenAIService
from nebulus_atom.models.history import HistoryManager
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class BaseAgent(ABC):
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.openai = OpenAIService()
        self.history_manager = HistoryManager(system_prompt)

        # Tools available to this agent (list of dicts)
        self.tools = []

    @abstractmethod
    async def process_turn(
        self, session_id: str, user_input: Optional[str] = None
    ) -> str:
        """
        Execute a single turn of the agent.
        Returns the final response string or status.
        """
        pass

    def add_tool(self, tool_def: Dict[str, Any]):
        self.tools.append(tool_def)

    def get_tools(self):
        return self.tools
