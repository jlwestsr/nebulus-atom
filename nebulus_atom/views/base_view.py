from abc import ABC, abstractmethod
from typing import Dict, Any, ContextManager


class BaseView(ABC):
    @abstractmethod
    async def print_welcome(self):
        """Displays the welcome message."""
        pass

    @abstractmethod
    async def prompt_user(self) -> str:
        """Prompts the user for input."""
        pass

    @abstractmethod
    async def ask_user_input(self, question: str) -> str:
        """Prompts the user for specific input requested by the agent."""
        pass

    @abstractmethod
    async def print_agent_response(self, text: str):
        """Displays the agent s text response."""
        pass

    @abstractmethod
    async def print_telemetry(self, metrics: Dict[str, Any]):
        """Displays performance telemetry."""
        pass

    @abstractmethod
    async def print_tool_output(self, output: str, tool_name: str = ""):
        """Displays the output of a tool execution."""
        pass

    @abstractmethod
    async def print_plan(self, plan_data: Dict[str, Any]):
        """Displays the plan status."""
        pass

    @abstractmethod
    async def print_error(self, message: str):
        """Displays an error message."""
        pass

    @abstractmethod
    async def print_goodbye(self):
        """Displays a goodbye message."""
        pass

    @abstractmethod
    def create_spinner(self, text: str) -> ContextManager:
        """Creates a context manager for a loading spinner."""
        pass
