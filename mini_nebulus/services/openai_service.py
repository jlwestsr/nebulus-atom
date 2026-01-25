from openai import OpenAI
from mini_nebulus.config import Config


class OpenAIService:
    def __init__(self):
        self.client = OpenAI(
            base_url=Config.NEBULUS_BASE_URL,
            api_key=Config.NEBULUS_API_KEY,
        )
        self.model = Config.NEBULUS_MODEL

    def create_chat_completion(self, messages, tools=None):
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            tools=tools,
            tool_choice="auto" if tools else None,
        )
