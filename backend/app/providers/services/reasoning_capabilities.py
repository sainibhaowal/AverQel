from __future__ import annotations

from dataclasses import dataclass
from typing import Final

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
    "custom",
    "openai-compatible",
}

_OPENAI_COMPATIBLE_PROVIDER_TYPES: Final[set[str]] = {
    "lmstudio",
    "openai",
    "opencode-zen",
    "custom",
    "openai-compatible",
    "groq",
    "groq-openai-compatible",
    "together",
    "fireworks",
    "mistral",
    "perplexity",
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
    reasoning_visibility: str = "hidden"
    supports_thinking_summary_stream: bool = False
    supported_reasoning_efforts: tuple[str, ...] = ()
    supports_thinking_toggle: bool = False
    request_controls_on: tuple[str, ...] = ()
    request_controls_off: tuple[str, ...] = ()
    response_formats: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "supports_reasoning": self.supports_reasoning,
            "reasoning_visibility": self.reasoning_visibility,
            "supports_thinking_summary_stream": self.supports_thinking_summary_stream,
            "supported_reasoning_efforts": list(self.supported_reasoning_efforts),
            "supports_thinking_toggle": self.supports_thinking_toggle,
            "request_controls_on": list(self.request_controls_on),
            "request_controls_off": list(self.request_controls_off),
            "response_formats": list(self.response_formats),
        }


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


def uses_enable_thinking_controls(
    provider_type: str | None, model_name: str | None
) -> bool:
    return (
        provider_type or ""
    ).lower() in _LOCAL_REASONING_PROVIDER_TYPES and _matches_any(
        model_name,
        _ENABLE_THINKING_HINTS,
    )


def uses_slash_think_controls(
    provider_type: str | None, model_name: str | None
) -> bool:
    return (
        provider_type or ""
    ).lower() in _LOCAL_REASONING_PROVIDER_TYPES and _matches_any(
        model_name,
        _SLASH_THINK_HINTS,
    )


def uses_openai_reasoning_payload(
    provider_type: str | None, model_name: str | None
) -> bool:
    return (
        provider_type or ""
    ).lower() in _OPENAI_COMPATIBLE_PROVIDER_TYPES and _matches_any(
        model_name,
        _OPENAI_REASONING_PAYLOAD_HINTS,
    )


def uses_think_tags(provider_type: str | None, model_name: str | None) -> bool:
    return (
        provider_type or ""
    ).lower() in _OPENAI_COMPATIBLE_PROVIDER_TYPES and _matches_any(
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
    if provider in {"google", "opencode-zen"} and _matches_any(
        model_name, _GOOGLE_HINTS
    ):
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
    if provider in {"anthropic", "opencode-zen"} and _matches_any(
        model_name, _ANTHROPIC_HINTS
    ):
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
