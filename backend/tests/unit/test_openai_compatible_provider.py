from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.providers.services.base import ProviderRequestError
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.types import ChatGenerateRequest, EmbeddingRequest

pytestmark = pytest.mark.unit_no_db


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self):
        yield from self._payload


class _FakeAsyncResponse:
    def __init__(self, lines):
        self.status_code = 200
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b""


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        return _FakeAsyncResponse(
            [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                'data: {"choices":[{"delta":{"content":" world"}}]}',
                "data: [DONE]",
            ]
        )


class _FakeTimeout:
    def __init__(self, *args, **kwargs):
        pass


class _ShapeAsyncClient:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        return _FakeAsyncResponse(self._lines)


class _CapturingAsyncClient:
    def __init__(self, capture):
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        self._capture.update(kwargs)
        return _FakeAsyncResponse(
            [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                "data: [DONE]",
            ]
        )


class _UnreadErrorAsyncResponse:
    def __init__(self, payload):
        self.status_code = 400
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        if False:
            yield ""

    async def aread(self):
        return self._payload

    def json(self):
        raise RuntimeError("ResponseNotRead")

    @property
    def text(self):
        raise RuntimeError("ResponseNotRead")


class _UnreadErrorAsyncClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        return _UnreadErrorAsyncResponse(self._payload)


def _request() -> ChatGenerateRequest:
    return ChatGenerateRequest(
        model="demo",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=32,
        base_url="http://mock/v1",
        api_key="k",
        metadata={"timeout_seconds": 8.0, "read_timeout_seconds": 30.0},
    )


def test_openai_compatible_provider_generate_and_sync_stream(monkeypatch):
    provider = OpenAICompatibleProvider()
    called_urls = []

    def _fake_post(url, *args, **kwargs):
        called_urls.append(url)
        return _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})

    def _fake_stream(method, url, *args, **kwargs):
        called_urls.append(url)
        return _FakeResponse(
            200,
            [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                'data: {"choices":[{"delta":{"content":" world"}}]}',
                "data: [DONE]",
            ],
        )

    fake_httpx = SimpleNamespace(
        post=_fake_post,
        stream=_fake_stream,
        Timeout=_FakeTimeout,
        AsyncClient=_FakeAsyncClient,
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setattr(
        "app.providers.services.url_resolution.os.path.exists",
        lambda path: path == "/.dockerenv",
    )

    request = _request()
    request = ChatGenerateRequest(
        model=request.model,
        messages=request.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        base_url="http://localhost:1234/v1",
        api_key=request.api_key,
        metadata=request.metadata,
    )

    result = provider.generate(request)
    assert result.content == "ok"
    assert "".join(provider.stream_generate_sync(request)) == "Hello world"
    assert called_urls == [
        "http://host.docker.internal:1234/v1/chat/completions",
        "http://host.docker.internal:1234/v1/chat/completions",
    ]


def test_openai_compatible_provider_embed_many_rewrites_localhost_in_docker(
    monkeypatch,
):
    provider = OpenAICompatibleProvider(supports_embeddings=True)
    called_urls = []

    def _fake_post(url, *args, **kwargs):
        called_urls.append(url)
        return _FakeResponse(200, {"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=_fake_post))
    monkeypatch.setattr(
        "app.providers.services.url_resolution.os.path.exists",
        lambda path: path == "/.dockerenv",
    )

    response = provider.embed_many(
        EmbeddingRequest(
            texts=["hi"],
            model="text-embedding-3-small",
            batch_size=1,
            normalize=False,
            dimension=3,
            timeout_seconds=8,
            provider_name="openai",
            metadata={"base_url": "http://localhost:1234/v1", "api_key": None},
        )
    )

    assert response.vectors == [[0.1, 0.2, 0.3]]
    assert called_urls == ["http://host.docker.internal:1234/v1/embeddings"]


@pytest.mark.asyncio
async def test_openai_compatible_provider_async_stream(monkeypatch):
    provider = OpenAICompatibleProvider()
    fake_httpx = SimpleNamespace(
        post=lambda *a, **k: _FakeResponse(200, {}),
        Timeout=_FakeTimeout,
        AsyncClient=_FakeAsyncClient,
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    chunks = []
    async for chunk in provider.stream_generate(_request()):
        chunks.append(chunk)
    assert "".join(chunks) == "Hello world"


@pytest.mark.asyncio
async def test_openai_compatible_provider_async_stream_includes_tools(monkeypatch):
    provider = OpenAICompatibleProvider()
    captured_payload: dict[str, object] = {}
    fake_httpx = SimpleNamespace(
        post=lambda *a, **k: _FakeResponse(200, {}),
        Timeout=_FakeTimeout,
        AsyncClient=lambda *a, **k: _CapturingAsyncClient(captured_payload),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    request = ChatGenerateRequest(
        model="demo",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=32,
        base_url="http://mock/v1",
        api_key="k",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_choice="auto",
        metadata={"timeout_seconds": 8.0, "read_timeout_seconds": 30.0},
    )

    chunks = []
    async for chunk in provider.stream_generate(request):
        chunks.append(chunk)

    assert "".join(chunks) == "Hello"
    assert captured_payload["json"]["tools"] == request.tools
    assert captured_payload["json"]["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_openai_compatible_provider_async_stream_preserves_error_message(
    monkeypatch,
):
    provider = OpenAICompatibleProvider()
    fake_httpx = SimpleNamespace(
        post=lambda *a, **k: _FakeResponse(200, {}),
        Timeout=_FakeTimeout,
        AsyncClient=lambda *a, **k: _UnreadErrorAsyncClient(
            b'{"error":{"message":"bad tool schema"}}'
        ),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    with pytest.raises(ProviderRequestError, match="bad tool schema"):
        async for _ in provider.stream_generate(_request()):
            pass


@pytest.mark.asyncio
async def test_openai_compatible_provider_async_stream_accepts_message_content_chunks(
    monkeypatch,
):
    provider = OpenAICompatibleProvider()
    fake_httpx = SimpleNamespace(
        post=lambda *a, **k: _FakeResponse(200, {}),
        Timeout=_FakeTimeout,
        AsyncClient=lambda *a, **k: _ShapeAsyncClient(
            [
                'data: {"choices":[{"message":{"content":"Hello"}}]}',
                'data: {"choices":[{"message":{"content":" world"}}]}',
                "data: [DONE]",
            ]
        ),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    chunks = []
    async for chunk in provider.stream_generate(_request()):
        chunks.append(chunk)
    assert "".join(chunks) == "Hello world"


@pytest.mark.asyncio
async def test_openai_compatible_provider_async_stream_normalizes_cumulative_chunks(
    monkeypatch,
):
    provider = OpenAICompatibleProvider()
    fake_httpx = SimpleNamespace(
        post=lambda *a, **k: _FakeResponse(200, {}),
        Timeout=_FakeTimeout,
        AsyncClient=lambda *a, **k: _ShapeAsyncClient(
            [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                'data: {"choices":[{"delta":{"content":"Hello world"}}]}',
                'data: {"choices":[{"delta":{"content":"Hello world!"}}]}',
                "data: [DONE]",
            ]
        ),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    chunks = []
    async for chunk in provider.stream_generate(_request()):
        chunks.append(chunk)

    assert chunks == ["Hello", " world", "!"]
    assert "".join(chunks) == "Hello world!"


@pytest.mark.asyncio
async def test_openai_compatible_provider_async_stream_accepts_text_field_chunks(
    monkeypatch,
):
    provider = OpenAICompatibleProvider()
    fake_httpx = SimpleNamespace(
        post=lambda *a, **k: _FakeResponse(200, {}),
        Timeout=_FakeTimeout,
        AsyncClient=lambda *a, **k: _ShapeAsyncClient(
            [
                'data: {"choices":[{"delta":{"text":"Hello"}}]}',
                'data: {"choices":[{"text":" world"}]}',
                "data: [DONE]",
            ]
        ),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    chunks = []
    async for chunk in provider.stream_generate(_request()):
        chunks.append(chunk)
    assert "".join(chunks) == "Hello world"


def test_openai_compatible_provider_lists_chat_and_embedding_models_separately(
    monkeypatch,
):
    provider = OpenAICompatibleProvider(
        supports_embeddings=True,
        base_url="https://api.example.com/v1",
        api_key="k",
    )
    fake_httpx = SimpleNamespace(
        get=lambda *a, **k: _FakeResponse(
            200,
            {
                "data": [
                    {"id": "gpt-5"},
                    {"id": "llama-3.3-70b-versatile"},
                    {"id": "text-embedding-3-large"},
                    {"id": "gpt-audio"},
                    {"id": "omni-moderation"},
                ]
            },
        )
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    chat_models = provider.list_models()
    embedding_models = provider.list_embedding_models()

    assert [model.name for model in chat_models] == ["gpt-5", "llama-3.3-70b-versatile"]
    assert [model.name for model in embedding_models] == ["text-embedding-3-large"]


def test_openai_compatible_provider_uses_groq_reasoning_fields() -> None:
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=32,
        base_url="https://api.groq.com/openai/v1",
        api_key="k",
        reasoning_enabled=True,
        reasoning_effort="medium",
    )

    OpenAICompatibleProvider()._apply_reasoning_request_settings(payload, request)

    assert payload["reasoning_effort"] == "medium"
    assert payload["include_reasoning"] is True
    assert "reasoning" not in payload


def test_openai_compatible_provider_disables_groq_reasoning_when_off() -> None:
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=32,
        base_url="https://api.groq.com/openai/v1",
        api_key="k",
        reasoning_enabled=False,
    )

    OpenAICompatibleProvider()._apply_reasoning_request_settings(payload, request)

    assert payload["include_reasoning"] is False
    assert "reasoning" not in payload


def test_openai_compatible_provider_uses_local_reasoning_controls_for_lmstudio() -> (
    None
):
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="qwen3-14b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="http://host.docker.internal:1234/v1",
        api_key="k",
        reasoning_enabled=True,
        reasoning_effort="high",
        metadata={"provider_type": "lmstudio"},
    )

    provider = OpenAICompatibleProvider()
    messages = provider._prepare_messages(request)
    provider._apply_reasoning_request_settings(payload, request)

    assert messages[-1]["content"].startswith("/think\n")
    assert payload["enable_thinking"] is True
    assert payload["reasoning_effort"] == "high"
    assert payload["reasoning"] == {"effort": "high"}


def test_openai_compatible_provider_uses_local_reasoning_controls_off_for_lmstudio() -> (
    None
):
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="qwen3-14b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="http://host.docker.internal:1234/v1",
        api_key="k",
        reasoning_enabled=False,
        metadata={"provider_type": "lmstudio"},
    )

    provider = OpenAICompatibleProvider()
    messages = provider._prepare_messages(request)
    provider._apply_reasoning_request_settings(payload, request)

    assert messages[-1]["content"].startswith("/no_think\n")
    assert payload["enable_thinking"] is False
    assert "reasoning_effort" not in payload
    assert "reasoning" not in payload


def test_openai_compatible_provider_uses_local_reasoning_controls_off_for_nemotron() -> (
    None
):
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="nvidia/nemotron-3-nano-4b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="http://host.docker.internal:1234/v1",
        api_key="k",
        reasoning_enabled=False,
        metadata={"provider_type": "lmstudio"},
    )

    provider = OpenAICompatibleProvider()
    messages = provider._prepare_messages(request)
    provider._apply_reasoning_request_settings(payload, request)

    assert messages[-1]["content"].startswith("/no_think\n")
    assert payload["enable_thinking"] is False
    assert "reasoning_effort" not in payload
    assert "reasoning" not in payload


def test_openai_compatible_provider_auto_reasoning_preserves_model_defaults() -> None:
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="nvidia/nemotron-3-nano-4b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="http://host.docker.internal:1234/v1",
        api_key="k",
        reasoning_enabled=False,
        tool_choice="required",
        metadata={"provider_type": "opencode-zen", "reasoning_mode": "auto"},
    )

    provider = OpenAICompatibleProvider()
    messages = provider._prepare_messages(request)
    provider._apply_reasoning_request_settings(payload, request)

    assert messages[-1]["content"] == "Explain this."
    assert payload == {}


def test_openai_compatible_provider_extracts_tagged_reasoning_content() -> None:
    thinking, answer = OpenAICompatibleProvider._extract_tagged_reasoning_content(
        "<think>Plan first.</think>Final answer.",
        enabled=True,
    )

    assert thinking == "Plan first."
    assert answer == "Final answer."


def test_openai_compatible_provider_splits_tagged_reasoning_stream() -> None:
    events, state = OpenAICompatibleProvider._split_stream_content_by_reasoning_tags(
        "<think>Plan",
        state="answer",
        enabled=True,
    )
    assert events == [("thinking", "Plan")]
    assert state == "thinking"

    events, state = OpenAICompatibleProvider._split_stream_content_by_reasoning_tags(
        " first.</think>Final",
        state=state,
        enabled=True,
    )
    assert events == [("thinking", " first."), ("delta", "Final")]
    assert state == "answer"


def test_openai_compatible_provider_prepares_gemma_thinking() -> None:
    request = ChatGenerateRequest(
        model="google/gemma-4-e4b",
        messages=[{"role": "user", "content": "Hello."}],
        temperature=0.1,
        max_tokens=64,
        base_url="http://localhost:1234/v1",
        api_key="k",
        reasoning_enabled=True,
        metadata={"provider_type": "lmstudio"},
    )

    messages = OpenAICompatibleProvider._prepare_messages(request)

    assert messages[0]["role"] == "system"
    assert "<|think|>" in str(messages[0]["content"])


def test_openai_compatible_provider_splits_gemma_channel_stream() -> None:
    events, state = OpenAICompatibleProvider._split_gemma_channel_content(
        "<|channel>thought\nPlan first.\n<channel|>Final answer.",
        state="answer",
        enabled=True,
    )

    assert ("thinking", "Plan first.") in events
    assert ("delta", "Final answer.") in events
    assert state == "answer"
