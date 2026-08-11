from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from app.providers.services.lmstudio_provider import LMStudioProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.types import ChatGenerateRequest, ChatGenerateResponse


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
        ),
    )

    async def collect() -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        async for event in provider.stream_generate_events(request):
            events.append(event)
        return events

    events = asyncio.run(collect())

    assert events[0]["type"] == "thinking"
    assert "".join(event["text"] for event in events if event["type"] == "thinking") == (
        "Visible reasoning summary."
    )
    assert "".join(event["text"] for event in events if event["type"] == "delta") == (
        "Visible fallback answer."
    )


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
