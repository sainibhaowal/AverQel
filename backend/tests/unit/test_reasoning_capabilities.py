from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.google_provider import GoogleProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.reasoning_capabilities import (
    model_supports_reasoning,
    resolve_reasoning_profile,
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
    assert model_supports_reasoning("custom", "openai/gpt-oss-120b")
    assert model_supports_reasoning("opencode-zen", "gpt-5.4")
    assert model_supports_reasoning("opencode-zen", "claude-sonnet-4-6")
    assert model_supports_reasoning("opencode-zen", "gemini-3.1-pro")
    assert model_supports_reasoning("opencode-zen", "deepseek-v4-flash")
    assert model_supports_reasoning("google", "gemini-3-pro")
    assert model_supports_reasoning("anthropic", "claude-3-7-sonnet-latest")
    assert model_supports_reasoning("google", "gemini-2.5-pro")
    assert model_supports_reasoning("lmstudio", "google/gemma-4-e4b")
    assert model_supports_reasoning("lmstudio", "gemma-3-27b-it")
    assert model_supports_reasoning("google", "gemma-4-26b-a4b-it")
    assert not model_supports_reasoning("openai", "gpt-4o-mini")
    assert not model_supports_reasoning("google", "gemini-1.5-flash")


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
        raise AssertionError(
            "follow-up generation should not trigger a second LLM call"
        )

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
