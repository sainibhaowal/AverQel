from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.google_provider import GoogleProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.opencode_zen_provider import OpenCodeZenProvider
from app.providers.services.types import ChatGenerateRequest, ChatGenerateResponse


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


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
                "event: response.output_text.delta",
                'data: {"delta":"Hello"}',
                "event: response.reasoning_summary_text.delta",
                'data: {"delta":"Plan first."}',
                "event: response.output_item.added",
                'data: {"item":{"type":"function_call","id":"call_1","name":"search"}}',
                "event: response.function_call_arguments.delta",
                'data: {"item_id":"call_1","delta":"{\\"query\\":\\"cats\\"}"}',
                "data: [DONE]",
            ]
        )


class _FakeTimeout:
    def __init__(self, *args, **kwargs):
        pass


def _request(model: str, *, reasoning_enabled: bool = False) -> ChatGenerateRequest:
    return ChatGenerateRequest(
        model=model,
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.1,
        max_tokens=64,
        base_url="https://opencode.ai/zen/v1",
        api_key="zen_test_key",
        reasoning_enabled=reasoning_enabled,
        metadata={"timeout_seconds": 8.0, "read_timeout_seconds": 30.0},
    )


def test_opencode_zen_omits_reasoning_payload_for_required_tools() -> None:
    request = replace(
        _request("nemotron-3-ultra-free", reasoning_enabled=True),
        tool_choice="required",
    )

    payload = OpenCodeZenProvider._build_responses_payload(request, stream=True)

    assert payload["tool_choice"] == "required"
    assert "reasoning" not in payload


def test_opencode_zen_provider_lists_models_and_parses_context_windows(monkeypatch):
    called_urls: list[str] = []

    def _fake_get(url, *args, **kwargs):
        called_urls.append(url)
        return _FakeResponse(
            200,
            {
                "data": [
                    {"id": "gpt-5.4", "context_window": 131072},
                    {
                        "id": "claude-sonnet-4-6",
                        "loaded_instances": [{"config": {"context_length": 200000}}],
                    },
                    {"id": "gemini-3.1-pro", "inputTokenLimit": 200000},
                    {"id": "qwen3.6-plus", "maxContextLength": 131072},
                ]
            },
        )

    fake_httpx = SimpleNamespace(get=_fake_get, Timeout=_FakeTimeout, AsyncClient=_FakeAsyncClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")
    models = provider.list_models()

    assert [model.name for model in models] == [
        "gpt-5.4",
        "claude-sonnet-4-6",
        "gemini-3.1-pro",
        "qwen3.6-plus",
    ]
    assert models[0].context_window == 131072
    assert models[1].context_window == 200000
    assert models[2].context_window == 200000
    assert models[3].context_window == 131072
    assert called_urls == ["https://opencode.ai/zen/v1/models"]


def test_opencode_zen_provider_parses_string_context_windows(monkeypatch):
    def _fake_get(url, *args, **kwargs):
        return _FakeResponse(
            200,
            {
                "data": [
                    {
                        "modelKey": "gpt-5.4",
                        "maxContextLength": "131072",
                    },
                    {
                        "name": "claude-sonnet-4-6",
                        "loaded_instances": [{"config": {"context_length": "200000"}}],
                    },
                ]
            },
        )

    fake_httpx = SimpleNamespace(get=_fake_get, Timeout=_FakeTimeout, AsyncClient=_FakeAsyncClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")
    models = provider.list_models()

    assert [model.name for model in models] == ["gpt-5.4", "claude-sonnet-4-6"]
    assert models[0].context_window == 131072
    assert models[1].context_window == 200000


def test_opencode_zen_provider_emits_live_context_for_deepseek_v4_flash(monkeypatch):
    def _fake_get(url, *args, **kwargs):
        return _FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "deepseek-v4-flash",
                        "contextWindow": 131072,
                    }
                ]
            },
        )

    fake_httpx = SimpleNamespace(get=_fake_get, Timeout=_FakeTimeout, AsyncClient=_FakeAsyncClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")
    models = provider.list_models()

    assert len(models) == 1
    assert models[0].name == "deepseek-v4-flash"
    assert models[0].context_window == 131072
    assert models[0].context_window_source == "live_model"


def test_opencode_zen_provider_uses_verified_docs_context_when_live_payload_missing(
    monkeypatch,
):
    def _fake_get(url, *args, **kwargs):
        return _FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "minimax-m2.5-free",
                        "owned_by": "opencode",
                    }
                ]
            },
        )

    fake_httpx = SimpleNamespace(get=_fake_get, Timeout=_FakeTimeout, AsyncClient=_FakeAsyncClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")
    models = provider.list_models()

    assert [model.name for model in models] == ["minimax-m2.5-free"]
    assert models[0].context_window == 204800
    assert models[0].context_window_source == "official_docs:minimax"


def test_opencode_zen_provider_routes_model_families(monkeypatch):
    calls: list[tuple[str, str, str | None]] = []

    def fake_anthropic_generate(self, request):
        calls.append(("anthropic", request.model, request.base_url))
        return ChatGenerateResponse(content="anthropic")

    def fake_google_generate(self, request):
        calls.append(("google", request.model, request.base_url))
        return ChatGenerateResponse(content="google")

    def fake_openai_generate(self, request):
        calls.append(("openai-compatible", request.model, request.base_url))
        return ChatGenerateResponse(content="openai-compatible")

    monkeypatch.setattr(AnthropicProvider, "generate", fake_anthropic_generate)
    monkeypatch.setattr(GoogleProvider, "generate", fake_google_generate)
    monkeypatch.setattr(OpenAICompatibleProvider, "generate", fake_openai_generate)

    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")

    assert provider.generate(_request("claude-sonnet-4-6")).content == "anthropic"
    assert provider.generate(_request("gemini-3.1-pro")).content == "google"
    assert provider.generate(_request("qwen3.6-plus")).content == "openai-compatible"

    assert calls == [
        ("anthropic", "claude-sonnet-4-6", "https://opencode.ai/zen/v1"),
        ("google", "gemini-3.1-pro", "https://opencode.ai/zen/v1"),
        ("openai-compatible", "qwen3.6-plus", "https://opencode.ai/zen/v1"),
    ]


@pytest.mark.asyncio
async def test_opencode_zen_provider_streams_responses_events(monkeypatch):
    fake_httpx = SimpleNamespace(
        Timeout=_FakeTimeout,
        AsyncClient=_FakeAsyncClient,
        post=lambda *a, **k: _FakeResponse(
            200,
            {
                "output_text": "Hello",
                "reasoning_content": "Plan first.",
                "output": [
                    {
                        "type": "function_call",
                        "id": "call_1",
                        "name": "search",
                        "arguments": '{"query":"cats"}',
                    }
                ],
            },
        ),
        get=lambda *a, **k: _FakeResponse(200, {"data": []}),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")
    # Capturing emitted reasoning must not depend on the request flag or model
    # capability hints. The provider already emitted the reasoning event.
    request = _request("gpt-5.4", reasoning_enabled=False)

    events = []
    async for event in provider.stream_generate_events(request):
        events.append(event)

    assert events[0] == {"type": "delta", "text": "Hello"}
    assert events[1] == {"type": "thinking", "text": "Plan first."}
    assert events[2]["type"] == "tool_calls_delta"
    assert events[2]["tool_calls"][0]["function"]["name"] == "search"
    assert events[2]["tool_calls"][0]["function"]["arguments"] == '{"query":"cats"}'
