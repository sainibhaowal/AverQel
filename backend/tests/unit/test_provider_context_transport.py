from __future__ import annotations

import sys
from types import SimpleNamespace

from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.types import ChatGenerateRequest


def _request(**overrides):
    values = {
        "model": "demo",
        "messages": [
            {"role": "system", "content": "stable policy"},
            {"role": "user", "content": "Hi"},
        ],
        "temperature": 0.1,
        "max_tokens": 32,
        "base_url": "http://mock/v1",
        "api_key": "key",
    }
    values.update(overrides)
    return ChatGenerateRequest(**values)


class _Response:
    status_code = 200

    def json(self):
        return {"content": [{"type": "text", "text": "ok"}], "usage": {}}


def test_anthropic_uses_documented_ephemeral_cache_control(monkeypatch) -> None:
    captured = {}

    def post(_url, **kwargs):
        captured.update(kwargs["json"])
        return _Response()

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=post))
    result = AnthropicProvider().generate(
        _request(prompt_cache_mode="anthropic_auto", prompt_cache_retention="5m")
    )

    assert result.content == "ok"
    assert captured["cache_control"] == {"type": "ephemeral"}


def test_openai_compatible_does_not_receive_anthropic_cache_fields(monkeypatch) -> None:
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def post(_url, **kwargs):
        captured.update(kwargs["json"])
        return Response()

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(post=post))
    OpenAICompatibleProvider().generate(
        _request(prompt_cache_mode="anthropic_auto", prompt_cache_key="must-not-leak")
    )

    assert "cache_control" not in captured
    assert "prompt_cache_key" not in captured
    assert "previous_response_id" not in captured
