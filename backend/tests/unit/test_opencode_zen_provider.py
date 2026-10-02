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


class _FakeConnectError(Exception):
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


def test_opencode_zen_omits_output_override_when_model_does_not_advertise_one() -> None:
    request = replace(_request("nemotron-3.5-lightning-free"), max_tokens=None)

    payload = OpenCodeZenProvider._build_responses_payload(request, stream=True)

    assert "max_output_tokens" not in payload


def test_opencode_zen_provider_lists_models_and_parses_context_windows(monkeypatch):
    called_urls: list[str] = []

    def _fake_get(url, *args, **kwargs):
        called_urls.append(url)
        return _FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "gpt-5.4",
                        "context_window": 131072,
                        "max_output_tokens": 32768,
                    },
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
    assert models[0].max_output_tokens == 32768
    assert models[1].context_window == 200000
    assert models[2].context_window == 200000
    assert models[3].context_window == 131072
    assert called_urls == ["https://opencode.ai/zen/v1/models"]


def test_opencode_zen_provider_retries_transient_model_discovery_failure(monkeypatch):
    attempts = 0

    def _fake_get(url, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _FakeConnectError("temporary DNS failure")
        return _FakeResponse(200, {"data": [{"id": "claude-sonnet-4-6"}]})

    fake_httpx = SimpleNamespace(
        get=_fake_get,
        ConnectError=_FakeConnectError,
        Timeout=_FakeTimeout,
        AsyncClient=_FakeAsyncClient,
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setattr(
        "app.providers.services.opencode_zen_provider.time.sleep", lambda _delay: None
    )

    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")
    models = provider.list_models()

    assert attempts == 2
    assert [model.name for model in models] == ["claude-sonnet-4-6"]


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
    assert provider.generate(_request("qwen3.6-plus")).content == "anthropic"

    assert calls == [
        ("anthropic", "claude-sonnet-4-6", "https://opencode.ai/zen/v1"),
        ("google", "gemini-3.1-pro", "https://opencode.ai/zen/v1"),
        ("anthropic", "qwen3.6-plus", "https://opencode.ai/zen/v1"),
    ]


def test_opencode_zen_free_pool_headers_include_session_id() -> None:
    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")

    headers = provider._headers(provider.api_key)

    assert headers["Authorization"] == "Bearer zen_test"
    assert headers["Content-Type"] == "application/json"
    assert headers["x-opencode-session"] == provider.session_id
    assert headers["X-Session-ID"] == provider.session_id
    assert headers["User-Agent"] == "opencode/1.18.31"
    assert headers["x-opencode-client"] == "desktop"
    assert headers["x-opencode-project"] == "global"
    assert OpenCodeZenProvider.OPENCODE_SESSION_RE.match(provider.session_id)
    assert OpenCodeZenProvider.OPENCODE_REQUEST_RE.match(headers["x-opencode-request"])
    assert len(provider.session_id) == 30


def test_opencode_zen_uses_conversation_session_header() -> None:
    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="zen_test")
    request = replace(
        _request("nemotron-3.5-lightning-free"),
        metadata={"conversation_id": "conversation-123"},
    )

    headers = provider._request_headers(request)

    # Free tier models upstream enforce Authorization: Bearer public
    assert headers["Authorization"] == "Bearer public"
    assert OpenCodeZenProvider.OPENCODE_SESSION_RE.match(headers["x-opencode-session"])
    assert headers["x-opencode-session"] == provider.translate_session_id("conversation-123")
    assert headers["X-Session-ID"] == headers["x-opencode-session"]
    assert headers["User-Agent"] == "opencode/1.18.31"


def test_opencode_zen_deterministic_session_translation() -> None:
    ses1 = OpenCodeZenProvider.translate_session_id("conv-abc-456")
    ses2 = OpenCodeZenProvider.translate_session_id("conv-abc-456")
    ses3 = OpenCodeZenProvider.translate_session_id("conv-xyz-789")

    assert ses1 == ses2
    assert ses1 != ses3
    assert OpenCodeZenProvider.OPENCODE_SESSION_RE.match(ses1)


def test_opencode_zen_user_agent_normalization() -> None:
    assert OpenCodeZenProvider._normalize_user_agent(None) == "opencode/1.18.31"
    assert OpenCodeZenProvider._normalize_user_agent("") == "opencode/1.18.31"
    assert OpenCodeZenProvider._normalize_user_agent("AverQel-DeepSpace/1.0") == "opencode/1.18.31"
    assert OpenCodeZenProvider._normalize_user_agent("opencode/1.15.0") == "opencode/1.18.31"
    assert OpenCodeZenProvider._normalize_user_agent("opencode/1.17.0") == "opencode/1.17.0"
    assert (
        OpenCodeZenProvider._normalize_user_agent("opencode/1.18.31 (desktop)")
        == "opencode/1.18.31 (desktop)"
    )
    assert OpenCodeZenProvider._normalize_user_agent("opencode/2.0.0") == "opencode/2.0.0"


def test_opencode_zen_free_model_detection_and_public_bearer() -> None:
    provider = OpenCodeZenProvider(base_url="https://opencode.ai/zen/v1", api_key="sk-real-key")

    # Paid model preserves user key
    paid_headers = provider._headers("sk-real-key", model="claude-sonnet-4-6")
    assert paid_headers["Authorization"] == "Bearer sk-real-key"

    # Free models enforce Bearer public
    free_headers1 = provider._headers("sk-real-key", model="muse-spark-1.3-contributor-free")
    assert free_headers1["Authorization"] == "Bearer public"

    free_headers2 = provider._headers(None, model="nemotron-3.5-lightning-free")
    assert free_headers2["Authorization"] == "Bearer public"


def test_opencode_zen_flattens_chat_tools_for_responses_api() -> None:
    request = replace(
        _request("muse-spark-1.2-contributor-free"),
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search the web.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    payload = OpenCodeZenProvider._build_responses_payload(request, stream=True)

    assert payload["tools"] == [
        {
            "type": "function",
            "name": "search",
            "description": "Search the web.",
            "parameters": {"type": "object", "properties": {}},
        }
    ]


def test_opencode_zen_routes_muse_and_grok_through_responses() -> None:
    assert OpenCodeZenProvider._model_family("muse-spark-1.2-contributor-free") == "responses"
    assert OpenCodeZenProvider._model_family("grok-build-0.1") == "responses"


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


def test_opencode_zen_converts_multi_turn_tool_calls_to_responses_input() -> None:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Find the project README."},
        {
            "role": "assistant",
            "content": "Searching for the README file...",
            "tool_calls": [
                {
                    "id": "fc_01a0af0f9f15708ca73f8d6b4f89be94",
                    "type": "function",
                    "function": {
                        "name": "find",
                        "arguments": '{"query": "README.md"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "fc_01a0af0f9f15708ca73f8d6b4f89be94",
            "content": "README.md found in /app",
        },
    ]

    instructions, input_items = OpenCodeZenProvider._convert_messages_to_input(messages)

    assert instructions == "You are a helpful assistant."
    assert len(input_items) == 4

    assert input_items[0] == {"role": "user", "content": "Find the project README."}
    assert input_items[1] == {
        "role": "assistant",
        "content": "Searching for the README file...",
    }
    assert input_items[2] == {
        "type": "function_call",
        "call_id": "fc_01a0af0f9f15708ca73f8d6b4f89be94",
        "name": "find",
        "arguments": '{"query": "README.md"}',
    }
    assert input_items[3] == {
        "type": "function_call_output",
        "call_id": "fc_01a0af0f9f15708ca73f8d6b4f89be94",
        "output": "README.md found in /app",
    }


def test_opencode_zen_converts_tool_calls_with_empty_assistant_content() -> None:
    # When the assistant emitted only a tool call and no text content
    messages = [
        {"role": "user", "content": "List files"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "list_files",
                        "arguments": {"path": "/"},
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": {"files": ["a", "b"]},
        },
    ]

    instructions, input_items = OpenCodeZenProvider._convert_messages_to_input(messages)

    assert instructions is None
    # Must NOT include empty assistant text, but MUST include function_call before function_call_output
    assert len(input_items) == 3
    assert input_items[0] == {"role": "user", "content": "List files"}
    assert input_items[1] == {
        "type": "function_call",
        "call_id": "call_123",
        "name": "list_files",
        "arguments": '{"path": "/"}',
    }
    assert input_items[2] == {
        "type": "function_call_output",
        "call_id": "call_123",
        "output": '{"files": ["a", "b"]}',
    }
