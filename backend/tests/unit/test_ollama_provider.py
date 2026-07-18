from __future__ import annotations

import sys
from types import SimpleNamespace

from app.services.providers.ollama_provider import OllamaProvider


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


def test_ollama_provider_pull_model_uses_official_api(monkeypatch) -> None:
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
