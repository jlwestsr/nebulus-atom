from openai import AsyncOpenAI
from nebulus_atom.config import Config
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class OpenAIService:
    def __init__(self):
        logger.info(
            f"Connecting to Nebulus at {Config.NEBULUS_BASE_URL} with model {Config.NEBULUS_MODEL}"
        )
        try:
            self.client = AsyncOpenAI(
                base_url=Config.NEBULUS_BASE_URL,
                api_key=Config.NEBULUS_API_KEY,
            )
            self.model = Config.NEBULUS_MODEL
        except Exception as e:
            logger.critical(
                f"Failed to initialize OpenAI client: {str(e)}", exc_info=True
            )
            raise e

    async def create_chat_completion(self, messages, tools=None):
        import time

        # logger.debug(
        #     f"Creating chat completion with {len(messages)} messages and {len(tools) if tools else 0} tools"
        # )
        start_time = time.time()
        self.last_telemetry = {
            "model": self.model,
            "ttft": None,
            "total_time": None,
            "usage": {
                "prompt_tokens": "N/A",  # Stream doesn't always provide this
                "completion_tokens": 0,
                "total_tokens": "N/A",
            },
        }

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            # Force native tools off for Prompt-Based Tool Calling
            tools=None,
            tool_choice=None,
            # stream_options={"include_usage": True},  # Request usage stats -- REMOVED for stability
        )

        first_token = True
        async for chunk in stream:
            if first_token:
                self.last_telemetry["ttft"] = time.time() - start_time
                first_token = False

            # OpenAI Streams provide usage in the last chunk
            if hasattr(chunk, "usage") and chunk.usage:
                self.last_telemetry["usage"] = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }

            yield chunk

        self.last_telemetry["total_time"] = time.time() - start_time
        logger.info(f"Completion finished. Stats: {self.last_telemetry}")

    async def create_chat_completion_simple(self, messages) -> str:
        """Non-streaming completion for internal reasoning (Router)."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message.content or ""
