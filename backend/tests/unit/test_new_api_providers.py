from __future__ import annotations

import asyncio
import base64
from threading import Event
from types import SimpleNamespace
from typing import Any

import pytest

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.manus_agent_provider import ManusAgentProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.provider_management_service import SUPPORTED_PROVIDER_CATALOG
from app.providers.services.reasoning_capabilities import supports_required_tool_choice
from app.providers.services.registry import (
    OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES,
    OPENAI_COMPATIBLE_PROVIDER_TYPES,
    PROVIDER_DEFAULT_BASE_URLS,
    ProviderRegistry,
)
from app.providers.services.types import ChatGenerateRequest, EmbeddingRequest

pytestmark = pytest.mark.unit_no_db


def _chat_request(
    provider_type: str,
    model: str,
    *,
    enabled: bool,
    effort: str | None = None,
) -> ChatGenerateRequest:
    return ChatGenerateRequest(
        model=model,
        messages=[{"role": "user", "content": "test"}],
        temperature=0.2,
        max_tokens=32,
        base_url="https://provider.example/v1",
        reasoning_enabled=enabled,
        reasoning_effort=effort,
        metadata={"provider_type": provider_type},
    )


def test_provider_catalog_routes_and_capabilities_are_wired() -> None:
    expected = {
        "moonshot": ("Moonshot AI (Kimi)", True, False, True),
        "zai": ("Z.AI (GLM)", True, False, False),
        "nvidia-nim": ("NVIDIA NIM", True, True, True),
        "manus": ("Manus Agent API", True, False, True),
    }
    for provider_type, (display_name, chat, embeddings, listing) in expected.items():
        catalog = SUPPORTED_PROVIDER_CATALOG[provider_type]
        assert catalog["display_name"] == display_name
        assert catalog["supports_chat"] is chat
        assert catalog["supports_embeddings"] is embeddings
        assert catalog["supports_model_listing"] is listing
        assert catalog["auth_modes"] == ["api_key"]
        assert catalog["supports_reranking"] is False
        assert catalog["supports_account_linking"] is False

    assert {"moonshot", "zai", "nvidia-nim"}.issubset(OPENAI_COMPATIBLE_PROVIDER_TYPES)
    assert "nvidia-nim" in OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES
    assert {"moonshot", "zai"}.isdisjoint(OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES)
    assert {provider: PROVIDER_DEFAULT_BASE_URLS[provider] for provider in expected} == {
        "moonshot": "https://api.moonshot.ai/v1",
        "zai": "https://api.z.ai/api/paas/v4",
        "nvidia-nim": "https://integrate.api.nvidia.com/v1",
        "manus": "https://api.manus.ai",
    }


def test_registry_uses_vendor_defaults_and_the_task_api_for_manus() -> None:
    for provider_type in ("moonshot", "zai", "nvidia-nim"):
        provider = ProviderRegistry._bind_chat_provider(
            provider_type,
            base_url=None,
            api_key="test-key",
        )
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.base_url == PROVIDER_DEFAULT_BASE_URLS[provider_type]
        assert provider.provider_name == provider_type

    manus = ProviderRegistry._bind_chat_provider("manus", base_url=None, api_key="test-key")
    assert isinstance(manus, ManusAgentProvider)
    assert manus.base_url == PROVIDER_DEFAULT_BASE_URLS["manus"]


def test_openai_compatible_route_defaults_match_documented_provider_surfaces() -> None:
    moonshot = OpenAICompatibleProvider(
        provider_name="moonshot", base_url=PROVIDER_DEFAULT_BASE_URLS["moonshot"]
    )
    zai = OpenAICompatibleProvider(provider_name="zai")
    nvidia = OpenAICompatibleProvider(provider_name="nvidia-nim", supports_embeddings=True)

    assert moonshot.endpoint_settings.chat_completions_path == "/chat/completions"
    assert moonshot.endpoint_settings.models_path == "/models"
    assert moonshot.endpoint_settings.embeddings_path is None
    assert zai.endpoint_settings.models_path is None
    assert zai.endpoint_settings.embeddings_path is None
    assert nvidia.endpoint_settings.models_path == "/models"
    assert nvidia.endpoint_settings.embeddings_path == "/embeddings"
    assert moonshot.supports_model_listing is True
    assert zai.supports_model_listing is False
    assert nvidia.supports_model_listing is True


def test_kimi_and_glm_reasoning_requests_use_their_native_fields() -> None:
    moonshot = OpenAICompatibleProvider(
        provider_name="moonshot",
        base_url=PROVIDER_DEFAULT_BASE_URLS["moonshot"],
    )
    payload: dict[str, Any] = {"model": "kimi-k3", "messages": []}
    moonshot._apply_reasoning_request_settings(
        payload,
        _chat_request("moonshot", "kimi-k3", enabled=True, effort="medium"),
    )
    assert payload["reasoning_effort"] == "high"
    assert "thinking" not in payload

    payload = {"model": "kimi-k3", "messages": []}
    moonshot._apply_reasoning_request_settings(
        payload, _chat_request("moonshot", "kimi-k3", enabled=False)
    )
    assert "reasoning_effort" not in payload
    assert "enable_thinking" not in payload

    payload = {"model": "kimi-k2.6", "messages": []}
    moonshot._apply_reasoning_request_settings(
        payload, _chat_request("moonshot", "kimi-k2.6", enabled=False)
    )
    assert payload["thinking"] == {"type": "disabled"}

    zai = OpenAICompatibleProvider(provider_name="zai")
    payload = {"model": "glm-5.2", "messages": []}
    zai._apply_reasoning_request_settings(payload, _chat_request("zai", "glm-5.2", enabled=False))
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["reasoning_effort"] == "none"
    assert "enable_thinking" not in payload

    payload = {"model": "glm-5.3", "messages": []}
    zai._apply_reasoning_request_settings(
        payload,
        _chat_request("zai", "glm-5.3", enabled=True, effort="extreme_high"),
    )
    assert payload["reasoning_effort"] == "max"
    assert "thinking" not in payload
    assert "enable_thinking" not in payload


def test_nvidia_reasoning_does_not_guess_fields_and_model_metadata_is_retained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleProvider(provider_name="nvidia-nim")
    payload: dict[str, Any] = {"model": "deepseek-ai/deepseek-v4-pro", "messages": []}
    provider._apply_reasoning_request_settings(
        payload,
        _chat_request("nvidia-nim", "deepseek-ai/deepseek-v4-pro", enabled=True, effort="high"),
    )
    assert set(payload) == {"model", "messages"}

    moonshot = OpenAICompatibleProvider(
        provider_name="moonshot",
        base_url=PROVIDER_DEFAULT_BASE_URLS["moonshot"],
    )
    monkeypatch.setattr(
        moonshot,
        "_fetch_model_listing_items",
        lambda: [
            {
                "id": "kimi-k3",
                "context_length": 200000,
                "supports_image_in": True,
                "supports_video_in": False,
                "supports_reasoning": True,
                "owned_by": "moonshotai",
            }
        ],
    )
    info = moonshot.list_models()[0]
    assert info.context_window == 200000
    assert info.capabilities["supports_image_in"] is True
    assert info.capabilities["supports_video_in"] is False
    assert info.capabilities["supports_reasoning"] is True
    assert info.capabilities["owned_by"] == "moonshotai"


def test_nvidia_embedding_requests_include_input_type_for_documented_families(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}

    def post(_url: str, *, json: dict[str, Any], **_kwargs: Any) -> Response:
        sent.update(json)
        return Response()

    provider = OpenAICompatibleProvider(
        provider_name="nvidia-nim",
        supports_embeddings=True,
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
    )
    monkeypatch.setattr(provider, "_httpx", lambda *_args: SimpleNamespace(post=post))
    response = provider.embed_many(
        EmbeddingRequest(
            texts=["what does this mean"],
            model="nvidia/nv-embedqa-e5-v5",
            batch_size=1,
            normalize=False,
            dimension=2,
            timeout_seconds=5,
            provider_name="nvidia-nim",
            metadata={"base_url": "https://integrate.api.nvidia.com/v1", "api_key": "test-key"},
            input_type="query",
        )
    )
    assert response.vectors == [[0.1, 0.2]]
    assert sent["input_type"] == "query"

    sent.clear()
    request = EmbeddingRequest(
        texts=["text"],
        model="baai/bge-m3",
        batch_size=1,
        normalize=False,
        dimension=2,
        timeout_seconds=5,
        provider_name="nvidia-nim",
        metadata={"base_url": "https://integrate.api.nvidia.com/v1", "api_key": "test-key"},
    )
    provider.embed_many(request)
    assert "input_type" not in sent


class _Response:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


def test_manus_creates_private_task_waits_for_completion_and_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[dict[str, Any]] = []
    get_calls = 0

    class HTTP:
        @staticmethod
        def post(_url: str, **kwargs: Any) -> _Response:
            posted.append(kwargs)
            return _Response(
                {
                    "ok": True,
                    "task_id": "task-123",
                    "task_url": "https://manus.im/app/task-123",
                }
            )

        @staticmethod
        def get(url: str, **_kwargs: Any) -> _Response:
            nonlocal get_calls
            if url.endswith("task.detail"):
                get_calls += 1
                task = (
                    {"status": "running"}
                    if get_calls == 1
                    else {
                        "status": "stopped",
                        "has_running_background_jobs": False,
                        "task_url": "https://manus.im/app/task-123",
                    }
                )
                return _Response({"ok": True, "task": task})
            return _Response(
                {
                    "ok": True,
                    "messages": [
                        {
                            "type": "assistant_message",
                            "assistant_message": {
                                "content": "Progress text",
                                "delivery_kind": "progress",
                            },
                        },
                        {
                            "type": "assistant_message",
                            "assistant_message": {
                                "content": "Completed answer",
                                "delivery_kind": "result",
                            },
                        },
                    ],
                }
            )

    monkeypatch.setattr("app.providers.services.manus_agent_provider.time.sleep", lambda _s: None)
    provider = ManusAgentProvider(api_key="manus-test-secret")
    monkeypatch.setattr(provider, "_httpx", lambda *_args: HTTP)
    response = provider.generate(
        ChatGenerateRequest(
            model="max-ultra",
            messages=[
                {"role": "system", "content": "Be precise."},
                {"role": "user", "content": "Explain this."},
            ],
            temperature=0.5,
            max_tokens=256,
            base_url="https://api.manus.ai",
            api_key="manus-test-secret",
            tools=[{"type": "function", "function": {"name": "test"}}],
            tool_choice="auto",
            metadata={"httpx_module": HTTP, "manus_task_timeout_seconds": 30},
        )
    )

    task_request = posted[0]["json"]
    assert response.content == "Completed answer"
    assert task_request["agent_profile"] == "max-ultra"
    assert task_request["interactive_mode"] is False
    assert task_request["share_visibility"] == "private"
    assert task_request["message"]["connectors"] == []
    prompt = task_request["message"]["content"][0]["text"]
    assert "SYSTEM:\n" in prompt and "USER:\n" in prompt
    assert "do not claim that an AverQel tool" in prompt


def test_manus_rejects_required_averqel_tools_and_lists_agent_profiles() -> None:
    provider = ManusAgentProvider(api_key="test-key")
    assert [model.name for model in provider.list_models()] == [
        "standard",
        "lite",
        "max",
        "max-medium",
        "max-high",
        "max-extra",
        "max-ultra",
    ]
    assert supports_required_tool_choice("manus", "standard") is False
    with pytest.raises(ProviderCapabilityError, match="cannot return an AverQel function call"):
        provider.generate(
            ChatGenerateRequest(
                model="standard",
                messages=[{"role": "user", "content": "run it"}],
                temperature=0.5,
                max_tokens=32,
                base_url="https://api.manus.ai",
                tool_choice="required",
            )
        )


def test_manus_uploads_images_without_forwarding_api_key_to_presigned_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_call: dict[str, Any] = {}
    put_call: dict[str, Any] = {}

    class HTTP:
        @staticmethod
        def post(url: str, **kwargs: Any) -> _Response:
            if url.endswith("file.upload"):
                upload_call.update(kwargs)
                return _Response(
                    {
                        "ok": True,
                        "file": {"id": "file-123", "status": "pending"},
                        "upload_url": "https://storage.example/presigned-upload",
                    }
                )
            return _Response(
                {"ok": True, "task_id": "task-image", "task_url": "https://manus.im/app/task-image"}
            )

        @staticmethod
        def put(url: str, **kwargs: Any) -> _Response:
            put_call.update({"url": url, **kwargs})
            return _Response({}, status_code=200)

        @staticmethod
        def get(url: str, **kwargs: Any) -> _Response:
            if url.endswith("file.detail"):
                return _Response({"ok": True, "file": {"id": "file-123", "status": "uploaded"}})
            if url.endswith("task.detail"):
                return _Response(
                    {
                        "ok": True,
                        "task": {"status": "stopped", "has_running_background_jobs": False},
                    }
                )
            return _Response(
                {
                    "ok": True,
                    "messages": [
                        {
                            "type": "assistant_message",
                            "assistant_message": {
                                "content": "Image reviewed.",
                                "delivery_kind": "result",
                            },
                        }
                    ],
                }
            )

    monkeypatch.setattr("app.providers.services.manus_agent_provider.time.sleep", lambda _s: None)
    provider = ManusAgentProvider(api_key="manus-test-secret")
    monkeypatch.setattr(provider, "_httpx", lambda *_args: HTTP)
    image = base64.b64encode(b"small test image").decode("ascii")
    response = provider.generate(
        ChatGenerateRequest(
            model="standard",
            messages=[{"role": "user", "content": "Describe this."}],
            temperature=0.2,
            max_tokens=128,
            base_url="https://api.manus.ai",
            images=[image],
        )
    )

    assert response.content == "Image reviewed."
    assert upload_call["headers"]["x-manus-api-key"] == "manus-test-secret"
    assert put_call["url"] == "https://storage.example/presigned-upload"
    assert put_call["content"] == b"small test image"
    assert put_call["headers"] == {"Content-Type": "image/jpeg"}
    assert "x-manus-api-key" not in put_call["headers"]


def test_manus_waiting_task_is_reported_without_automatic_action_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = 0

    class HTTP:
        @staticmethod
        def post(_url: str, **_kwargs: Any) -> _Response:
            nonlocal created
            created += 1
            return _Response(
                {
                    "ok": True,
                    "task_id": "task-waiting",
                    "task_url": "https://manus.im/app/task-waiting",
                }
            )

        @staticmethod
        def get(_url: str, **_kwargs: Any) -> _Response:
            return _Response({"ok": True, "task": {"status": "waiting"}})

    provider = ManusAgentProvider(api_key="test-key")
    monkeypatch.setattr(provider, "_httpx", lambda *_args: HTTP)
    with pytest.raises(
        ProviderRequestError, match="waiting for user input or an action decision"
    ) as exc:
        provider.generate(
            ChatGenerateRequest(
                model="standard",
                messages=[{"role": "user", "content": "Do this task."}],
                temperature=0.2,
                max_tokens=64,
                base_url="https://api.manus.ai",
            )
        )
    assert exc.value.status_code == 409
    assert "https://manus.im/app/task-waiting" in str(exc.value)
    assert getattr(exc.value, "no_retry", False) is True
    assert created == 1


def test_manus_task_timeout_is_not_retried_as_a_new_task(monkeypatch: pytest.MonkeyPatch) -> None:
    created = 0

    class HTTP:
        @staticmethod
        def post(_url: str, **_kwargs: Any) -> _Response:
            nonlocal created
            created += 1
            return _Response({"ok": True, "task_id": "task-running"})

    clock_values = iter((0.0, 31.0))
    monkeypatch.setattr(
        "app.providers.services.manus_agent_provider.time",
        SimpleNamespace(monotonic=lambda: next(clock_values)),
    )
    provider = ManusAgentProvider(api_key="test-key")
    monkeypatch.setattr(provider, "_httpx", lambda *_args: HTTP)

    with pytest.raises(
        ProviderRequestError, match="still running after AverQel's wait limit"
    ) as exc:
        provider.generate(
            ChatGenerateRequest(
                model="standard",
                messages=[{"role": "user", "content": "Do this task."}],
                temperature=0.2,
                max_tokens=64,
                base_url="https://api.manus.ai",
                metadata={"manus_task_timeout_seconds": 30},
            )
        )

    assert exc.value.status_code == 504
    assert getattr(exc.value, "no_retry", False) is True
    assert created == 1


@pytest.mark.asyncio
async def test_manus_stream_cancellation_stops_the_remote_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    task_detail_requested = Event()

    class HTTP:
        @staticmethod
        def post(url: str, **kwargs: Any) -> _Response:
            calls.append((url, kwargs.get("json", {})))
            if url.endswith("/task.create"):
                return _Response({"ok": True, "task_id": "task-running"})
            return _Response({"ok": True})

        @staticmethod
        def get(url: str, **_kwargs: Any) -> _Response:
            if url.endswith("/task.detail"):
                task_detail_requested.set()
                return _Response({"ok": True, "task": {"status": "running"}})
            return _Response({"ok": True, "messages": []})

    monkeypatch.setattr(
        "app.providers.services.manus_agent_provider._POLL_INTERVAL_SECONDS",
        0.01,
    )
    provider = ManusAgentProvider(api_key="test-key")
    monkeypatch.setattr(provider, "_httpx", lambda *_args: HTTP)
    request = ChatGenerateRequest(
        model="standard",
        messages=[{"role": "user", "content": "Do this task."}],
        temperature=0.2,
        max_tokens=64,
        base_url="https://api.manus.ai",
        metadata={"httpx_module": HTTP},
    )

    async def consume_stream() -> None:
        async for _event in provider.stream_generate_events(request):
            pass

    stream_task = asyncio.create_task(consume_stream())
    for _ in range(1000):
        if task_detail_requested.is_set():
            break
        await asyncio.sleep(0.001)
    assert task_detail_requested.is_set()

    stream_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stream_task

    assert [url.rsplit("/", maxsplit=1)[-1] for url, _ in calls] == [
        "task.create",
        "task.stop",
    ]
    assert calls[-1][1] == {"task_id": "task-running"}


def test_manus_health_check_verifies_api_key_without_creating_a_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class HTTP:
        @staticmethod
        def get(url: str, **_kwargs: Any) -> _Response:
            calls.append(url)
            return _Response({"ok": True, "data": []})

    monkeypatch.setattr(
        "app.providers.services.manus_agent_provider.importlib.import_module",
        lambda _name: HTTP,
    )
    result = ManusAgentProvider(api_key="test-key").health_check()

    assert result.status == "healthy"
    assert result.metadata == {"check": "task-list", "generation_request_sent": False}
    assert calls == ["https://api.manus.ai/v2/task.list"]
