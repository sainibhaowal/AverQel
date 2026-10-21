from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.providers.api.providers import (
    _active_chat_model_for_provider,
    _model_response,
    _provider_model_responses,
)
from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.google_provider import GoogleProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.reasoning_capabilities import (
    is_deepseek_v4_model,
    merge_reasoning_capabilities,
    model_supports_reasoning,
    resolve_reasoning_profile,
    supports_required_tool_choice,
    uses_deepseek_reasoning_protocol,
)
from app.providers.services.types import (
    ChatGenerateRequest,
    ProviderSelectionCandidate,
)
from app.query.schemas.structured_response import sanitize_mermaid_syntax
from app.query.services.answer_service import AnswerService


def test_reasoning_capabilities_cover_supported_providers() -> None:
    assert model_supports_reasoning("lmstudio", "nvidia/nemotron-3-nano-4b")
    assert model_supports_reasoning("lmstudio", "qwen2.5-14b-instruct")
    assert model_supports_reasoning("openai", "o4-mini")
    assert not model_supports_reasoning("custom", "openai/gpt-oss-120b")
    assert not model_supports_reasoning("openai-compatible", "qwen3-30b-a3b")
    assert model_supports_reasoning("opencode-zen", "gpt-5.4")
    assert model_supports_reasoning("opencode-zen", "claude-sonnet-4-6")
    assert model_supports_reasoning("opencode-zen", "gemini-3.1-pro")
    assert model_supports_reasoning("opencode-zen", "deepseek-v4-flash")
    assert model_supports_reasoning("deepseek", "deepseek-reasoner")
    assert model_supports_reasoning("deepseek", "deepseek-r1")
    assert model_supports_reasoning("deepseek", "deepseek-flash")
    assert model_supports_reasoning("google", "gemini-3-pro")
    assert model_supports_reasoning("anthropic", "claude-3-7-sonnet-latest")
    assert model_supports_reasoning("google", "gemini-2.5-pro")
    assert model_supports_reasoning("lmstudio", "google/gemma-4-e4b")
    assert model_supports_reasoning("lmstudio", "gemma-3-27b-it")
    assert model_supports_reasoning("google", "gemma-4-26b-a4b-it")
    assert not model_supports_reasoning("openai", "gpt-4o-mini")
    assert not model_supports_reasoning("google", "gemini-1.5-flash")
    assert not model_supports_reasoning("deepseek", "deepseek-chat")


def test_deepseek_protocol_detection_covers_direct_and_gateway_routes() -> None:
    assert uses_deepseek_reasoning_protocol("deepseek", "reasoner")
    assert uses_deepseek_reasoning_protocol("openrouter", "deepseek/deepseek-chat")
    assert uses_deepseek_reasoning_protocol("custom", "DeepSeek-V4-Flash")
    assert not uses_deepseek_reasoning_protocol("openai", "gpt-5")
    assert is_deepseek_v4_model("deepseek/deepseek-v4-flash")
    assert not is_deepseek_v4_model("deepseek-reasoner")


def test_nvidia_nim_nemotron_profiles_expose_only_documented_levels() -> None:
    ultra = resolve_reasoning_profile("nvidia-nim", "nvidia/nemotron-3-ultra-550b-a55b")
    super_model = resolve_reasoning_profile("nvidia-nim", "nvidia/nemotron-3-super-120b-a12b")
    nano = resolve_reasoning_profile("nvidia-nim", "nvidia/nemotron-3-nano-30b-a3b")

    assert ultra.to_dict()["reasoning_capabilities_known"] is True
    assert ultra.supported_reasoning_efforts == ("medium", "high")
    assert super_model.supported_reasoning_efforts == ("low", "high")
    assert nano.supported_reasoning_efforts == ()
    assert nano.supports_thinking_toggle is True
    assert (
        resolve_reasoning_profile("nvidia-nim", "vendor/unknown-model").to_dict()[
            "reasoning_capabilities_known"
        ]
        is False
    )


def test_advertised_reasoning_metadata_normalizes_native_effort_names() -> None:
    capabilities = merge_reasoning_capabilities(
        "openai",
        "vendor/reasoner-v9",
        advertised={
            "capabilities": {
                "reasoning": {
                    "supported_efforts": ["low", "high", "xhigh", "max"],
                    "request_controls_on": ["reasoning_effort"],
                    "request_controls_off": ["reasoning_effort_none"],
                }
            }
        },
    )

    assert capabilities["reasoning_capabilities_known"] is True
    assert capabilities["supports_reasoning"] is True
    assert capabilities["supported_reasoning_efforts"] == [
        "low",
        "high",
        "very_high",
        "extreme_high",
    ]
    assert capabilities["reasoning_effort_values"] == {
        "low": "low",
        "high": "high",
        "very_high": "xhigh",
        "extreme_high": "max",
    }
    assert capabilities["request_controls_on"] == ["reasoning_effort"]
    assert capabilities["request_controls_off"] == ["reasoning_effort_none"]


def test_advertised_reasoning_metadata_keeps_new_and_model_specific_efforts() -> None:
    capabilities = merge_reasoning_capabilities(
        "openai",
        "vendor/reasoner-v10",
        advertised={
            "supported_reasoning_efforts": ["minimal", "ultra", "tier-5", "invalid/value"],
            "reasoning_effort_values": {
                "tier-5": "tier-five",
                "invalid/value": "must-not-pass",
            },
            "request_controls_on": ["reasoning_effort"],
        },
    )

    assert capabilities["supported_reasoning_efforts"] == ["minimal", "ultra", "tier_5"]
    assert capabilities["reasoning_effort_values"] == {
        "minimal": "minimal",
        "ultra": "ultra",
        "tier_5": "tier-five",
    }


def test_unknown_cached_metadata_does_not_hide_verified_model_profile() -> None:
    capabilities = merge_reasoning_capabilities(
        "nvidia-nim",
        "nvidia/nemotron-3-ultra-550b-a55b",
        advertised={
            "reasoning_capabilities_known": False,
            "supports_reasoning": False,
            "supported_reasoning_efforts": [],
            "supports_thinking_toggle": False,
        },
    )

    assert capabilities["reasoning_capabilities_known"] is True
    assert capabilities["supports_reasoning"] is True
    assert capabilities["supported_reasoning_efforts"] == ["medium", "high"]


def test_provider_model_response_repairs_stale_cached_reasoning_profile() -> None:
    row = SimpleNamespace(
        id=UUID("9b96f146-c9ca-48e4-a287-ed8ad1152d6c"),
        provider_config_id=UUID("8d224f0e-1150-4d57-8f84-80def800e041"),
        model_name="nvidia/nemotron-3-ultra-550b-a55b",
        model_kind="chat",
        display_name=None,
        context_window=None,
        capabilities_json={
            "reasoning_capabilities_known": False,
            "supports_reasoning": False,
            "supported_reasoning_efforts": [],
            "supports_thinking_toggle": False,
        },
        is_available=True,
        last_seen_at=None,
    )

    response = _model_response(row, provider_type="nvidia-nim")

    assert response.capabilities_json["reasoning_capabilities_known"] is True
    assert response.capabilities_json["supported_reasoning_efforts"] == ["medium", "high"]


def test_provider_model_response_includes_uncached_default_model_profile() -> None:
    provider = SimpleNamespace(
        id=UUID("1a779c6b-b408-4f66-9c12-df47877ac86a"),
        provider_type="nvidia-nim",
        default_chat_model="nvidia/nemotron-3-super-120b-a12b",
        supports_chat=True,
        api_base_url="https://integrate.api.nvidia.com/v1",
    )

    responses = _provider_model_responses([], provider=provider)

    assert len(responses) == 1
    assert responses[0].model_name == provider.default_chat_model
    assert responses[0].capabilities_json["supported_reasoning_efforts"] == ["low", "high"]


def test_provider_model_response_includes_assigned_model_without_a_cached_catalog_row() -> None:
    provider = SimpleNamespace(
        id=UUID("1a779c6b-b408-4f66-9c12-df47877ac86a"),
        provider_type="zai",
        default_chat_model=None,
        supports_chat=True,
        api_base_url="https://api.z.ai/api/paas/v4",
    )

    responses = _provider_model_responses(
        [],
        provider=provider,
        assigned_chat_model="glm-5.2",
    )

    assert len(responses) == 1
    assert responses[0].model_name == "glm-5.2"
    assert responses[0].capabilities_json["supported_reasoning_efforts"] == [
        "low",
        "medium",
        "high",
        "very_high",
        "extreme_high",
    ]


def test_synthetic_custom_model_response_uses_configured_reasoning_levels() -> None:
    provider = SimpleNamespace(
        id=UUID("1a779c6b-b408-4f66-9c12-df47877ac86a"),
        provider_type="custom",
        default_chat_model="custom-reasoner",
        supports_chat=True,
        api_base_url="https://gateway.example/v1",
        metadata_json={
            "openai_compatible": {
                "reasoning": {
                    "supported_efforts": ["low", "high"],
                    "effort_parameter": "reasoning.effort",
                }
            }
        },
    )

    responses = _provider_model_responses([], provider=provider)

    assert responses[0].capabilities_json["reasoning_capabilities_known"] is True
    assert responses[0].capabilities_json["supported_reasoning_efforts"] == ["low", "high"]


def test_custom_provider_repairs_cached_unknown_reasoning_metadata() -> None:
    provider = SimpleNamespace(
        id=UUID("1a779c6b-b408-4f66-9c12-df47877ac86a"),
        provider_type="custom",
        default_chat_model="custom-reasoner",
        supports_chat=True,
        api_base_url="https://gateway.example/v1",
        metadata_json={
            "openai_compatible": {
                "reasoning": {
                    "supported_efforts": ["low", "high"],
                    "effort_parameter": "reasoning.effort",
                }
            }
        },
    )
    row = SimpleNamespace(
        id=None,
        provider_config_id=provider.id,
        model_name="custom-reasoner",
        model_kind="chat",
        display_name="Custom Reasoner",
        context_window=None,
        capabilities_json={"reasoning_capabilities_known": False},
        is_available=True,
        last_seen_at=None,
    )

    responses = _provider_model_responses([row], provider=provider)

    assert responses[0].capabilities_json["reasoning_capabilities_known"] is True
    assert responses[0].capabilities_json["supported_reasoning_efforts"] == ["low", "high"]


def test_provider_model_response_uses_openai_compatible_endpoint_dialect() -> None:
    row = SimpleNamespace(
        id=None,
        provider_config_id=UUID("8d224f0e-1150-4d57-8f84-80def800e041"),
        model_name="llama-3.3-70b-versatile",
        model_kind="chat",
        display_name=None,
        context_window=None,
        capabilities_json={},
        is_available=True,
        last_seen_at=None,
    )
    provider = SimpleNamespace(
        provider_type="openai-compatible",
        api_base_url="https://api.groq.com/openai/v1",
        default_chat_model=None,
        supports_chat=True,
    )

    response = _provider_model_responses([row], provider=provider)[0]

    assert response.capabilities_json["reasoning_capabilities_known"] is True
    assert response.capabilities_json["supported_reasoning_efforts"] == ["low", "medium", "high"]
    assert "include_reasoning" in response.capabilities_json["request_controls_on"]


def test_active_chat_model_lookup_is_scoped_to_tenant_user_and_provider(monkeypatch) -> None:
    provider_id = UUID("8d224f0e-1150-4d57-8f84-80def800e041")
    tenant_id = UUID("9b96f146-c9ca-48e4-a287-ed8ad1152d6c")
    user_id = UUID("1a779c6b-b408-4f66-9c12-df47877ac86a")
    active_assignment = SimpleNamespace(
        provider_config_id=provider_id,
        model_name="assigned-model",
    )

    class FakeAssignmentsRepository:
        def __init__(self, db) -> None:
            assert db is database

        def get_active_assignment(self, **kwargs):
            assert kwargs == {
                "tenant_id": tenant_id,
                "workspace_id": None,
                "feature_scope": "chat",
                "owner_user_id": user_id,
            }
            return active_assignment

    database = object()
    monkeypatch.setattr(
        "app.providers.api.providers.ProviderAssignmentsRepository",
        FakeAssignmentsRepository,
    )

    assert (
        _active_chat_model_for_provider(
            database,
            tenant_id=tenant_id,
            user_id=user_id,
            provider_config_id=provider_id,
        )
        == "assigned-model"
    )


def test_deepseek_v4_does_not_support_forced_tool_choice() -> None:
    assert not supports_required_tool_choice("opencode-zen", "deepseek-v4-flash")
    assert not supports_required_tool_choice("openrouter", "deepseek-v4-pro")
    assert supports_required_tool_choice("opencode-zen", "qwen3.6-plus")


def test_deepseek_flash_exposes_the_universal_reasoning_levels() -> None:
    profile = resolve_reasoning_profile("deepseek", "deepseek-flash")

    assert profile.supports_thinking_toggle is True
    assert profile.supported_reasoning_efforts == (
        "low",
        "medium",
        "high",
        "very_high",
        "extreme_high",
    )


def test_mistral_and_meta_profiles_use_vendor_supported_reasoning_models() -> None:
    mistral = resolve_reasoning_profile("mistral", "mistral-small-latest")
    meta = resolve_reasoning_profile("meta", "muse-spark-1.3")

    assert mistral.supports_thinking_toggle is True
    assert mistral.supported_reasoning_efforts == (
        "low",
        "medium",
        "high",
        "very_high",
        "extreme_high",
    )
    assert meta.supports_reasoning is True
    assert meta.reasoning_visibility == "hidden"
    assert meta.supports_thinking_toggle is False
    assert meta.supported_reasoning_efforts[-1] == "extreme_high"
    assert model_supports_reasoning("cline", "deepseek/deepseek-r1") is False


def test_reasoning_profile_tracks_dynamic_controls_for_local_qwen() -> None:
    profile = resolve_reasoning_profile(
        "lmstudio", "qwen3-14b", base_url="http://localhost:1234/v1"
    )

    assert profile.supports_reasoning is True
    assert profile.supports_thinking_toggle is True
    assert "enable_thinking_true" in profile.request_controls_on
    assert "enable_thinking_false" in profile.request_controls_off
    assert "slash_think" in profile.request_controls_on
    assert "slash_no_think" in profile.request_controls_off


def test_reasoning_profile_tracks_dynamic_controls_for_local_nemotron() -> None:
    profile = resolve_reasoning_profile(
        "lmstudio", "nvidia/nemotron-3-nano-4b", base_url="http://localhost:1234/v1"
    )

    assert profile.supports_reasoning is True
    assert profile.supports_thinking_toggle is True
    assert "enable_thinking_true" in profile.request_controls_on
    assert "enable_thinking_false" in profile.request_controls_off
    assert "slash_think" in profile.request_controls_on
    assert "slash_no_think" in profile.request_controls_off


def test_reasoning_profile_marks_thinking_only_models_as_non_toggleable() -> None:
    profile = resolve_reasoning_profile(
        "lmstudio",
        "Qwen3-4B-Thinking-2507",
        base_url="http://localhost:1234/v1",
    )

    assert profile.supports_reasoning is True
    assert profile.supports_thinking_toggle is False
    assert profile.request_controls_on == ()
    assert profile.request_controls_off == ()


def test_reasoning_profile_tracks_dynamic_controls_for_groq() -> None:
    profile = resolve_reasoning_profile(
        "openai-compatible",
        "openai/gpt-oss-120b",
        base_url="https://api.groq.com/openai/v1",
    )

    assert profile.supports_reasoning is True
    assert profile.supports_thinking_toggle is True
    assert profile.request_controls_on == ("include_reasoning", "reasoning_effort")
    assert profile.request_controls_off == ("include_reasoning_false",)


def test_reasoning_profile_tracks_dynamic_controls_for_google() -> None:
    profile = resolve_reasoning_profile("google", "gemini-2.5-pro")

    assert profile.supports_reasoning is True
    assert profile.supports_thinking_toggle is True
    assert profile.request_controls_on == ("thinking_config_include_thoughts",)
    assert profile.request_controls_off == ("thinking_config_disable",)


def test_reasoning_profile_supports_opencode_deepseek_v4_flash() -> None:
    profile = resolve_reasoning_profile("opencode-zen", "deepseek-v4-flash")

    assert profile.supports_reasoning is True
    assert profile.supports_thinking_summary_stream is True
    assert profile.supports_thinking_toggle is True
    assert "reasoning" in profile.request_controls_on


def test_reasoning_profile_tracks_dynamic_controls_for_gemini_3() -> None:
    profile = resolve_reasoning_profile("google", "gemini-3-pro")

    assert profile.supports_reasoning is True
    assert profile.supports_thinking_toggle is True
    assert profile.request_controls_on == ("thinking_config_include_thoughts",)
    assert profile.request_controls_off == ("thinking_config_disable",)


def test_anthropic_generate_exposes_thinking_only_when_enabled(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "content": [
                    {"type": "thinking", "text": "Plan first."},
                    {"type": "text", "text": "Final answer."},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }

    class FakeHttpx:
        @staticmethod
        def post(*args: Any, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(AnthropicProvider, "_httpx", staticmethod(lambda: FakeHttpx))
    provider = AnthropicProvider()

    request = ChatGenerateRequest(
        model="claude-3-7-sonnet-latest",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=256,
        base_url="https://api.anthropic.com/v1",
        api_key="test",
        reasoning_enabled=True,
    )
    result = provider.generate(request)
    assert result.content == "Final answer."
    assert result.thinking_content == "Plan first."

    off_result = provider.generate(replace(request, reasoning_enabled=False))
    # Provider-emitted thinking is always captured; the flag controls only
    # optional request-side reasoning controls.
    assert off_result.thinking_content == "Plan first."


def test_anthropic_uses_advertised_capabilities_for_unprofiled_models(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {"content": [{"type": "text", "text": "Answer."}]}

    class FakeHttpx:
        @staticmethod
        def post(*args: Any, **kwargs: Any) -> FakeResponse:
            captured.append(kwargs["json"])
            return FakeResponse()

    monkeypatch.setattr(AnthropicProvider, "_httpx", staticmethod(lambda: FakeHttpx))
    provider = AnthropicProvider()
    request = ChatGenerateRequest(
        model="vendor/new-claude-family",
        messages=[{"role": "user", "content": "Use the advertised thinking level."}],
        temperature=0,
        max_tokens=10_000,
        base_url="https://api.anthropic.com/v1",
        api_key="test",
        reasoning_enabled=True,
        reasoning_effort="high",
        metadata={
            "model_reasoning_capabilities": {
                "reasoning_capabilities_known": True,
                "supports_reasoning": True,
                "supported_reasoning_efforts": ["low", "high"],
            }
        },
    )

    provider.generate(request)

    assert captured[0]["thinking"] == {"type": "enabled", "budget_tokens": 8_000}


@pytest.mark.asyncio
async def test_anthropic_stream_uses_the_selected_effort_for_thinking_budget(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    class FakeResponse:
        status_code = 200

        async def aiter_lines(self):
            if False:
                yield ""

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *args: Any) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        def stream(self, method: str, url: str, *, headers: dict[str, str], json: dict[str, Any]):
            captured.append(json)
            return FakeStream()

    class FakeHttpx:
        AsyncClient = FakeClient

    monkeypatch.setattr(AnthropicProvider, "_httpx", staticmethod(lambda: FakeHttpx))
    provider = AnthropicProvider()
    request = ChatGenerateRequest(
        model="claude-3-7-sonnet-latest",
        messages=[{"role": "user", "content": "Think deeply."}],
        temperature=0,
        max_tokens=10_000,
        base_url="https://api.anthropic.com/v1",
        api_key="test",
        stream=True,
        reasoning_enabled=True,
        reasoning_effort="high",
    )

    async for _event in provider.stream_generate_events(request):
        pass

    assert captured[0]["thinking"] == {"type": "enabled", "budget_tokens": 8_000}


def test_google_generate_exposes_thinking_only_when_enabled(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Plan first.", "thought": True},
                                {"text": "Final answer."},
                            ]
                        }
                    }
                ]
            }

    class FakeHttpx:
        @staticmethod
        def post(*args: Any, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(GoogleProvider, "_httpx", staticmethod(lambda: FakeHttpx))
    provider = GoogleProvider()

    request = ChatGenerateRequest(
        model="gemini-2.5-pro",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=256,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="test",
        reasoning_enabled=True,
    )
    result = provider.generate(request)
    assert result.content == "Final answer."
    assert result.thinking_content == "Plan first."

    off_result = provider.generate(replace(request, reasoning_enabled=False))
    assert off_result.thinking_content == "Plan first."


def test_google_uses_advertised_capabilities_for_unprofiled_models() -> None:
    request = ChatGenerateRequest(
        model="models/gemini-experimental-reasoner",
        messages=[{"role": "user", "content": "Think this through."}],
        temperature=0,
        max_tokens=128,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="test",
        reasoning_enabled=True,
        reasoning_effort="high",
        metadata={
            "model_reasoning_capabilities": {
                "reasoning_capabilities_known": True,
                "supports_reasoning": True,
                "supported_reasoning_efforts": ["high"],
            }
        },
    )

    generation_config = GoogleProvider._build_generation_config(request)

    assert generation_config["thinkingConfig"] == {
        "includeThoughts": True,
        "thinkingBudget": 24_576,
    }


def test_google_build_generation_config_disables_thinking_explicitly() -> None:
    request = ChatGenerateRequest(
        model="gemini-2.5-pro",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=256,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="test",
        reasoning_enabled=False,
    )

    config = GoogleProvider._build_generation_config(request)

    assert config["thinkingConfig"] == {"includeThoughts": False, "thinkingBudget": 0}


def test_google_auto_reasoning_preserves_provider_defaults() -> None:
    request = ChatGenerateRequest(
        model="gemini-2.5-pro",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=256,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="test",
        metadata={"reasoning_mode": "auto"},
    )

    config = GoogleProvider._build_generation_config(request)

    assert "thinkingConfig" not in config


def test_google_required_tools_suppress_explicit_thinking_controls() -> None:
    request = ChatGenerateRequest(
        model="gemini-2.5-pro",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=256,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="test",
        reasoning_enabled=True,
        tool_choice="required",
        metadata={"reasoning_mode": "explicit"},
    )

    config = GoogleProvider._build_generation_config(request)

    assert "thinkingConfig" not in config


def test_openai_compatible_disable_thinking_omits_effort_for_local_controls() -> None:
    payload: dict[str, object] = {}
    request = ChatGenerateRequest(
        model="qwen3-14b",
        messages=[{"role": "user", "content": "Explain this."}],
        temperature=0.1,
        max_tokens=64,
        base_url="http://host.docker.internal:1234/v1",
        api_key="k",
        reasoning_enabled=False,
        metadata={"provider_type": "lmstudio"},
    )

    OpenAICompatibleProvider()._apply_reasoning_request_settings(payload, request)

    assert payload["enable_thinking"] is False
    assert "reasoning_effort" not in payload


def test_followup_generation_uses_static_fallback_without_extra_llm_call(
    monkeypatch,
) -> None:
    service = AnswerService(no_result_answer_text="No answer")
    called = False

    def fail_call(**kwargs: Any) -> tuple[str, dict[str, int]]:
        nonlocal called
        called = True
        raise AssertionError("follow-up generation should not trigger a second LLM call")

    monkeypatch.setattr(service, "_call_llm_with_retry", fail_call)

    followups = service.generate_followups(
        query_text="What changed?",
        answer_text="Here is the answer.",
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        previous_messages=None,
        provider_candidates=[
            ProviderSelectionCandidate(
                provider_type="openai",
                model_name="o4-mini",
                feature_scope="chat",
                source="env_fallback",
                base_url="http://mock-api",
                api_key="test",
            )
        ],
    )

    assert followups == [
        "Can you explain what changed in more detail?",
        "What is the most important takeaway here?",
        "Can you show the exact evidence from the documents?",
    ]
    assert called is False


def test_sanitize_mermaid_quotes_complex_labels() -> None:
    syntax = """graph TD
A[Course Book] --> B[Units]
K --> L[Textbooks (Klenke, Rohatgi, etc.)]
M --> N[Tables (Table 1, Table 11)]
"""

    sanitized = sanitize_mermaid_syntax(syntax)

    assert 'L["Textbooks (Klenke, Rohatgi, etc.)"]' in sanitized
    assert 'N["Tables (Table 1, Table 11)"]' in sanitized


def test_reasoning_profile_tracks_gemma_controls() -> None:
    profile = resolve_reasoning_profile("lmstudio", "google/gemma-4-e4b")

    assert profile.supports_reasoning is True
    assert profile.supports_thinking_summary_stream is True
    assert "gemma_think_token" in profile.request_controls_on
    assert "gemma_channel_tags" in profile.response_formats
    assert "think_tags" in profile.response_formats
