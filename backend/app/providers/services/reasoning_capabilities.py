from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

_GEMMA_HINTS: Final[tuple[str, ...]] = (
    "gemma",
    "gemma2",
    "gemma-2",
    "gemma-3",
    "gemma3",
    "gemma-4",
    "gemma4",
    "gemma-4b",
    "gemma-4-27b",
    "gemma-4-9b",
    "gemma-4-2b",
)

_OPENAI_COMPATIBLE_HINTS: Final[tuple[str, ...]] = (
    "o1",
    "o1-preview",
    "o1-mini",
    "o3",
    "o3-mini",
    "o4",
    "gpt-5",
    "gpt-oss",
    "gpt-4.1-reasoning",
    "gpt-4o-reasoning",
    "codex",
    "code",
    "reason",
    "reasoning",
    "thinking",
    "deepseek-r1",
    "deepseek-r",
    "deepseek-reasoner",
    "deepseek-flash",
    "deepseek-v4",
    "deepseek-v3",
    "deepseek-v2.5",
    "qwq",
    "qwen",
    "qwen2",
    "qwen2.5",
    "qwen3",
    "qwen-2.5",
    "qwen-3",
    "kimi",
    "kimi-k2",
    "kimi-k2-5",
    "kimi-k2-pro",
    "moonshot",
    "nemotron",
    "nemotron-4",
    "nemotron-340b",
    "llama-3.1",
    "llama-3.2",
    "llama-3.3",
    "llama-4",
    "mistral-large",
    "mistral-reasoning",
    *_GEMMA_HINTS,
)

_OPENAI_REASONING_PAYLOAD_HINTS: Final[tuple[str, ...]] = (
    "o1",
    "o1-preview",
    "o1-mini",
    "o3",
    "o3-mini",
    "o4",
    "gpt-oss",
    "gpt-4.1-reasoning",
    "gpt-4o-reasoning",
)

_SLASH_THINK_HINTS: Final[tuple[str, ...]] = (
    "qwen",
    "qwq",
    "qwen2",
    "qwen2.5",
    "qwen3",
    "nemotron",
    "nemotron-4",
    "llama-3.1",
    "llama-3.2",
    "llama-3.3",
    "llama-4",
)

_ENABLE_THINKING_HINTS: Final[tuple[str, ...]] = (
    "qwen",
    "qwen2",
    "qwen2.5",
    "qwen3",
    "qwq",
    "deepseek-r1",
    "deepseek-r",
    "deepseek-flash",
    "deepseek-v4",
    "deepseek-v3",
    "kimi",
    "kimi-k2",
    "kimi-k2-5",
    "kimi-k2-pro",
    "moonshot",
    "minimax",
    "nemotron",
    "nemotron-4",
    "nemotron-340b",
    "reason",
    "reasoning",
    "thinking",
    "codex",
    "code",
    "llama-3.1",
    "llama-3.2",
    "llama-3.3",
    "llama-4",
    "mistral-large",
    "mistral-reasoning",
)

_THINK_TAG_HINTS: Final[tuple[str, ...]] = (
    "deepseek-r1",
    "deepseek-r",
    "deepseek-flash",
    "deepseek-v4",
    "deepseek-v3",
    "qwq",
    "qwen",
    "qwen2",
    "qwen2.5",
    "qwen3",
    "reason",
    "reasoning",
    "thinking",
    "kimi",
    "kimi-k2",
    "kimi-k2-5",
    "kimi-k2-pro",
    "moonshot",
    "nemotron",
    "nemotron-4",
    "nemotron-340b",
    "codex",
    "code",
    "llama-3.1",
    "llama-3.2",
    "llama-3.3",
    "llama-4",
    "mistral-large",
    "mistral-reasoning",
    *_GEMMA_HINTS,
)

_THINKING_ONLY_HINTS: Final[tuple[str, ...]] = (
    "thinking-2507",
    "-thinking",
    "_thinking",
)

_ANTHROPIC_HINTS: Final[tuple[str, ...]] = (
    "claude-3.7",
    "claude-3-7",
    "claude-3.7-sonnet",
    "claude-3.7-opus",
    "claude-4",
    "claude-4-sonnet",
    "claude-4-opus",
    "sonnet-4",
    "opus-4",
    "thinking",
    "claude-code",
    "claude-code-4",
)

_GOOGLE_HINTS: Final[tuple[str, ...]] = (
    "gemini-2.5",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-thinking",
    "gemini-3",
    "gemini-3-pro",
    "gemini-3-flash",
    "gemini-3-flash-thinking",
    "thinking",
    *_GEMMA_HINTS,
)

_LOCAL_REASONING_PROVIDER_TYPES: Final[set[str]] = {
    "lmstudio",
    "ollama",
    "vllm",
}

_REASONING_EFFORT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]{0,19}$")
_REASONING_EFFORT_ALIASES: Final[dict[str, str]] = {
    "xhigh": "very_high",
    "max": "extreme_high",
}
_REASONING_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "supports_reasoning",
        "reasoning_capabilities_known",
        "reasoning_visibility",
        "supports_thinking_summary_stream",
        "supported_reasoning_efforts",
        "default_reasoning_effort",
        "supports_thinking_toggle",
        "request_controls_on",
        "request_controls_off",
        "reasoning_effort_values",
    }
)
_REASONING_REQUEST_CONTROLS: Final[frozenset[str]] = frozenset(
    {
        "reasoning",
        "reasoning_effort",
        "thinking_enabled",
        "thinking_disabled",
        "enable_thinking_true",
        "enable_thinking_false",
        "include_reasoning",
        "include_reasoning_false",
        "reasoning_effort_none",
        "omit_reasoning",
        "omit_reasoning_effort",
        "gemma_think_token",
        "slash_think",
        "slash_no_think",
    }
)


def uses_deepseek_reasoning_protocol(provider_type: str, model_name: str) -> bool:
    """Identify DeepSeek even when it is routed through a compatible gateway."""

    return (
        str(provider_type or "").strip().casefold() == "deepseek"
        or "deepseek" in str(model_name or "").casefold()
    )


def is_deepseek_v4_model(model_name: str) -> bool:
    """DeepSeek V4 requires non-null assistant content on tool-call messages."""

    normalized = str(model_name or "").casefold()
    return "deepseek-v4" in normalized or "deepseek_v4" in normalized


def normalize_reasoning_effort_value(value: object) -> str | None:
    """Normalize a provider-advertised option into a safe UI/API identifier.

    Provider catalogs are the authority for whether an option is selectable.
    This helper only limits the identifier alphabet and maps legacy aliases;
    it does not claim that a provider supports any value.
    """
    if not isinstance(value, str):
        return None
    native = value.strip().casefold()
    if not _REASONING_EFFORT_PATTERN.fullmatch(native):
        return None
    canonical = _REASONING_EFFORT_ALIASES.get(native, native.replace("-", "_"))
    return canonical if _REASONING_EFFORT_PATTERN.fullmatch(canonical) else None


_OPENAI_COMPATIBLE_PROVIDER_TYPES: Final[set[str]] = {
    "lmstudio",
    "openai",
    "deepseek",
    "opencode-zen",
    "custom",
    "openai-compatible",
    "groq",
    "groq-openai-compatible",
    "meta",
    "moonshot",
    "together",
    "fireworks",
    "mistral",
    "zai",
    "nvidia-nim",
    "perplexity",
    "openrouter",
    "vllm",
}


def _matches_any(model_name: str | None, hints: tuple[str, ...]) -> bool:
    """Check if model name matches any of the given hints with intelligent pattern matching."""
    if not model_name:
        return False
    lowered = model_name.lower()

    # Direct substring match
    for hint in hints:
        if hint in lowered:
            return True

    # Pattern-based matching for reasoning models
    # Match patterns like "model-reasoning", "model-thinking", "model-r1", etc.
    reasoning_patterns = [
        "-reasoning",
        "-thinking",
        "-r1",
        "-r2",
        "-r3",
        "_reasoning",
        "_thinking",
        "_r1",
        "_r2",
        "_r3",
        "-coder",
        "-code",
        "-codex",
        "-pro-reasoning",
        "-flash-thinking",
    ]

    for pattern in reasoning_patterns:
        if pattern in lowered:
            return True

    # Match version patterns for reasoning models
    # e.g., "o1", "o3", "gpt-4.1", "claude-3.7"
    if any(
        lowered[char].isdigit() and lowered[char - 1 : char + 2] in ["o1", "o3", "o4"]
        for char in range(1, len(lowered) - 1)
    ):
        return True

    return False


@dataclass(frozen=True, slots=True)
class ReasoningProfile:
    supports_reasoning: bool = False
    reasoning_capabilities_known: bool = False
    reasoning_visibility: str = "hidden"
    supports_thinking_summary_stream: bool = False
    supported_reasoning_efforts: tuple[str, ...] = ()
    default_reasoning_effort: str | None = None
    reasoning_effort_values: tuple[tuple[str, str], ...] = ()
    supports_thinking_toggle: bool = False
    request_controls_on: tuple[str, ...] = ()
    request_controls_off: tuple[str, ...] = ()
    response_formats: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "supports_reasoning": self.supports_reasoning,
            "reasoning_capabilities_known": (
                self.reasoning_capabilities_known
                or self.supports_reasoning
                or self.supports_thinking_toggle
                or bool(self.supported_reasoning_efforts)
            ),
            "reasoning_visibility": self.reasoning_visibility,
            "supports_thinking_summary_stream": self.supports_thinking_summary_stream,
            "supported_reasoning_efforts": list(self.supported_reasoning_efforts),
            "supports_thinking_toggle": self.supports_thinking_toggle,
            "request_controls_on": list(self.request_controls_on),
            "request_controls_off": list(self.request_controls_off),
            "response_formats": list(self.response_formats),
        }
        if self.default_reasoning_effort:
            result["default_reasoning_effort"] = self.default_reasoning_effort
        if self.reasoning_effort_values:
            result["reasoning_effort_values"] = dict(self.reasoning_effort_values)
        return result


def uses_groq_reasoning_api(
    provider_type: str | None,
    model_name: str | None,
    *,
    base_url: str | None = None,
) -> bool:
    if not _matches_any(model_name, _OPENAI_COMPATIBLE_HINTS):
        return False
    normalized_provider = (provider_type or "").lower()
    normalized_base_url = (base_url or "").lower()
    return (
        normalized_provider in {"groq", "groq-openai-compatible"}
        or "api.groq.com" in normalized_base_url
    )


def uses_enable_thinking_controls(provider_type: str | None, model_name: str | None) -> bool:
    return (provider_type or "").lower() in _LOCAL_REASONING_PROVIDER_TYPES and _matches_any(
        model_name,
        _ENABLE_THINKING_HINTS,
    )


def uses_slash_think_controls(provider_type: str | None, model_name: str | None) -> bool:
    return (provider_type or "").lower() in _LOCAL_REASONING_PROVIDER_TYPES and _matches_any(
        model_name,
        _SLASH_THINK_HINTS,
    )


def uses_openai_reasoning_payload(provider_type: str | None, model_name: str | None) -> bool:
    return (provider_type or "").lower() in _OPENAI_COMPATIBLE_PROVIDER_TYPES and _matches_any(
        model_name,
        _OPENAI_REASONING_PAYLOAD_HINTS,
    )


def uses_think_tags(provider_type: str | None, model_name: str | None) -> bool:
    return (provider_type or "").lower() in _OPENAI_COMPATIBLE_PROVIDER_TYPES and _matches_any(
        model_name,
        _THINK_TAG_HINTS,
    )


def uses_gemma_think_trigger(model_name: str | None) -> bool:
    return _matches_any(model_name, _GEMMA_HINTS)


def resolve_reasoning_profile(
    provider_type: str | None,
    model_name: str | None,
    *,
    base_url: str | None = None,
) -> ReasoningProfile:
    provider = (provider_type or "").lower()
    # A model name alone cannot establish the request dialect of an arbitrary
    # compatible endpoint. Custom endpoint controls come from its explicit
    # provider metadata and are attached by the OpenAI-compatible adapter.
    if provider == "custom":
        return ReasoningProfile()
    if provider == "openai-compatible" and not uses_groq_reasoning_api(
        provider_type, model_name, base_url=base_url
    ):
        return ReasoningProfile()
    if provider == "moonshot":
        if _matches_any(model_name, ("kimi-k3",)):
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=("low", "high", "extreme_high"),
                supports_thinking_toggle=False,
                request_controls_on=("reasoning_effort",),
                request_controls_off=(),
                response_formats=("reasoning_content",),
            )
        if _matches_any(model_name, ("kimi-k2.7-code", "kimi-k2.6")):
            always_on = "kimi-k2.7-code" in (model_name or "").lower()
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=(),
                supports_thinking_toggle=not always_on,
                request_controls_on=() if always_on else ("thinking_enabled",),
                request_controls_off=() if always_on else ("thinking_disabled",),
                response_formats=("reasoning_content",),
            )
        return ReasoningProfile()
    if provider == "zai":
        lowered_model = (model_name or "").lower()
        if "glm-5.3" in lowered_model:
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=("low", "high", "extreme_high"),
                supports_thinking_toggle=False,
                request_controls_on=("reasoning_effort",),
                request_controls_off=(),
                response_formats=("reasoning_content",),
            )
        if "glm-5.2" in lowered_model:
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=(
                    "low",
                    "medium",
                    "high",
                    "very_high",
                    "extreme_high",
                ),
                supports_thinking_toggle=True,
                request_controls_on=("thinking_enabled", "reasoning_effort"),
                request_controls_off=("thinking_disabled", "reasoning_effort_none"),
                response_formats=("reasoning_content",),
            )
        if _matches_any(model_name, ("glm-5.1", "glm-5", "glm-4.7", "glm-4.6", "glm-4.5")):
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=(),
                supports_thinking_toggle=True,
                request_controls_on=("thinking_enabled",),
                request_controls_off=("thinking_disabled",),
                response_formats=("reasoning_content",),
            )
        return ReasoningProfile()
    if provider == "larprouter":
        lowered_model = (model_name or "").casefold().replace("_", "-")
        if "deepseek-v4.1-flash" in lowered_model or "deepseek-v4-flash" in lowered_model:
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=("low", "high", "extreme_high"),
                default_reasoning_effort="high",
                reasoning_effort_values=(
                    ("low", "low"),
                    ("high", "high"),
                    ("extreme_high", "max"),
                ),
                supports_thinking_toggle=True,
                request_controls_on=("thinking_enabled", "reasoning_effort"),
                request_controls_off=("thinking_disabled",),
                response_formats=("reasoning_content",),
            )
        if "glm-5.3" in lowered_model:
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=("low", "high", "extreme_high"),
                default_reasoning_effort="extreme_high",
                reasoning_effort_values=(
                    ("low", "low"),
                    ("high", "high"),
                    ("extreme_high", "max"),
                ),
                supports_thinking_toggle=False,
                request_controls_on=("reasoning_effort",),
                response_formats=("reasoning_content",),
            )
        return ReasoningProfile()
    if provider == "nvidia-nim":
        lowered_model = (model_name or "").lower().replace("_", "-")
        if "nemotron-3-ultra" in lowered_model:
            # NVIDIA documents `none`, `medium`, and `high` for this family.
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=("medium", "high"),
                supports_thinking_toggle=True,
                request_controls_on=("reasoning_effort",),
                request_controls_off=("reasoning_effort_none",),
                response_formats=("reasoning_content",),
            )
        if "nemotron-3-super" in lowered_model:
            # NVIDIA documents `none`, `low`, and `high` for this family.
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=("low", "high"),
                supports_thinking_toggle=True,
                request_controls_on=("reasoning_effort",),
                request_controls_off=("reasoning_effort_none",),
                response_formats=("reasoning_content",),
            )
        if "nemotron-3-nano-30b-a3b" in lowered_model:
            # The NIM API documents a chat-template thinking switch, not effort
            # levels, for this model.
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=(),
                supports_thinking_toggle=True,
                request_controls_on=("enable_thinking_true",),
                request_controls_off=("enable_thinking_false",),
                response_formats=("reasoning_content",),
            )
        # NIM hosts models from multiple vendors; model-name matching cannot
        # establish one safe shared reasoning request dialect.
        return ReasoningProfile()
    if provider == "meta":
        if _matches_any(model_name, ("muse-spark",)):
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="hidden",
                supports_thinking_summary_stream=False,
                supported_reasoning_efforts=(
                    "low",
                    "medium",
                    "high",
                    "very_high",
                    "extreme_high",
                ),
                supports_thinking_toggle=False,
                request_controls_on=("reasoning_effort",),
                request_controls_off=("omit_reasoning_effort",),
                response_formats=(),
            )
        return ReasoningProfile()
    if provider == "mistral":
        if _matches_any(model_name, ("zai-glm-5-3",)):
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=("low", "high", "extreme_high"),
                supports_thinking_toggle=False,
                request_controls_on=("reasoning_effort",),
                request_controls_off=("omit_reasoning_effort",),
                response_formats=("reasoning_content",),
            )
        if _matches_any(
            model_name,
            (
                "mistral-small",
                "mistral-medium",
                "mistral-large",
                "magistral",
                "mistral-reasoning",
            ),
        ):
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=(
                    "low",
                    "medium",
                    "high",
                    "very_high",
                    "extreme_high",
                ),
                supports_thinking_toggle=True,
                request_controls_on=("reasoning_effort",),
                request_controls_off=("reasoning_effort_none",),
                response_formats=("reasoning_content",),
            )
        return ReasoningProfile()
    if provider == "deepseek" and _matches_any(model_name, _OPENAI_COMPATIBLE_HINTS):
        return ReasoningProfile(
            supports_reasoning=True,
            reasoning_visibility="provider_exposed",
            supports_thinking_summary_stream=True,
            supported_reasoning_efforts=(
                "low",
                "medium",
                "high",
                "very_high",
                "extreme_high",
            ),
            supports_thinking_toggle=True,
            request_controls_on=("thinking_enabled", "reasoning_effort"),
            request_controls_off=("thinking_disabled",),
            response_formats=("reasoning_content",),
        )
    if provider in {"google", "opencode-zen"} and uses_gemma_think_trigger(model_name):
        return ReasoningProfile(
            supports_reasoning=True,
            reasoning_visibility="provider_exposed",
            supports_thinking_summary_stream=True,
            supported_reasoning_efforts=("low", "medium", "high"),
            supports_thinking_toggle=True,
            request_controls_on=("gemma_think_token",),
            request_controls_off=(),
            response_formats=("reasoning_content", "gemma_channel_tags", "think_tags"),
        )
    if provider in {"google", "opencode-zen"} and _matches_any(model_name, _GOOGLE_HINTS):
        return ReasoningProfile(
            supports_reasoning=True,
            reasoning_visibility="provider_exposed",
            supports_thinking_summary_stream=True,
            supported_reasoning_efforts=("low", "medium", "high"),
            supports_thinking_toggle=True,
            request_controls_on=("thinking_config_include_thoughts",),
            request_controls_off=("thinking_config_disable",),
            response_formats=("thought_parts",),
        )
    if provider in {"anthropic", "opencode-zen"} and _matches_any(model_name, _ANTHROPIC_HINTS):
        return ReasoningProfile(
            supports_reasoning=True,
            reasoning_visibility="provider_exposed",
            supports_thinking_summary_stream=True,
            supported_reasoning_efforts=("low", "medium", "high"),
            supports_thinking_toggle=True,
            request_controls_on=("anthropic_thinking_block",),
            request_controls_off=("omit_thinking_block",),
            response_formats=("thinking_blocks",),
        )
    if provider == "opencode-zen" and _matches_any(
        model_name,
        _ENABLE_THINKING_HINTS + _OPENAI_COMPATIBLE_HINTS + _THINKING_ONLY_HINTS,
    ):
        response_formats = ["reasoning_content"]
        if uses_think_tags(provider_type, model_name):
            response_formats.append("think_tags")
        return ReasoningProfile(
            supports_reasoning=True,
            reasoning_visibility="provider_exposed",
            supports_thinking_summary_stream=True,
            supported_reasoning_efforts=("low", "medium", "high"),
            supports_thinking_toggle=True,
            request_controls_on=("reasoning", "reasoning_effort"),
            request_controls_off=("omit_reasoning",),
            response_formats=tuple(response_formats),
        )
    if provider in _OPENAI_COMPATIBLE_PROVIDER_TYPES and _matches_any(
        model_name,
        _OPENAI_COMPATIBLE_HINTS,
    ):
        if _matches_any(model_name, _THINKING_ONLY_HINTS):
            return ReasoningProfile(
                supports_reasoning=True,
                reasoning_visibility="provider_exposed",
                supports_thinking_summary_stream=True,
                supported_reasoning_efforts=("low", "medium", "high"),
                supports_thinking_toggle=False,
                request_controls_on=(),
                request_controls_off=(),
                response_formats=("reasoning_content", "think_tags"),
            )
        request_controls_on: list[str] = []
        request_controls_off: list[str] = []
        response_formats = ["reasoning_content"]

        if uses_groq_reasoning_api(provider_type, model_name, base_url=base_url):
            request_controls_on.extend(["include_reasoning", "reasoning_effort"])
            request_controls_off.append("include_reasoning_false")
        else:
            if uses_openai_reasoning_payload(provider_type, model_name):
                request_controls_on.extend(["reasoning", "reasoning_effort"])
                request_controls_off.append("omit_reasoning")
            if uses_enable_thinking_controls(provider_type, model_name):
                request_controls_on.append("enable_thinking_true")
                request_controls_off.append("enable_thinking_false")
            if uses_slash_think_controls(provider_type, model_name):
                request_controls_on.append("slash_think")
                request_controls_off.append("slash_no_think")

        if uses_think_tags(provider_type, model_name):
            response_formats.append("think_tags")
        if uses_gemma_think_trigger(model_name):
            request_controls_on.append("gemma_think_token")
            response_formats.append("gemma_channel_tags")

        return ReasoningProfile(
            supports_reasoning=True,
            reasoning_visibility="provider_exposed",
            supports_thinking_summary_stream=True,
            supported_reasoning_efforts=("low", "medium", "high"),
            supports_thinking_toggle=bool(request_controls_on or request_controls_off),
            request_controls_on=tuple(dict.fromkeys(request_controls_on)),
            request_controls_off=tuple(dict.fromkeys(request_controls_off)),
            response_formats=tuple(dict.fromkeys(response_formats)),
        )
    return ReasoningProfile()


def model_supports_reasoning(provider_type: str | None, model_name: str | None) -> bool:
    return resolve_reasoning_profile(provider_type, model_name).supports_reasoning


def supports_required_tool_choice(provider_type: str | None, model_name: str | None) -> bool:
    """Return whether a model can accept a forced tool choice.

    DeepSeek V4 models are thinking-first models at the upstream API and
    reject ``tool_choice=required`` (the rejection is independent of whether
    AverQel sends an explicit reasoning option).  ``auto`` still permits the
    model to call the supplied tools and is the only compatible negotiation.
    """
    if (provider_type or "").lower() == "manus":
        # Manus API v2 accepts agent tasks, not an OpenAI function-tool choice.
        return False
    normalized = (model_name or "").lower().replace("_", "-")
    return "deepseek-v4" not in normalized


def reasoning_capabilities(
    provider_type: str | None,
    model_name: str | None,
    *,
    base_url: str | None = None,
) -> dict[str, object]:
    return resolve_reasoning_profile(
        provider_type,
        model_name,
        base_url=base_url,
    ).to_dict()


def merge_reasoning_capabilities(
    provider_type: str | None,
    model_name: str | None,
    *,
    base_url: str | None = None,
    advertised: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve model capabilities from provider metadata, then verified profiles.

    A provider model-list response can include reasoning fields at its root or
    under ``capabilities`` / ``reasoning``. Unknown metadata never erases a
    verified model-family profile, and arbitrary provider response fields are
    not copied into the capability cache.
    """
    result: dict[str, Any] = reasoning_capabilities(
        provider_type,
        model_name,
        base_url=base_url,
    )
    if not isinstance(advertised, Mapping):
        return result

    sources: list[Mapping[str, Any]] = [advertised]
    for source in tuple(sources):
        for key in ("capabilities", "reasoning_capabilities", "reasoning"):
            nested = source.get(key)
            if isinstance(nested, Mapping):
                sources.append(nested)
                for nested_key in ("reasoning_capabilities", "reasoning"):
                    nested_reasoning = nested.get(nested_key)
                    if isinstance(nested_reasoning, Mapping):
                        sources.append(nested_reasoning)

    selected: dict[str, Any] = {}
    efforts_raw: object | None = None
    default_effort: str | None = None
    effort_values: dict[str, str] = {}
    for source in sources:
        for key in _REASONING_METADATA_KEYS:
            value = source.get(key)
            if key in {"request_controls_on", "request_controls_off"}:
                if isinstance(value, list | tuple):
                    selected[key] = [
                        item
                        for item in value
                        if isinstance(item, str) and item in _REASONING_REQUEST_CONTROLS
                    ]
                continue
            if key == "supported_reasoning_efforts":
                if isinstance(value, list | tuple):
                    efforts_raw = value[:32]
                continue
            if key == "default_reasoning_effort":
                default_effort = normalize_reasoning_effort_value(value)
                continue
            if key == "reasoning_effort_values" and isinstance(value, Mapping):
                for name, native_value in value.items():
                    canonical = normalize_reasoning_effort_value(name)
                    if (
                        canonical
                        and (canonical in effort_values or len(effort_values) < 33)
                        and isinstance(native_value, str)
                        and _REASONING_EFFORT_PATTERN.fullmatch(native_value.strip().casefold())
                    ):
                        effort_values[canonical] = native_value.strip()
                continue
            if key in {
                "supports_reasoning",
                "reasoning_capabilities_known",
                "supports_thinking_summary_stream",
                "supports_thinking_toggle",
            }:
                if isinstance(value, bool):
                    selected[key] = value
                continue
            if key == "reasoning_visibility" and value in {"hidden", "provider_exposed"}:
                selected[key] = value

        # Model catalogs commonly use ``supported_efforts`` for nested
        # reasoning metadata. Accept the alias without accepting arbitrary
        # effort names or request fields.
        if efforts_raw is None:
            alias = source.get("supported_efforts")
            if isinstance(alias, list | tuple):
                efforts_raw = alias

    normalized_efforts: list[str] = []
    native_values: dict[str, str] = {}
    if isinstance(efforts_raw, list | tuple):
        for value in efforts_raw:
            if not isinstance(value, str):
                continue
            canonical = normalize_reasoning_effort_value(value)
            if canonical is None:
                continue
            if canonical not in normalized_efforts and len(normalized_efforts) < 32:
                normalized_efforts.append(canonical)
                native_values[canonical] = value.strip()
    if normalized_efforts or (
        efforts_raw is not None and selected.get("reasoning_capabilities_known") is not False
    ):
        selected["supported_reasoning_efforts"] = normalized_efforts
        selected["reasoning_capabilities_known"] = True
        selected["supports_reasoning"] = bool(normalized_efforts) or selected.get(
            "supports_thinking_toggle", False
        )
    if effort_values:
        native_values.update(effort_values)
    if native_values:
        profile_values = result.get("reasoning_effort_values")
        selected["reasoning_effort_values"] = {
            **(profile_values if isinstance(profile_values, dict) else {}),
            **native_values,
        }
    if default_effort and (not normalized_efforts or default_effort in normalized_efforts):
        selected["default_reasoning_effort"] = default_effort

    if selected.get("reasoning_capabilities_known") is False:
        advertised_is_explicit = bool(selected.get("supported_reasoning_efforts"))
    else:
        advertised_is_explicit = (
            selected.get("reasoning_capabilities_known") is True
            or "supports_reasoning" in selected
            or "supported_reasoning_efforts" in selected
            or "supports_thinking_toggle" in selected
        )
    if not advertised_is_explicit:
        return result

    # Provider-confirmed metadata wins. A catalog's explicit unknown marker
    # alone does not override a verified family profile.
    result.update(selected)
    result["reasoning_capabilities_known"] = True
    if "supported_reasoning_efforts" not in result:
        result["supported_reasoning_efforts"] = []
    if "supports_reasoning" not in result:
        result["supports_reasoning"] = bool(
            result.get("supported_reasoning_efforts") or result.get("supports_thinking_toggle")
        )
    return result


def request_supports_reasoning(
    metadata: Mapping[str, Any] | None,
    *,
    inferred_support: bool,
) -> bool:
    """Prefer resolved per-model request metadata over model-name inference."""
    if isinstance(metadata, Mapping):
        capabilities = metadata.get("model_reasoning_capabilities")
        if (
            isinstance(capabilities, Mapping)
            and capabilities.get("reasoning_capabilities_known") is True
        ):
            return capabilities.get("supports_reasoning") is True
    return inferred_support
