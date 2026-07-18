from __future__ import annotations

import sys
from types import SimpleNamespace

from app.services.providers.anthropic_provider import AnthropicProvider
from app.services.providers.google_provider import GoogleProvider


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_anthropic_lists_models_from_single_api_key(monkeypatch) -> None:
    provider = AnthropicProvider(base_url="https://api.anthropic.com/v1", api_key="k")
    fake_httpx = SimpleNamespace(
        get=lambda *a, **k: _FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "claude-sonnet-4-20250514",
                        "display_name": "Claude Sonnet 4",
                        "input_token_limit": 200000,
                    },
                    {
                        "id": "claude-opus-4-20250514",
                        "display_name": "Claude Opus 4",
                        "input_token_limit": 200000,
                    },
                ]
            },
        )
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    models = provider.list_models()

    assert [model.name for model in models] == [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
    ]
    assert all(model.kind == "chat" for model in models)


def test_google_lists_chat_models_and_filters_non_chat_variants(monkeypatch) -> None:
    provider = GoogleProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="k",
    )
    fake_httpx = SimpleNamespace(
        get=lambda *a, **k: _FakeResponse(
            200,
            {
                "models": [
                    {
                        "name": "models/gemini-2.5-pro",
                        "baseModelId": "gemini-2.5-pro",
                        "displayName": "Gemini 2.5 Pro",
                        "inputTokenLimit": 1048576,
                        "supportedGenerationMethods": [
                            "generateContent",
                            "countTokens",
                        ],
                    },
                    {
                        "name": "models/gemini-2.5-flash",
                        "baseModelId": "gemini-2.5-flash",
                        "displayName": "Gemini 2.5 Flash",
                        "inputTokenLimit": 1048576,
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-2.5-pro-preview-tts",
                        "baseModelId": "gemini-2.5-pro-preview-tts",
                        "displayName": "Gemini 2.5 Pro TTS",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            },
        )
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    models = provider.list_models()

    assert [model.name for model in models] == ["gemini-2.5-pro", "gemini-2.5-flash"]
    assert all(model.kind == "chat" for model in models)
