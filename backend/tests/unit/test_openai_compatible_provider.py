from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.openai_compatible_config import OpenAICompatibleEndpointSettings
from app.providers.services.types import ChatGenerateRequest, EmbeddingRequest, ProviderModelInfo

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


def test_openai_compatible_provider_generate_unwraps_success_data_envelope(monkeypatch):
    provider = OpenAICompatibleProvider()
    response_payload = {
        "success": True,
        "data": {
            "choices": [{"message": {"content": "wrapped response"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        },
    }
    fake_httpx = SimpleNamespace(post=lambda *args, **kwargs: _FakeResponse(200, response_payload))
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    response = provider.generate(_request())

    assert response.content == "wrapped response"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 2}


def test_openai_compatible_provider_rejects_unsuccessful_data_envelope(monkeypatch):
    provider = OpenAICompatibleProvider()
    fake_httpx = SimpleNamespace(
        post=lambda *args, **kwargs: _FakeResponse(200, {"success": False, "data": {"choices": []}})
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    with pytest.raises(RuntimeError, match="unsuccessful response"):
        provider.generate(_request())


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
    assert "stream_options" not in captured_payload["json"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_name", "provider_metadata", "request_provider", "expects_usage"),
    [
        ("deepseek", None, "deepseek", True),
        (
            "custom",
            {"openai_compatible": {"stream_usage": "enabled"}},
            "custom",
            True,
        ),
        ("custom", None, "custom", False),
    ],
)
async def test_chat_stream_requests_usage_only_for_documented_or_enabled_endpoints(
    monkeypatch,
    provider_name,
    provider_metadata,
    request_provider,
    expects_usage,
):
    captured: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        provider_name=provider_name,
        provider_metadata=provider_metadata,
    )
    request = _request()
    request.metadata["provider_type"] = request_provider
    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            Timeout=_FakeTimeout,
            AsyncClient=lambda *args, **kwargs: _CapturingAsyncClient(captured),
        ),
    )

    async for _event in provider.stream_generate_events(request):
        pass

    stream_options = captured["json"].get("stream_options")
    if expects_usage:
        assert stream_options == {"include_usage": True}
    else:
        assert stream_options is None


@pytest.mark.asyncio
async def test_chat_stream_retries_without_rejected_optional_usage_parameter(monkeypatch):
    captured_payloads: list[dict[str, object]] = []

    class _FallbackAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            captured_payloads.append(kwargs["json"].copy())
            if len(captured_payloads) == 1:
                return _UnreadErrorAsyncResponse(
                    b'{"error":{"message":"Unknown parameter: stream_options"}}'
                )
            return _FakeAsyncResponse(
                ['data: {"choices":[{"delta":{"content":"safe retry"}}]}', "data: [DONE]"]
            )

    provider = OpenAICompatibleProvider(provider_name="deepseek")
    request = _request()
    request.metadata["provider_type"] = "deepseek"
    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(Timeout=_FakeTimeout, AsyncClient=_FallbackAsyncClient),
    )

    events = [event async for event in provider.stream_generate_events(request)]

    assert events == [{"type": "delta", "text": "safe retry"}]
    assert captured_payloads[0]["stream_options"] == {"include_usage": True}
    assert "stream_options" not in captured_payloads[1]


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


def test_custom_model_listing_keeps_multimodal_chat_and_embed_named_models(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        supports_embeddings=True,
        base_url="https://api.example.com/v1",
    )
    fake_httpx = SimpleNamespace(
        get=lambda *args, **kwargs: _FakeResponse(
            200,
            {
                "data": [
                    {"id": "vision-image-chat-v1"},
                    {"id": "nomic-embed-text"},
                ]
            },
        )
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    assert [model.name for model in provider.list_models()] == ["vision-image-chat-v1"]
    assert [model.name for model in provider.list_embedding_models()] == ["nomic-embed-text"]


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


def test_openai_compatible_provider_applies_discovered_effort_metadata() -> None:
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="vendor/unknown-reasoner-v9",
        messages=[{"role": "user", "content": "Think this through."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://api.example.test/v1",
        reasoning_enabled=True,
        reasoning_effort="very_high",
        metadata={
            "provider_type": "openai",
            "reasoning_mode": "explicit",
            "model_reasoning_capabilities": {
                "reasoning_capabilities_known": True,
                "supports_reasoning": True,
                "supported_reasoning_efforts": ["low", "very_high"],
                "reasoning_effort_values": {"very_high": "xhigh"},
                "request_controls_on": ["reasoning_effort"],
                "request_controls_off": ["reasoning_effort_none"],
            },
        },
    )

    OpenAICompatibleProvider()._apply_reasoning_request_settings(payload, request)

    assert payload == {"reasoning_effort": "xhigh"}


def test_openai_compatible_provider_applies_discovered_reasoning_off_control() -> None:
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="vendor/unknown-reasoner-v9",
        messages=[{"role": "user", "content": "Think this through."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://api.example.test/v1",
        reasoning_enabled=False,
        metadata={
            "provider_type": "openai",
            "reasoning_mode": "off",
            "model_reasoning_capabilities": {
                "reasoning_capabilities_known": True,
                "supports_reasoning": True,
                "supported_reasoning_efforts": ["low", "high"],
                "supports_thinking_toggle": True,
                "request_controls_off": ["reasoning_effort_none"],
            },
        },
    )

    OpenAICompatibleProvider()._apply_reasoning_request_settings(payload, request)

    assert payload == {"reasoning_effort": "none"}


def test_openai_compatible_provider_uses_local_reasoning_controls_for_lmstudio() -> None:
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
    assert payload["reasoning"] == "high"


def test_openai_compatible_provider_uses_local_reasoning_controls_off_for_lmstudio() -> None:
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


def test_openai_compatible_provider_maps_deepseek_universal_effort() -> None:
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://api.deepseek.com",
        api_key="k",
        reasoning_enabled=True,
        reasoning_effort="very_high",
        metadata={"provider_type": "deepseek"},
    )

    OpenAICompatibleProvider()._apply_reasoning_request_settings(payload, request)

    assert payload == {"thinking": {"type": "enabled"}, "reasoning_effort": "max"}


def test_openai_compatible_provider_uses_local_reasoning_controls_off_for_nemotron() -> None:
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
    assert payload["reasoning"] == "off"


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


def test_openai_compatible_required_tools_suppress_reasoning_for_any_provider() -> None:
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="qwen3-14b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://example.test/v1",
        reasoning_enabled=True,
        tool_choice="required",
        metadata={"provider_type": "openrouter", "reasoning_mode": "explicit"},
    )

    provider = OpenAICompatibleProvider(provider_name="openrouter")
    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {}


def test_openai_compatible_downgrades_deepseek_v4_forced_tool_choice() -> None:
    request = ChatGenerateRequest(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Check my inbox."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://opencode.ai/zen/v1",
        tool_choice="required",
        metadata={"provider_type": "opencode-zen"},
    )

    assert OpenAICompatibleProvider._effective_tool_choice(request) == "auto"


def test_openai_compatible_omits_deepseek_v4_tool_choice_when_thinking() -> None:
    request = ChatGenerateRequest(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Check my inbox."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://opencode.ai/zen/v1",
        tools=[{"type": "function", "function": {"name": "search"}}],
        tool_choice="auto",
        reasoning_enabled=True,
        metadata={"provider_type": "opencode-zen", "reasoning_mode": "explicit"},
    )

    assert OpenAICompatibleProvider._effective_tool_choice(request) is None


def test_openai_compatible_auto_mode_observes_tagged_reasoning() -> None:
    request = ChatGenerateRequest(
        model="qwen3-14b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="http://host.docker.internal:1234/v1",
        metadata={"provider_type": "ollama", "reasoning_mode": "auto"},
    )

    events, state = OpenAICompatibleProvider._split_stream_content_for_reasoning(
        "<think>Plan first.</think>Final answer.",
        state="answer",
        enabled=OpenAICompatibleProvider._reasoning_observation_enabled(request),
        model=request.model,
    )

    assert events == [("thinking", "Plan first."), ("delta", "Final answer.")]
    assert state == "answer"


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

    messages = OpenAICompatibleProvider()._prepare_messages(request)

    assert messages[0]["role"] == "system"
    assert "<|think|>" in str(messages[0]["content"])


def test_openai_compatible_provider_preserves_attached_image_mime_type() -> None:
    request = ChatGenerateRequest(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Describe this image."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://api.example.test/v1",
        images=["data:image/png;base64,iVBORw0KGgo="],
        metadata={"provider_type": "openai"},
    )

    messages = OpenAICompatibleProvider()._prepare_messages(request)

    assert messages[-1]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
    }


def test_openai_compatible_provider_splits_gemma_channel_stream() -> None:
    events, state = OpenAICompatibleProvider._split_gemma_channel_content(
        "<|channel>thought\nPlan first.\n<channel|>Final answer.",
        state="answer",
        enabled=True,
    )

    assert ("thinking", "Plan first.") in events
    assert ("delta", "Final answer.") in events
    assert state == "answer"


def test_custom_endpoint_does_not_guess_reasoning_parameters_from_model_name() -> None:
    provider = OpenAICompatibleProvider(provider_name="custom")
    request = ChatGenerateRequest(
        model="qwen3-14b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://endpoint.example/v1",
        reasoning_enabled=True,
        reasoning_effort="high",
        metadata={"provider_type": "custom", "reasoning_mode": "explicit"},
    )
    payload: dict[str, object] = {}

    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {}
    assert provider._prepare_messages(request)[-1]["content"] == "Explain this."

    gemma_request = ChatGenerateRequest(
        model="gemma-3-12b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://endpoint.example/v1",
        reasoning_enabled=True,
    )
    assert provider._prepare_messages(gemma_request)[-1]["content"] == "Explain this."


@pytest.mark.parametrize(
    ("effort", "mapped"),
    [
        ("low", "minimal"),
        ("medium", "balanced"),
        ("high", "deep"),
        ("very_high", "xhigh"),
        ("extreme_high", "maximum"),
    ],
)
def test_custom_reasoning_levels_use_only_configured_endpoint_fields(effort, mapped) -> None:
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        provider_metadata={
            "openai_compatible": {
                "reasoning": {
                    "supported_efforts": ["low", "medium", "high", "very_high", "extreme_high"],
                    "effort_parameter": "reasoning.effort",
                    "effort_values": {
                        "low": "minimal",
                        "medium": "balanced",
                        "high": "deep",
                        "very_high": "xhigh",
                        "extreme_high": "maximum",
                    },
                    "toggle_parameter": "enable_thinking",
                }
            }
        },
    )
    request = ChatGenerateRequest(
        model="any-model",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://endpoint.example/v1",
        reasoning_enabled=True,
        reasoning_effort=effort,
        metadata={"provider_type": "custom", "reasoning_mode": "explicit"},
    )
    payload: dict[str, object] = {}

    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {"reasoning": {"effort": mapped}, "enable_thinking": True}


def test_custom_reasoning_off_sends_only_configured_disable_field() -> None:
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        provider_metadata={
            "openai_compatible": {
                "reasoning": {
                    "supported_efforts": ["low", "medium", "high"],
                    "effort_parameter": "reasoning.effort",
                    "effort_off_value": "none",
                    "toggle_parameter": "enable_thinking",
                    "toggle_disabled_value": False,
                }
            }
        },
    )
    request = ChatGenerateRequest(
        model="any-model",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://endpoint.example/v1",
        reasoning_enabled=False,
        metadata={"provider_type": "custom", "reasoning_mode": "off"},
    )
    payload: dict[str, object] = {}

    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {
        "enable_thinking": False,
        "reasoning": {"effort": "none"},
    }


def test_custom_route_and_api_key_header_preserve_base_query(monkeypatch) -> None:
    captured: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        provider_metadata={
            "openai_compatible": {
                "chat_completions_path": "/custom/chat",
                "auth_header_name": "X-API-Key",
                "auth_scheme": "raw",
            }
        },
    )

    def _fake_post(url, *args, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=_fake_post))
    request = ChatGenerateRequest(
        model="deployment-1",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=32,
        base_url="https://endpoint.example/v1/custom/chat?tenant=team-a",
        api_key="secret-key",
        metadata={"provider_type": "custom"},
    )

    assert provider.generate(request).content == "ok"
    assert captured["url"] == "https://endpoint.example/v1/custom/chat?tenant=team-a"
    assert captured["headers"]["X-API-Key"] == "secret-key"
    assert "Authorization" not in captured["headers"]


def test_responses_protocol_maps_messages_tools_usage_and_manual_route(monkeypatch) -> None:
    captured: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        provider_metadata={
            "openai_compatible": {
                "api_mode": "responses",
                "responses_path": "/responses-v2",
                "send_temperature": False,
            }
        },
    )

    def _fake_post(url, *args, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeResponse(
            200,
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Answer"}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "lookup",
                        "arguments": '{"query":"x"}',
                    },
                ],
                "usage": {"input_tokens": 7, "output_tokens": 3},
            },
        )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=_fake_post))
    request = ChatGenerateRequest(
        model="response-model",
        messages=[
            {"role": "user", "content": "Question"},
            {
                "role": "assistant",
                "content": "Calling a tool",
                "tool_calls": [
                    {
                        "id": "call-old",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": '{"query":"old"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-old", "content": "tool result"},
        ],
        temperature=0.1,
        max_tokens=32,
        base_url="https://endpoint.example/v1",
        api_key="key",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Lookup data",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Duplicate lookup definition",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ],
        tool_choice="auto",
        metadata={"provider_type": "custom"},
    )

    response = provider.generate(request)

    assert captured["url"] == "https://endpoint.example/v1/responses-v2"
    assert captured["json"]["max_output_tokens"] == 32
    assert "temperature" not in captured["json"]
    input_items = captured["json"]["input"]
    assert input_items[0] == {
        "type": "message",
        "role": "user",
        "content": "Question",
    }
    assert input_items[1]["content"] == "Calling a tool"
    assert input_items[2]["type"] == "function_call"
    assert input_items[3] == {
        "type": "function_call_output",
        "call_id": "call-old",
        "output": "tool result",
    }
    assert captured["json"]["tools"] == [
        {
            "type": "function",
            "name": "lookup",
            "parameters": {"type": "object", "properties": {}},
            "description": "Lookup data",
        }
    ]
    assert response.content == "Answer"
    assert response.tool_calls == [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "lookup", "arguments": '{"query":"x"}'},
        }
    ]
    assert response.usage == {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}


@pytest.mark.asyncio
async def test_responses_stream_maps_text_tool_arguments_and_usage(monkeypatch) -> None:
    lines = [
        'data: {"type":"response.output_text.delta","delta":"Hello"}',
        'data: {"type":"response.output_item.added","output_index":0,"item":{"type":"function_call","call_id":"call-1","name":"lookup","arguments":""}}',
        'data: {"type":"response.function_call_arguments.delta","output_index":0,"delta":"{\\"q\\":1}"}',
        'data: {"type":"response.completed","response":{"usage":{"input_tokens":4,"output_tokens":2}}}',
        "data: [DONE]",
    ]
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        provider_metadata={"openai_compatible": {"api_mode": "responses"}},
    )
    fake_httpx = SimpleNamespace(
        Timeout=_FakeTimeout,
        AsyncClient=lambda *args, **kwargs: _ShapeAsyncClient(lines),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    request = ChatGenerateRequest(
        model="response-model",
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=16,
        base_url="https://endpoint.example/v1",
        metadata={"provider_type": "custom"},
    )

    events = [event async for event in provider.stream_generate_events(request)]

    assert events[0] == {"type": "delta", "text": "Hello"}
    assert events[1]["type"] == "tool_calls_delta"
    assert events[2]["tool_calls"][0]["function"]["arguments"] == '{"q":1}'
    assert events[3] == {
        "type": "usage",
        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
    }


def test_custom_model_discovery_can_be_disabled_and_health_is_degraded() -> None:
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        base_url="https://endpoint.example/v1",
        provider_metadata={"openai_compatible": {"models_path": None}},
    )

    assert provider.supports_model_listing is False
    with pytest.raises(ProviderCapabilityError, match="discovery is disabled"):
        provider.list_models()
    assert provider.health_check().status == "degraded"


def test_chat_completions_accepts_tool_calls_with_null_content(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(provider_name="custom")
    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            post=lambda *args, **kwargs: _FakeResponse(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {"name": "lookup", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        ),
    )
    request = ChatGenerateRequest(
        model="tool-model",
        messages=[{"role": "user", "content": "Use a tool."}],
        temperature=0.1,
        max_tokens=32,
        base_url="https://endpoint.example/v1",
    )

    response = provider.generate(request)

    assert response.content == ""
    assert response.tool_calls is not None
    assert response.tool_calls[0]["id"] == "call-1"


@pytest.mark.asyncio
async def test_chat_completions_stream_reports_in_band_provider_errors(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(provider_name="custom")
    fake_httpx = SimpleNamespace(
        Timeout=_FakeTimeout,
        AsyncClient=lambda *args, **kwargs: _ShapeAsyncClient(
            ['data: {"error":{"message":"Unsupported parameter: enable_thinking"}}']
        ),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    with pytest.raises(ProviderRequestError, match="Unsupported parameter: enable_thinking"):
        async for _ in provider.stream_generate_events(_request()):
            pass


def test_custom_model_reasoning_is_intersection_of_config_and_model_advertisement() -> None:
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        provider_metadata={
            "openai_compatible": {
                "reasoning": {
                    "supported_efforts": ["low"],
                    "effort_parameter": "reasoning.effort",
                }
            }
        },
    )

    capabilities = provider._reasoning_capabilities_for_model(
        {"id": "model", "supported_reasoning_efforts": ["low", "high"]}
    )

    assert capabilities["supported_reasoning_efforts"] == ["low"]


def test_custom_embedding_payload_can_send_dimensions_and_reorders_indexed_results(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        supports_embeddings=True,
        provider_metadata={"openai_compatible": {"send_embedding_dimensions": True}},
    )

    def _fake_post(url, *args, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeResponse(
            200,
            {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=_fake_post))
    response = provider.embed_many(
        EmbeddingRequest(
            texts=["first", "second"],
            model="embedding-model",
            batch_size=2,
            normalize=False,
            dimension=2,
            timeout_seconds=8,
            provider_name="custom",
            metadata={"base_url": "https://endpoint.example/v1", "api_key": "key"},
        )
    )

    assert captured["json"]["dimensions"] == 2
    assert response.vectors == [[1.0, 0.0], [0.0, 1.0]]


def test_cline_uses_models_route_and_disables_embeddings(monkeypatch) -> None:
    captured: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        provider_name="cline",
        base_url="https://api.cline.bot/api/v1",
        api_key="test-key",
    )

    def _fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeResponse(
            200,
            {
                "object": "list",
                "data": [
                    {
                        "id": "anthropic/claude-sonnet-4-6",
                        "object": "model",
                        "context_length": 200000,
                    },
                    {"id": "openai/gpt-6.1-mini"},
                    {"id": "text-embedding/example"},
                ],
            },
        )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(get=_fake_get))

    assert provider.endpoint_settings.chat_completions_path == "/chat/completions"
    assert provider.endpoint_settings.models_path == "/models"
    assert provider.endpoint_settings.embeddings_path is None
    assert provider.supports_model_listing is True
    models = provider.list_models()
    assert [model.name for model in models] == [
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-6.1-mini",
    ]
    assert models[0].context_window == 200000
    assert captured["url"] == "https://api.cline.bot/api/v1/models"
    assert "Authorization" not in captured["headers"]
    assert captured["timeout"] == 8.0
    with pytest.raises(ProviderCapabilityError, match="embedding-capable"):
        provider.list_embedding_models()


def test_cline_public_catalog_does_not_report_chat_credentials_as_healthy(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(provider_name="cline")
    monkeypatch.setattr(
        provider,
        "list_models",
        lambda: [
            ProviderModelInfo(
                name="anthropic/claude-sonnet-4-6",
                kind="chat",
            )
        ],
    )

    result = provider.health_check()

    assert result.status == "degraded"
    assert result.error_code == "chat_access_not_verified"
    assert result.metadata == {
        "listing": "public_catalog",
        "chat_probe": "not_run",
        "model_count": 1,
    }


def test_cline_chat_request_uses_bearer_auth_and_provider_model_id(monkeypatch) -> None:
    captured: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        provider_name="cline",
        base_url="https://api.cline.bot/api/v1",
        api_key="cline-test-key",
    )

    def _fake_post(url, *args, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeResponse(200, {"choices": [{"message": {"content": "Cline response"}}]})

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=_fake_post))
    response = provider.generate(
        ChatGenerateRequest(
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            max_tokens=64,
            base_url="https://api.cline.bot/api/v1",
            api_key="cline-test-key",
            metadata={"provider_type": "cline"},
        )
    )

    assert response.content == "Cline response"
    assert captured["url"] == "https://api.cline.bot/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer cline-test-key"
    assert captured["json"]["model"] == "anthropic/claude-sonnet-4-6"


def test_mistral_reasoning_chunks_are_separated_from_final_content(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(
        provider_name="mistral",
        base_url="https://api.mistral.ai/v1",
        api_key="mistral-test-key",
    )
    request = ChatGenerateRequest(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": "What is 17 times 23?"}],
        temperature=0.1,
        max_tokens=128,
        base_url="https://api.mistral.ai/v1",
        api_key="mistral-test-key",
        reasoning_enabled=True,
        reasoning_effort="high",
        metadata={"provider_type": "mistral", "reasoning_mode": "explicit"},
    )

    def _fake_post(url, *args, **kwargs):
        assert url == "https://api.mistral.ai/v1/chat/completions"
        assert kwargs["json"]["reasoning_effort"] == "high"
        return _FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {
                                    "type": "thinking",
                                    "thinking": [{"type": "text", "text": "calculate"}],
                                },
                                {"type": "text", "text": "391"},
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=_fake_post))
    response = provider.generate(request)

    assert response.content == "391"
    assert response.thinking_content == "calculate"


async def test_mistral_streaming_thinking_chunks_are_not_emitted_as_answer(monkeypatch) -> None:
    lines = [
        'data: {"choices":[{"delta":{"content":[{"type":"thinking","thinking":[{"type":"text","text":"step"}]}]}}]}',
        'data: {"choices":[{"delta":{"content":[{"type":"thinking","thinking":[{"type":"text","text":"step"}]},{"type":"text","text":"answer"}]}}]}',
        "data: [DONE]",
    ]
    provider = OpenAICompatibleProvider(provider_name="mistral")
    request = ChatGenerateRequest(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=32,
        base_url="https://api.mistral.ai/v1",
        reasoning_enabled=True,
        reasoning_effort="high",
        metadata={"provider_type": "mistral", "reasoning_mode": "explicit"},
    )
    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            Timeout=_FakeTimeout,
            AsyncClient=lambda *args, **kwargs: _ShapeAsyncClient(lines),
        ),
    )

    events = [event async for event in provider.stream_generate_events(request)]

    assert [event for event in events if event["type"] == "thinking"] == [
        {"type": "thinking", "text": "step"}
    ]
    assert [event for event in events if event["type"] == "delta"] == [
        {"type": "delta", "text": "answer"}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_name", "provider_type", "model", "expected"),
    [
        ("deepseek", "deepseek", "deepseek-reasoner", True),
        ("openrouter", "openrouter", "deepseek/deepseek-chat", True),
        ("openai-compatible", "custom", "DeepSeek-V4-Flash", True),
        ("openai", "openai", "gpt-5", False),
    ],
)
async def test_deepseek_stream_preserves_exact_private_reasoning_continuation(
    monkeypatch, provider_name, provider_type, model, expected
) -> None:
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"opaque continuation"}}]}',
        "data: [DONE]",
    ]
    provider = OpenAICompatibleProvider(provider_name=provider_name)
    request = replace(_request(), model=model, metadata={"provider_type": provider_type})
    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            Timeout=_FakeTimeout,
            AsyncClient=lambda *args, **kwargs: _ShapeAsyncClient(lines),
        ),
    )

    events = [event async for event in provider.stream_generate_events(request)]

    continuation_event = {
        "type": "provider_continuation",
        "reasoning_content": "opaque continuation",
    }
    assert (continuation_event in events) is expected


def test_meta_uses_stateless_responses_and_private_reasoning(monkeypatch) -> None:
    captured: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        provider_name="meta",
        base_url="https://api.meta.ai/v1",
        api_key="meta-test-key",
    )

    def _fake_post(url, *args, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeResponse(
            200,
            {
                "output": [
                    {"type": "reasoning", "summary": [{"text": "private reasoning"}]},
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Meta response"}],
                    },
                ]
            },
        )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=_fake_post))
    request = ChatGenerateRequest(
        model="muse-spark-1.3",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.1,
        max_tokens=128,
        base_url="https://api.meta.ai/v1",
        api_key="meta-test-key",
        reasoning_enabled=True,
        reasoning_effort="extreme_high",
        metadata={"provider_type": "meta", "reasoning_mode": "explicit"},
    )

    response = provider.generate(request)

    assert response.content == "Meta response"
    assert response.thinking_content is None
    assert captured["url"] == "https://api.meta.ai/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer meta-test-key"
    assert captured["json"]["store"] is False
    assert captured["json"]["reasoning"] == {"effort": "max"}
    assert "reasoning_effort" not in captured["json"]
    assert "temperature" not in captured["json"]

    off_payload = provider._build_responses_payload(
        ChatGenerateRequest(
            model="muse-spark-1.3-contributor",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.1,
            max_tokens=128,
            base_url="https://api.meta.ai/v1",
            reasoning_enabled=False,
            metadata={"provider_type": "meta", "reasoning_mode": "off"},
        ),
        stream=False,
    )
    assert off_payload["store"] is False
    assert "reasoning" not in off_payload


def test_meta_model_listing_omits_non_chat_models(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(
        provider_name="meta",
        base_url="https://api.meta.ai/v1",
        api_key="meta-test-key",
    )
    called: list[str] = []

    def _fake_get(url, *args, **kwargs):
        called.append(url)
        return _FakeResponse(
            200,
            {
                "data": [
                    {"id": "muse-spark-1.3"},
                    {"id": "muse-image-1.0"},
                    {"id": "sam-3"},
                ]
            },
        )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(get=_fake_get))

    assert [model.name for model in provider.list_models()] == ["muse-spark-1.3"]
    assert called == ["https://api.meta.ai/v1/models"]


@pytest.mark.parametrize(
    "field_path",
    ["model", "temperature", "messages.role", "input.foo", "tools", "bad..path"],
)
def test_custom_reasoning_rejects_unsafe_or_reserved_field_paths(field_path: str) -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleEndpointSettings.model_validate(
            {"reasoning": {"effort_parameter": field_path}}
        )


@pytest.mark.parametrize("header_name", ["Content-Type", "Host", "Content-Length", "Cookie"])
def test_custom_auth_header_rejects_transport_and_cookie_headers(header_name: str) -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleEndpointSettings.model_validate({"auth_header_name": header_name})


@pytest.mark.parametrize(
    ("model", "enabled", "effort", "expected"),
    [
        ("nvidia/nemotron-3-ultra-550b-a55b", True, "medium", "medium"),
        ("nvidia/nemotron-3-ultra-550b-a55b", True, "high", "high"),
        ("nvidia/nemotron-3-ultra-550b-a55b", False, None, "none"),
        ("nvidia/nemotron-3-super-120b-a12b", True, "low", "low"),
        ("nvidia/nemotron-3-super-120b-a12b", True, "high", "high"),
        ("nvidia/nemotron-3-super-120b-a12b", False, None, "none"),
    ],
)
def test_nvidia_nim_nemotron_efforts_use_documented_request_values(
    model: str, enabled: bool, effort: str | None, expected: str
) -> None:
    provider = OpenAICompatibleProvider(provider_name="nvidia-nim")
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model=model,
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=128,
        base_url="https://integrate.api.nvidia.com/v1",
        reasoning_enabled=enabled,
        reasoning_effort=effort,
        metadata={"provider_type": "nvidia-nim", "reasoning_mode": "explicit"},
    )

    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {"reasoning_effort": expected}


@pytest.mark.parametrize("enabled", [True, False])
def test_nvidia_nim_nemotron_nano_uses_documented_thinking_toggle(enabled: bool) -> None:
    provider = OpenAICompatibleProvider(provider_name="nvidia-nim")
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="nvidia/nemotron-3-nano-30b-a3b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=128,
        base_url="https://integrate.api.nvidia.com/v1",
        reasoning_enabled=enabled,
        metadata={"provider_type": "nvidia-nim", "reasoning_mode": "explicit"},
    )

    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {"chat_template_kwargs": {"enable_thinking": enabled}}


def test_unknown_model_auto_reasoning_leaves_provider_defaults_untouched() -> None:
    provider = OpenAICompatibleProvider(provider_name="nvidia-nim")
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="vendor/unlisted-model",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=128,
        base_url="https://integrate.api.nvidia.com/v1",
        reasoning_enabled=False,
        metadata={"provider_type": "nvidia-nim", "reasoning_mode": "auto"},
    )

    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {}


def test_nvidia_nemotron_reasoning_remains_enabled_with_required_tool_choice() -> None:
    provider = OpenAICompatibleProvider(provider_name="nvidia-nim")
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="nvidia/nemotron-3-ultra-550b-a55b",
        messages=[{"role": "user", "content": "Use the available tool."}],
        temperature=0.1,
        max_tokens=128,
        base_url="https://integrate.api.nvidia.com/v1",
        reasoning_enabled=True,
        reasoning_effort="high",
        tool_choice="required",
        metadata={"provider_type": "nvidia-nim", "reasoning_mode": "explicit"},
    )

    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {"reasoning_effort": "high"}


def test_custom_reasoning_preserves_provider_specific_effort_value() -> None:
    provider = OpenAICompatibleProvider(
        provider_name="custom",
        provider_metadata={
            "openai_compatible": {
                "reasoning": {
                    "supported_efforts": ["minimal", "ultra", "tier-5"],
                    "effort_parameter": "reasoning.effort",
                    "effort_values": {
                        "minimal": "minimal",
                        "ultra": "ultra",
                        "tier_5": "vendor-tier-five",
                    },
                }
            }
        },
    )
    request = ChatGenerateRequest(
        model="any-model",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://endpoint.example/v1",
        reasoning_enabled=True,
        reasoning_effort="tier_5",
        metadata={"provider_type": "custom", "reasoning_mode": "explicit"},
    )
    payload: dict[str, object] = {}

    provider._apply_reasoning_request_settings(payload, request)

    assert payload == {"reasoning": {"effort": "vendor-tier-five"}}


def test_custom_reasoning_rejects_unsafe_advertised_effort_metadata() -> None:
    with pytest.raises(ValidationError):
        OpenAICompatibleEndpointSettings.model_validate(
            {
                "reasoning": {
                    "supported_efforts": ["bad/value"],
                    "effort_parameter": "reasoning.effort",
                }
            }
        )
