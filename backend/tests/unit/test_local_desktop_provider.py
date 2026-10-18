from __future__ import annotations

from unittest.mock import Mock

from app.providers.services.local_desktop_provider import LocalDesktopRuntimeProvider
from app.providers.services.types import ChatGenerateRequest


def test_chat_payload_is_openai_compatible_and_omits_secrets() -> None:
    request = ChatGenerateRequest(
        model="llama3.2",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=128,
        base_url="http://127.0.0.1:11434",
        api_key="must-not-be-forwarded",
        stream=True,
        tools=[{"type": "function", "function": {"name": "ping"}}],
        tool_choice="auto",
        reasoning_effort="high",
    )
    payload = LocalDesktopRuntimeProvider._chat_payload(request)
    assert payload["stream"] is True
    assert payload["model"] == "llama3.2"
    assert payload["tools"] == request.tools
    assert payload["tool_choice"] == "auto"
    assert "api_key" not in payload
    assert "base_url" not in payload


def test_health_check_reports_desktop_runtime_result(monkeypatch) -> None:
    provider = LocalDesktopRuntimeProvider(
        provider_type="ollama",
        tenant_id="tenant",
        owner_user_id="user",
        base_url="http://127.0.0.1:11434",
    )
    monkeypatch.setattr(provider, "_rpc", Mock(return_value={"provider": "ollama"}))
    result = provider.health_check()
    assert result.status == "healthy"
    assert result.metadata["runtime"] == "electron"
    assert result.metadata["provider"] == "ollama"
