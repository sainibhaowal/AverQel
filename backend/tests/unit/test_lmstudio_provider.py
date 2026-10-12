from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from app.providers.services.lmstudio_provider import LMStudioProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.types import ChatGenerateRequest, ChatGenerateResponse

pytestmark = pytest.mark.unit_no_db


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_lmstudio_provider_separates_chat_and_embedding_models_with_selection_only_metadata(
    monkeypatch,
) -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")
    fake_httpx = SimpleNamespace(
        get=lambda *args, **kwargs: _FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "qwen2.5-coder-7b-instruct",
                        "owned_by": "lmstudio",
                    },
                    {
                        "id": "text-embedding-nomic-embed-text-v1.5",
                        "owned_by": "lmstudio",
                    },
                ]
            },
        )
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    chat_models = provider.list_models()
    embedding_models = provider.list_embedding_models()

    assert len(chat_models) == 1
    assert chat_models[0].kind == "chat"
    assert chat_models[0].name == "qwen2.5-coder-7b-instruct"
    assert chat_models[0].capabilities["runtime"] == "lmstudio"
    assert chat_models[0].capabilities["selection_only"] is True
    assert chat_models[0].capabilities["install_supported"] is False
    assert chat_models[0].capabilities["supports_chat"] is True
    assert chat_models[0].capabilities["supports_embeddings"] is False

    assert len(embedding_models) == 1
    assert embedding_models[0].kind == "embedding"
    assert embedding_models[0].name == "text-embedding-nomic-embed-text-v1.5"
    assert embedding_models[0].capabilities["supports_chat"] is False
    assert embedding_models[0].capabilities["supports_embeddings"] is True


def test_lmstudio_provider_normalizes_root_base_url_to_v1(monkeypatch) -> None:
    monkeypatch.setattr("app.providers.services.url_resolution._running_in_docker", lambda: False)
    requested_urls: list[str] = []
    provider = LMStudioProvider().bind("http://localhost:1234")

    def fake_get(url: str, *args, **kwargs):
        requested_urls.append(url)
        if url.endswith("/api/v1/models"):
            return _FakeResponse(404, {})
        return _FakeResponse(200, {"data": [{"id": "qwen2.5-coder-7b-instruct"}]})

    fake_httpx = SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    provider.list_models()

    assert provider.base_url == "http://localhost:1234/v1"
    assert requested_urls[0] == "http://localhost:1234/api/v1/models"
    assert "http://localhost:1234/v1/models" in requested_urls


def test_lmstudio_provider_prefers_native_models_metadata_for_context_window(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.providers.services.url_resolution._running_in_docker", lambda: False)
    requested_urls: list[str] = []
    provider = LMStudioProvider().bind("http://localhost:1234/v1")

    def fake_get(url: str, *args, **kwargs):
        requested_urls.append(url)
        if url.endswith("/api/v1/models"):
            return _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "modelKey": "qwen2.5-14b-instruct",
                            "displayName": "Qwen2.5 14B Instruct",
                            "loaded_instances": [{"config": {"context_length": 131072}}],
                            "owned_by": "lmstudio",
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected fallback request: {url}")

    fake_httpx = SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    models = provider.list_models()

    assert requested_urls == ["http://localhost:1234/api/v1/models"]
    assert len(models) == 1
    assert models[0].name == "qwen2.5-14b-instruct"
    assert models[0].display_name == "Qwen2.5 14B Instruct"
    assert models[0].context_window == 131072
    assert models[0].capabilities["runtime"] == "lmstudio"


def test_lmstudio_provider_uses_advertised_reasoning_options_and_native_values() -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")
    model = provider._build_model_info(
        item={
            "key": "vendor/model-v2",
            "capabilities": {
                "reasoning": {
                    "allowed_options": ["off", "low", "ultra", "tier-5"],
                    "default": "low",
                }
            },
        },
        name="vendor/model-v2",
        kind="chat",
    )

    capabilities = model.capabilities
    assert capabilities["reasoning_capabilities_known"] is True
    assert capabilities["supported_reasoning_efforts"] == ["low", "ultra", "tier_5"]
    assert capabilities["supports_thinking_toggle"] is True
    assert capabilities["reasoning_effort_values"] == {
        "low": "low",
        "ultra": "ultra",
        "tier_5": "tier-5",
        "off": "off",
    }

    adapter = OpenAICompatibleProvider(provider_name="lmstudio")
    on_payload: dict[str, object] = {}
    on_request = ChatGenerateRequest(
        model=model.name,
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0,
        max_tokens=64,
        base_url="http://localhost:1234/v1",
        reasoning_enabled=True,
        reasoning_effort="ultra",
        metadata={
            "provider_type": "lmstudio",
            "reasoning_mode": "explicit",
            "model_reasoning_capabilities": capabilities,
        },
    )
    adapter._apply_discovered_reasoning_settings(on_payload, on_request, reasoning_enabled=True)

    off_payload: dict[str, object] = {}
    adapter._apply_discovered_reasoning_settings(
        off_payload,
        on_request,
        reasoning_enabled=False,
    )
    assert on_payload["reasoning_effort"] == "ultra"
    assert off_payload["reasoning_effort"] == "off"

    custom_payload: dict[str, object] = {}
    custom_request = ChatGenerateRequest(
        model=model.name,
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0,
        max_tokens=64,
        base_url="http://localhost:1234/v1",
        reasoning_enabled=True,
        reasoning_effort="tier_5",
        metadata={
            "provider_type": "lmstudio",
            "reasoning_mode": "explicit",
            "model_reasoning_capabilities": capabilities,
        },
    )
    adapter._apply_discovered_reasoning_settings(
        custom_payload, custom_request, reasoning_enabled=True
    )
    assert custom_payload["reasoning_effort"] == "tier-5"


def test_lmstudio_unknown_model_without_advertised_options_keeps_provider_default() -> None:
    model = LMStudioProvider()._build_model_info(
        item={"key": "vendor/unknown-model"},
        name="vendor/unknown-model",
        kind="chat",
    )

    assert model.capabilities["reasoning_capabilities_known"] is False
    assert model.capabilities["supported_reasoning_efforts"] == []


def test_lmstudio_provider_checks_chat_model_usability(monkeypatch) -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")

    def fake_post(url: str, *args, **kwargs):
        payload = kwargs.get("json", {})
        status_code = 200 if payload.get("model") == "mistralai/ministral-3-3b" else 400
        return _FakeResponse(status_code, {"ok": status_code == 200})

    fake_httpx = SimpleNamespace(post=fake_post)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    assert provider.chat_model_is_usable("mistralai/ministral-3-3b") is True
    assert provider.chat_model_is_usable("liquid/lfm2.5-1.2b") is False


def test_lmstudio_provider_falls_back_to_buffered_chunks_when_async_streaming_fails(
    monkeypatch,
) -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")
    request = ChatGenerateRequest(
        model="ministral",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.0,
        max_tokens=64,
        base_url="http://localhost:1234/v1",
        stream=True,
    )

    async def fake_stream_generate(self, request):
        if False:
            yield ""  # pragma: no cover
        raise RuntimeError("provider status 500")

    monkeypatch.setattr(OpenAICompatibleProvider, "stream_generate", fake_stream_generate)
    monkeypatch.setattr(
        LMStudioProvider,
        "generate",
        lambda self, request: ChatGenerateResponse(
            content="LM Studio fallback still streams readable text across multiple chunks."
        ),
    )

    async def collect() -> list[str]:
        chunks: list[str] = []
        async for chunk in provider.stream_generate(request):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect())

    assert "".join(chunks) == (
        "LM Studio fallback still streams readable text across multiple chunks."
    )
    assert len(chunks) > 1


def test_lmstudio_provider_falls_back_to_buffered_events_when_async_streaming_fails(
    monkeypatch,
) -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")
    request = ChatGenerateRequest(
        model="google/gemma-4-e4b",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.0,
        max_tokens=64,
        base_url="http://localhost:1234/v1",
        stream=True,
        reasoning_enabled=True,
    )

    async def fake_stream_generate_events(self, request):
        if False:
            yield {"type": "delta", "text": ""}  # pragma: no cover
        raise RuntimeError("provider status 500")

    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "stream_generate_events",
        fake_stream_generate_events,
    )
    monkeypatch.setattr(
        LMStudioProvider,
        "generate",
        lambda self, request: ChatGenerateResponse(
            content="Visible fallback answer.",
            thinking_content="Visible reasoning summary.",
            usage={"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9},
        ),
    )

    async def collect() -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        async for event in provider.stream_generate_events(request):
            events.append(event)
        return events

    events = asyncio.run(collect())

    assert events[0] == {"type": "stream_timing", "mode": "buffered"}
    assert {
        "type": "usage",
        "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9},
    } in events
    assert "".join(event["text"] for event in events if event["type"] == "thinking") == (
        "Visible reasoning summary."
    )
    assert "".join(event["text"] for event in events if event["type"] == "delta") == (
        "Visible fallback answer."
    )


@pytest.mark.unit_no_db
def test_lmstudio_does_not_restart_with_buffered_output_after_partial_stream(monkeypatch) -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")
    request = ChatGenerateRequest(
        model="qwen3",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.0,
        max_tokens=64,
        base_url="http://localhost:1234/v1",
    )
    fallback_calls = 0

    async def partial_then_fail(self, candidate):
        yield {"type": "delta", "text": "Already visible."}
        raise RuntimeError("provider stream closed")

    def unexpected_fallback(self, candidate):
        nonlocal fallback_calls
        fallback_calls += 1
        return ChatGenerateResponse(content="This must not be duplicated.")

    monkeypatch.setattr(OpenAICompatibleProvider, "stream_generate_events", partial_then_fail)
    monkeypatch.setattr(LMStudioProvider, "generate", unexpected_fallback)

    async def collect() -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        async for event in provider.stream_generate_events(request):
            events.append(event)
        return events

    with pytest.raises(RuntimeError, match="provider stream closed"):
        asyncio.run(collect())

    assert fallback_calls == 0


def test_lmstudio_normalizes_stream_event_request_base_url(monkeypatch) -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")
    request = ChatGenerateRequest(
        model="lfm2.5-8b-a1b",
        messages=[
            {"role": "system", "content": "Keep the answer concise."},
            {"role": "user", "content": "Say hello."},
        ],
        temperature=0.0,
        max_tokens=64,
        base_url="http://localhost:1234",
        stream=True,
    )
    attempted_base_urls: list[str] = []

    async def fake_stream_generate_events(self, candidate):
        attempted_base_urls.append(candidate.base_url)
        yield {"type": "delta", "text": "Hello."}

    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "stream_generate_events",
        fake_stream_generate_events,
    )

    async def collect() -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        async for event in provider.stream_generate_events(request):
            events.append(event)
        return events

    events = asyncio.run(collect())

    assert events == [{"type": "delta", "text": "Hello."}]
    assert attempted_base_urls == ["http://localhost:1234/v1"]


def test_lmstudio_normalizes_buffered_request_base_url(monkeypatch) -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")
    request = ChatGenerateRequest(
        model="lfm2.5-8b-a1b",
        messages=[{"role": "user", "content": "Say hello."}],
        temperature=0.0,
        max_tokens=64,
        base_url="http://localhost:1234",
    )
    attempted_base_urls: list[str] = []

    def fake_generate(self, candidate):
        attempted_base_urls.append(candidate.base_url)
        return ChatGenerateResponse(content="Hello.")

    monkeypatch.setattr(OpenAICompatibleProvider, "generate", fake_generate)

    response = provider.generate(request)

    assert response.content == "Hello."
    assert attempted_base_urls == ["http://localhost:1234/v1"]


def test_lmstudio_provider_falls_back_to_buffered_chunks_when_sync_streaming_fails(
    monkeypatch,
) -> None:
    provider = LMStudioProvider().bind("http://localhost:1234/v1")
    request = ChatGenerateRequest(
        model="ministral",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.0,
        max_tokens=64,
        base_url="http://localhost:1234/v1",
        stream=True,
    )

    def fake_stream_generate_sync(self, request):
        raise RuntimeError("provider status 500")
        yield ""  # pragma: no cover

    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "stream_generate_sync",
        fake_stream_generate_sync,
    )
    monkeypatch.setattr(
        LMStudioProvider,
        "generate",
        lambda self, request: ChatGenerateResponse(
            content="LM Studio sync fallback still streams readable text across multiple chunks."
        ),
    )

    chunks = list(provider.stream_generate_sync(request))

    assert "".join(chunks) == (
        "LM Studio sync fallback still streams readable text across multiple chunks."
    )
    assert len(chunks) > 1
