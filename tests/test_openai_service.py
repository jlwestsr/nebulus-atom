"""Tests for OpenAIService - the core LLM client."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class TestOpenAIServiceInit:
    """Tests for OpenAIService initialization."""

    @patch("nebulus_atom.services.openai_service.Config")
    @patch("nebulus_atom.services.openai_service.AsyncOpenAI")
    def test_init_creates_client_with_config(self, mock_openai_cls, mock_config):
        mock_config.NEBULUS_BASE_URL = "http://localhost:5000/v1"
        mock_config.NEBULUS_API_KEY = "test-key"
        mock_config.NEBULUS_MODEL = "test-model"
        mock_config.NEBULUS_TIMEOUT = 300.0

        from nebulus_atom.services.openai_service import OpenAIService

        svc = OpenAIService()
        assert svc.model == "test-model"
        mock_openai_cls.assert_called_once()
        call_kwargs = mock_openai_cls.call_args
        assert call_kwargs.kwargs["base_url"] == "http://localhost:5000/v1"
        assert call_kwargs.kwargs["api_key"] == "test-key"

    @patch("nebulus_atom.services.openai_service.Config")
    @patch("nebulus_atom.services.openai_service.AsyncOpenAI")
    def test_init_configures_timeout(self, mock_openai_cls, mock_config):
        mock_config.NEBULUS_BASE_URL = "http://localhost:5000/v1"
        mock_config.NEBULUS_API_KEY = "test-key"
        mock_config.NEBULUS_MODEL = "test-model"
        mock_config.NEBULUS_TIMEOUT = 600.0

        from nebulus_atom.services.openai_service import OpenAIService

        OpenAIService()
        call_kwargs = mock_openai_cls.call_args
        timeout = call_kwargs.kwargs["timeout"]
        assert timeout.read == 600.0
        assert timeout.connect == 30.0

    @patch("nebulus_atom.services.openai_service.Config")
    @patch(
        "nebulus_atom.services.openai_service.AsyncOpenAI",
        side_effect=Exception("connection failed"),
    )
    def test_init_raises_on_client_failure(self, mock_openai_cls, mock_config):
        mock_config.NEBULUS_BASE_URL = "http://localhost:5000/v1"
        mock_config.NEBULUS_API_KEY = "test-key"
        mock_config.NEBULUS_MODEL = "test-model"
        mock_config.NEBULUS_TIMEOUT = 300.0

        from nebulus_atom.services.openai_service import OpenAIService

        with pytest.raises(Exception, match="connection failed"):
            OpenAIService()


class TestStreamingCompletion:
    """Tests for streaming mode chat completion."""

    @pytest.fixture
    def service(self):
        with (
            patch("nebulus_atom.services.openai_service.Config") as mock_config,
            patch("nebulus_atom.services.openai_service.AsyncOpenAI") as mock_cls,
        ):
            mock_config.NEBULUS_BASE_URL = "http://localhost:5000/v1"
            mock_config.NEBULUS_API_KEY = "test-key"
            mock_config.NEBULUS_MODEL = "test-model"
            mock_config.NEBULUS_TIMEOUT = 300.0
            mock_config.NEBULUS_STREAMING = True

            svc = self._create_service(mock_cls, mock_config)
            yield svc

    def _create_service(self, mock_cls, mock_config):
        from nebulus_atom.services.openai_service import OpenAIService

        return OpenAIService()

    @pytest.mark.asyncio
    async def test_streaming_yields_chunks(self, service):
        chunks = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="Hello", tool_calls=None),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=" world", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            ),
        ]

        async def mock_stream():
            for c in chunks:
                yield c

        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = True
            messages = [{"role": "user", "content": "hi"}]

            received = []
            async for chunk in service.create_chat_completion(messages):
                received.append(chunk)

            assert len(received) == 2
            assert received[0].choices[0].delta.content == "Hello"
            assert received[1].choices[0].delta.content == " world"

    @pytest.mark.asyncio
    async def test_streaming_records_ttft(self, service):
        chunks = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="Hi", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            ),
        ]

        async def mock_stream():
            for c in chunks:
                yield c

        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = True
            messages = [{"role": "user", "content": "hi"}]

            async for _ in service.create_chat_completion(messages):
                pass

            assert service.last_telemetry["ttft"] is not None
            assert service.last_telemetry["ttft"] >= 0

    @pytest.mark.asyncio
    async def test_streaming_captures_usage(self, service):
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        chunks = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="Hi", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=usage,
            ),
        ]

        async def mock_stream():
            for c in chunks:
                yield c

        service.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = True
            messages = [{"role": "user", "content": "hi"}]

            async for _ in service.create_chat_completion(messages):
                pass

            assert service.last_telemetry["usage"]["prompt_tokens"] == 10
            assert service.last_telemetry["usage"]["completion_tokens"] == 5
            assert service.last_telemetry["usage"]["total_tokens"] == 15


class TestNonStreamingCompletion:
    """Tests for non-streaming mode chat completion."""

    @pytest.fixture
    def service(self):
        with (
            patch("nebulus_atom.services.openai_service.Config") as mock_config,
            patch("nebulus_atom.services.openai_service.AsyncOpenAI"),
        ):
            mock_config.NEBULUS_BASE_URL = "http://localhost:5000/v1"
            mock_config.NEBULUS_API_KEY = "test-key"
            mock_config.NEBULUS_MODEL = "test-model"
            mock_config.NEBULUS_TIMEOUT = 300.0
            mock_config.NEBULUS_STREAMING = False

            from nebulus_atom.services.openai_service import OpenAIService

            svc = OpenAIService()
            yield svc

    @pytest.mark.asyncio
    async def test_non_streaming_yields_fake_chunk(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Hello world"),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=8, completion_tokens=2, total_tokens=10
            ),
        )

        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = False
            messages = [{"role": "user", "content": "hi"}]

            received = []
            async for chunk in service.create_chat_completion(messages):
                received.append(chunk)

            assert len(received) == 1
            assert received[0].choices[0].delta.content == "Hello world"
            assert received[0].choices[0].finish_reason == "stop"
            assert received[0].choices[0].delta.tool_calls is None
            assert received[0].choices[0].delta.role is None

    @pytest.mark.asyncio
    async def test_non_streaming_handles_none_content(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=None),
                )
            ],
            usage=None,
        )

        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = False
            messages = [{"role": "user", "content": "hi"}]

            received = []
            async for chunk in service.create_chat_completion(messages):
                received.append(chunk)

            assert received[0].choices[0].delta.content == ""

    @pytest.mark.asyncio
    async def test_non_streaming_captures_usage(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok"),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=20, completion_tokens=1, total_tokens=21
            ),
        )

        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = False
            messages = [{"role": "user", "content": "hi"}]

            async for _ in service.create_chat_completion(messages):
                pass

            assert service.last_telemetry["usage"]["prompt_tokens"] == 20
            assert service.last_telemetry["usage"]["completion_tokens"] == 1

    @pytest.mark.asyncio
    async def test_non_streaming_no_usage(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok"),
                )
            ],
            usage=None,
        )

        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = False
            messages = [{"role": "user", "content": "hi"}]

            async for _ in service.create_chat_completion(messages):
                pass

            assert service.last_telemetry["usage"]["prompt_tokens"] == "N/A"

    @pytest.mark.asyncio
    async def test_non_streaming_records_total_time(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok"),
                )
            ],
            usage=None,
        )

        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = False
            messages = [{"role": "user", "content": "hi"}]

            async for _ in service.create_chat_completion(messages):
                pass

            assert service.last_telemetry["total_time"] is not None
            assert service.last_telemetry["total_time"] >= 0


class TestSimpleCompletion:
    """Tests for create_chat_completion_simple."""

    @pytest.fixture
    def service(self):
        with (
            patch("nebulus_atom.services.openai_service.Config") as mock_config,
            patch("nebulus_atom.services.openai_service.AsyncOpenAI"),
        ):
            mock_config.NEBULUS_BASE_URL = "http://localhost:5000/v1"
            mock_config.NEBULUS_API_KEY = "test-key"
            mock_config.NEBULUS_MODEL = "test-model"
            mock_config.NEBULUS_TIMEOUT = 300.0

            from nebulus_atom.services.openai_service import OpenAIService

            svc = OpenAIService()
            yield svc

    @pytest.mark.asyncio
    async def test_simple_returns_content(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="The answer is 42"),
                )
            ],
        )
        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await service.create_chat_completion_simple(
            [{"role": "user", "content": "what is the answer?"}]
        )
        assert result == "The answer is 42"

    @pytest.mark.asyncio
    async def test_simple_returns_empty_on_none(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=None),
                )
            ],
        )
        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await service.create_chat_completion_simple(
            [{"role": "user", "content": "hi"}]
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_simple_calls_without_streaming(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok"),
                )
            ],
        )
        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        await service.create_chat_completion_simple([{"role": "user", "content": "hi"}])

        call_kwargs = service.client.chat.completions.create.call_args
        assert call_kwargs.kwargs["stream"] is False


class TestTelemetryInit:
    """Tests for telemetry initialization."""

    @pytest.fixture
    def service(self):
        with (
            patch("nebulus_atom.services.openai_service.Config") as mock_config,
            patch("nebulus_atom.services.openai_service.AsyncOpenAI"),
        ):
            mock_config.NEBULUS_BASE_URL = "http://localhost:5000/v1"
            mock_config.NEBULUS_API_KEY = "test-key"
            mock_config.NEBULUS_MODEL = "test-model"
            mock_config.NEBULUS_TIMEOUT = 300.0
            mock_config.NEBULUS_STREAMING = False

            from nebulus_atom.services.openai_service import OpenAIService

            svc = OpenAIService()
            yield svc

    @pytest.mark.asyncio
    async def test_telemetry_initialized_with_model(self, service):
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok"),
                )
            ],
            usage=None,
        )
        service.client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("nebulus_atom.services.openai_service.Config") as mock_config:
            mock_config.NEBULUS_STREAMING = False

            async for _ in service.create_chat_completion(
                [{"role": "user", "content": "hi"}]
            ):
                pass

            assert service.last_telemetry["model"] == "test-model"
