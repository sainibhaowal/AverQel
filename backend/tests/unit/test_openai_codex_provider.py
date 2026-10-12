from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from app.providers.services import openai_codex_provider as codex_module
from app.providers.services.base import ProviderCapabilityError
from app.providers.services.openai_codex_config import (
    codex_reasoning_effort_values,
    codex_supported_reasoning_efforts,
    validate_codex_desktop_settings,
)
from app.providers.services.openai_codex_provider import (
    OpenAICodexProvider,
    OpenAIPlanUsageLimitError,
)
from app.providers.services.types import ChatGenerateRequest

pytestmark = pytest.mark.unit_no_db


def _request() -> ChatGenerateRequest:
    return ChatGenerateRequest(
        model="gpt-5-codex",
        messages=[
            {"role": "system", "content": "Follow the app's policy."},
            {"role": "user", "content": "Summarize this."},
        ],
        temperature=0.2,
        max_tokens=256,
        base_url="https://api.openai.com/v1",
        reasoning_enabled=True,
        reasoning_effort="high",
        metadata={"tenant_id": "tenant-test", "user_id": "user-test"},
    )


class _FakeRedis:
    def __init__(self, frames: list[dict[str, Any]]) -> None:
        self.frames = frames
        self.closed = False
        self.request_packet: dict[str, Any] | None = None

    def delete(self, _key: str) -> None:
        return None

    def eval(self, _script: str, _key_count: int, *_args: Any) -> int:
        if len(_args) >= 3 and isinstance(_args[2], str):
            try:
                self.request_packet = json.loads(_args[2])
            except json.JSONDecodeError:
                pass
        return 1

    def xread(self, _streams: dict[str, str], **_kwargs: Any) -> list[Any]:
        rows = [
            (str(index), {"frame": json.dumps(frame)})
            for index, frame in enumerate(self.frames, start=1)
        ]
        self.frames = []
        return [("response-key", rows)] if rows else []

    def exists(self, _key: str) -> int:
        return 1

    def expire(self, *_args: Any) -> None:
        return None

    def lrem(self, *_args: Any) -> int:
        return 0

    def close(self) -> None:
        self.closed = True


def _frame(kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": kind, "data": data or {}}


def _codex_provider(
    efforts: list[str] | None = None,
    effort_values: dict[str, str] | None = None,
) -> OpenAICodexProvider:
    model: dict[str, Any] = {"id": "gpt-5-codex", "name": "GPT-5 Codex"}
    if efforts is not None:
        model["supported_reasoning_efforts"] = efforts
    if effort_values is not None:
        model["reasoning_effort_values"] = effort_values
    return OpenAICodexProvider(
        metadata={
            "codex_desktop": {
                "account_id": "0123456789abcdef0123456789abcdef",
                "models": [model],
            }
        }
    )


@pytest.mark.parametrize(
    ("ui_effort", "api_effort"),
    [
        ("minimal", "minimal"),
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("very_high", "xhigh"),
        ("extreme_high", "max"),
        ("ultra", "ultra"),
    ],
)
def test_codex_reasoning_levels_map_to_distinct_supported_api_efforts(
    ui_effort: str, api_effort: str
) -> None:
    provider = _codex_provider(["minimal", "low", "medium", "high", "xhigh", "max", "ultra"])

    payload = provider._responses_payload(replace(_request(), reasoning_effort=ui_effort))

    assert payload["reasoning"] == {"effort": api_effort}


def test_codex_model_discovery_preserves_exact_reasoning_capabilities() -> None:
    provider = _codex_provider(["low", "high", "very_high"])

    model = provider.list_models()[0]

    assert model.capabilities["supported_reasoning_efforts"] == ["low", "high", "very_high"]
    assert model.capabilities["supports_reasoning"] is True


def test_codex_model_advertised_custom_effort_reaches_the_api_unchanged() -> None:
    provider = _codex_provider(["tier_5"], {"tier_5": "tier-five"})

    payload = provider._responses_payload(replace(_request(), reasoning_effort="tier_5"))

    assert payload["reasoning"] == {"effort": "tier-five"}
    assert codex_supported_reasoning_efforts(provider.codex_settings, "gpt-5-codex") == ("tier_5",)
    assert codex_reasoning_effort_values(provider.codex_settings, "gpt-5-codex") == {
        "tier_5": "tier-five"
    }


def test_codex_request_preserves_attached_image_mime_type() -> None:
    provider = _codex_provider()
    request = replace(_request(), images=["data:image/png;base64,iVBORw0KGgo="])

    payload = provider._responses_payload(request)

    assert payload["input"][-1] == {
        "role": "user",
        "content": [{"type": "input_image", "image_url": "data:image/png;base64,iVBORw0KGgo="}],
    }


def test_codex_explicit_empty_effort_catalog_is_not_treated_as_unknown() -> None:
    settings = {"models": [{"id": "gpt-5-codex", "supported_reasoning_efforts": []}]}

    assert codex_supported_reasoning_efforts(settings, "gpt-5-codex") == ()
    assert (
        codex_supported_reasoning_efforts({"models": [{"id": "gpt-5-codex"}]}, "gpt-5-codex")
        is None
    )


def test_codex_configuration_keeps_and_validates_model_effort_metadata() -> None:
    metadata = {
        "codex_desktop": {
            "account_id": "0123456789abcdef0123456789abcdef",
            "models": [
                {
                    "id": "gpt-5-codex",
                    "name": "GPT-5 Codex",
                    "supported_reasoning_efforts": ["low", "very_high", "extreme_high"],
                }
            ],
        }
    }

    normalized = validate_codex_desktop_settings(metadata, default_chat_model="gpt-5-codex")
    assert normalized["models"][0]["supported_reasoning_efforts"] == [
        "low",
        "very_high",
        "extreme_high",
    ]

    metadata["codex_desktop"]["models"][0]["supported_reasoning_efforts"] = ["ultra"]
    normalized = validate_codex_desktop_settings(metadata)
    assert normalized["models"][0]["supported_reasoning_efforts"] == ["ultra"]

    metadata["codex_desktop"]["models"][0]["supported_reasoning_efforts"] = ["invalid/value"]
    with pytest.raises(ValueError, match="reasoning metadata"):
        validate_codex_desktop_settings(metadata)


def test_codex_request_rejects_effort_not_advertised_by_selected_model() -> None:
    provider = _codex_provider(["low", "medium", "high"])

    with pytest.raises(ProviderCapabilityError, match="does not support"):
        provider._responses_payload(replace(_request(), reasoning_effort="very_high"))


def test_streams_text_and_tool_arguments_then_completes_without_exposing_account_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis(
        [
            _frame("event", {"type": "response.output_text.delta", "delta": "Ready."}),
            _frame(
                "event",
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {
                        "type": "function_call",
                        "id": "call-1",
                        "call_id": "call-1",
                        "name": "lookup",
                        "arguments": "",
                    },
                },
            ),
            _frame(
                "event",
                {
                    "type": "response.function_call_arguments.done",
                    "output_index": 0,
                    "arguments": '{"query":"weather"}',
                },
            ),
            _frame(
                "event",
                {
                    "type": "response.completed",
                    "response": {
                        "usage": {"input_tokens": 42, "output_tokens": 9, "total_tokens": 51}
                    },
                },
            ),
            _frame("closed"),
        ]
    )
    monkeypatch.setattr(
        codex_module, "get_settings", lambda: SimpleNamespace(redis_url="redis://isolated")
    )
    monkeypatch.setattr(
        codex_module.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: fake_redis,
    )
    provider = OpenAICodexProvider(
        metadata={
            "codex_desktop": {
                "account_id": "0123456789abcdef0123456789abcdef",
                "models": [{"id": "gpt-5-codex", "name": "GPT-5 Codex"}],
            }
        }
    )

    async def collect() -> list[dict[str, Any]]:
        return [event async for event in provider.stream_generate_events(_request())]

    events = asyncio.run(collect())

    assert {"type": "delta", "text": "Ready."} in events
    tool_call_events = [event for event in events if event.get("type") == "tool_calls_delta"]
    assert len(tool_call_events) == 2
    assert tool_call_events[0]["tool_calls"][0]["function"]["name"] == "lookup"
    assert tool_call_events[1]["tool_calls"][0]["function"]["arguments"] == '{"query":"weather"}'
    assert {
        "type": "usage",
        "usage": {"prompt_tokens": 42, "completion_tokens": 9, "total_tokens": 51},
    } in events
    assert fake_redis.request_packet is not None
    assert fake_redis.request_packet["params"]["account_id"] == "0123456789abcdef0123456789abcdef"
    assert fake_redis.request_packet["params"]["request"]["model"] == "gpt-5-codex"
    assert "tenant-test" not in json.dumps(fake_redis.request_packet)
    assert fake_redis.closed


def test_plan_usage_limit_error_is_returned_without_retrying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis(
        [
            _frame(
                "error",
                {
                    "message": "Usage limit reached.",
                    "code": "subscription_sharing_usage_limit_exceeded",
                    "http_status": 429,
                },
            )
        ]
    )
    monkeypatch.setattr(
        codex_module, "get_settings", lambda: SimpleNamespace(redis_url="redis://isolated")
    )
    monkeypatch.setattr(
        codex_module.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: fake_redis,
    )
    provider = OpenAICodexProvider(
        metadata={"codex_desktop": {"account_id": "0123456789abcdef0123456789abcdef"}}
    )

    async def collect() -> list[dict[str, Any]]:
        return [event async for event in provider.stream_generate_events(_request())]

    with pytest.raises(OpenAIPlanUsageLimitError) as error:
        asyncio.run(collect())

    assert error.value.status_code == 429
    assert error.value.no_retry is True
    assert fake_redis.closed
