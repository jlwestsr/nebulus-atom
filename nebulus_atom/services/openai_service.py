import httpx
from openai import AsyncOpenAI
from nebulus_atom.config import Config
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class OpenAIService:
    def __init__(self):
        logger.info(
            f"Connecting to Nebulus at {Config.NEBULUS_BASE_URL} with model {Config.NEBULUS_MODEL}"
        )
        logger.info(f"Request timeout: {Config.NEBULUS_TIMEOUT}s")
        try:
            # Configure timeout for slow models (MLX, etc.)
            timeout = httpx.Timeout(
                connect=30.0,  # Connection timeout
                read=Config.NEBULUS_TIMEOUT,  # Read timeout for streaming
                write=30.0,  # Write timeout
                pool=30.0,  # Pool timeout
            )
            self.client = AsyncOpenAI(
                base_url=Config.NEBULUS_BASE_URL,
                api_key=Config.NEBULUS_API_KEY,
                timeout=timeout,
            )
            self.model = Config.NEBULUS_MODEL
        except Exception as e:
            logger.critical(
                f"Failed to initialize OpenAI client: {str(e)}", exc_info=True
            )
            raise e

    async def create_chat_completion(self, messages, tools=None):
        import time
        from types import SimpleNamespace

        start_time = time.time()
        self.last_telemetry = {
            "model": self.model,
            "ttft": None,
            "total_time": None,
            "usage": {
                "prompt_tokens": "N/A",
                "completion_tokens": 0,
                "total_tokens": "N/A",
            },
        }

        if Config.NEBULUS_STREAMING:
            # Streaming mode (default for servers that support SSE)
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                tools=None,
                tool_choice=None,
            )

            first_token = True
            async for chunk in stream:
                if first_token:
                    self.last_telemetry["ttft"] = time.time() - start_time
                    first_token = False

                if hasattr(chunk, "usage") and chunk.usage:
                    self.last_telemetry["usage"] = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }

                yield chunk
        else:
            # Non-streaming mode (for MLX and other servers without SSE support)
            logger.info("Using non-streaming mode")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                tools=None,
                tool_choice=None,
            )

            self.last_telemetry["ttft"] = time.time() - start_time

            # Convert response to streaming-like chunks for compatibility
            content = response.choices[0].message.content or ""
            # Yield single chunk with full content (simulates stream end)
            fake_chunk = SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=content,
                            tool_calls=None,
                            role=None,
                        ),
                        finish_reason="stop",
                    )
                ]
            )
            yield fake_chunk

            if response.usage:
                self.last_telemetry["usage"] = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

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
