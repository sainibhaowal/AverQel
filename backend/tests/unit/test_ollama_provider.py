from __future__ import annotations

import sys
from types import SimpleNamespace

from app.providers.services.ollama_provider import OllamaProvider
from app.providers.services.types import ChatGenerateRequest


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_ollama_provider_lists_chat_and_embedding_models_with_runtime_metadata(
    monkeypatch,
) -> None:
    provider = OllamaProvider().bind("http://localhost:11434")
    fake_httpx = SimpleNamespace(
        get=lambda *args, **kwargs: _FakeResponse(
            200,
            {
                "models": [
                    {
                        "name": "llama3.2:3b",
                        "size": 2147483648,
                        "details": {
                            "family": "llama",
                            "parameter_size": "3B",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            },
        ),
        post=lambda *args, **kwargs: _FakeResponse(200, {"status": "success"}),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    chat_models = provider.list_models()
    embedding_models = provider.list_embedding_models()

    assert len(chat_models) == 1
    assert chat_models[0].kind == "chat"
    assert chat_models[0].capabilities["runtime"] == "ollama"
    assert chat_models[0].capabilities["install_supported"] is True
    assert chat_models[0].capabilities["supports_chat"] is True
    assert chat_models[0].capabilities["supports_embeddings"] is True
    assert chat_models[0].capabilities["family"] == "llama"

    assert len(embedding_models) == 1
    assert embedding_models[0].kind == "embedding"
    assert embedding_models[0].capabilities["supports_chat"] is False
    assert embedding_models[0].capabilities["supports_embeddings"] is True


def test_ollama_discovery_uses_per_model_thinking_metadata_and_compatible_effort_controls(
    monkeypatch,
) -> None:
    provider = OllamaProvider().bind("http://localhost:11434")

    def fake_post(url, *, json, **_kwargs):
        if url.endswith("/api/show") and json["model"] == "qwen3:8b":
            return _FakeResponse(
                200,
                {"thinking": {"values": [False, True], "default": True}},
            )
        if url.endswith("/api/show") and json["model"] == "gpt-oss:20b":
            return _FakeResponse(
                200,
                {"thinking": {"values": ["low", "ultra", "tier-5"], "default": "low"}},
            )
        return _FakeResponse(404, {})

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            get=lambda *_args, **_kwargs: _FakeResponse(
                200,
                {
                    "models": [
                        {"name": "qwen3:8b", "details": {"family": "qwen3"}},
                        {"name": "gpt-oss:20b", "details": {"family": "gpt-oss"}},
                        {"name": "llama3.2:3b", "details": {"family": "llama"}},
                    ]
                },
            ),
            post=fake_post,
        ),
    )

    models = {model.name: model for model in provider.list_models()}
    toggle = models["qwen3:8b"].capabilities
    named = models["gpt-oss:20b"].capabilities

    assert toggle["supported_reasoning_efforts"] == ["on"]
    assert toggle["supports_thinking_toggle"] is True
    assert toggle["request_controls_on"] == ["reasoning_effort"]
    assert toggle["request_controls_off"] == ["reasoning_effort_none"]
    assert toggle["reasoning_effort_values"] == {"on": "high"}
    assert named["supported_reasoning_efforts"] == ["low", "ultra", "tier_5"]
    assert named["reasoning_effort_values"] == {
        "low": "low",
        "ultra": "ultra",
        "tier_5": "tier-5",
    }
    assert "supported_reasoning_efforts" not in models["llama3.2:3b"].capabilities

    for enabled, effort, expected in ((True, "on", "high"), (False, None, "none")):
        request = ChatGenerateRequest(
            model="qwen3:8b",
            messages=[{"role": "user", "content": "Explain this."}],
            temperature=0,
            max_tokens=64,
            base_url="http://localhost:11434/v1",
            reasoning_enabled=enabled,
            reasoning_effort=effort,
            tool_choice="required",
            metadata={
                "provider_type": "ollama",
                "reasoning_mode": "explicit" if enabled else "off",
                "model_reasoning_capabilities": toggle,
            },
        )
        payload = {}
        provider._apply_reasoning_request_settings(payload, request)
        assert payload["reasoning_effort"] == expected

    custom_request = ChatGenerateRequest(
        model="gpt-oss:20b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0,
        max_tokens=64,
        base_url="http://localhost:11434/v1",
        reasoning_enabled=True,
        reasoning_effort="tier_5",
        metadata={
            "provider_type": "ollama",
            "reasoning_mode": "explicit",
            "model_reasoning_capabilities": named,
        },
    )
    custom_payload: dict[str, object] = {}
    provider._apply_reasoning_request_settings(custom_payload, custom_request)
    assert custom_payload["reasoning_effort"] == "tier-5"


def test_ollama_provider_pull_model_uses_official_api(monkeypatch) -> None:
    monkeypatch.setattr("app.providers.services.url_resolution._running_in_docker", lambda: False)
    provider = OllamaProvider().bind("http://localhost:11434")
    calls: list[tuple[str, dict[str, object]]] = []

    def _post(url: str, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(200, {"status": "success"})

    fake_httpx = SimpleNamespace(
        get=lambda *args, **kwargs: _FakeResponse(200, {"models": []}),
        post=_post,
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    result = provider.pull_model("nomic-embed-text")

    assert calls[0][0] == "http://localhost:11434/api/pull"
    assert calls[0][1]["json"] == {"name": "nomic-embed-text", "stream": False}
    assert result.metadata["pulled"] == "nomic-embed-text"
