from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class ContextWindowResolution:
    context_window: int | None
    source: str | None = None


def coerce_positive_int(value: Any) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value > 0:
        return int(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", "").replace("_", "")
        if stripped.isdigit():
            parsed = int(stripped)
            if parsed > 0:
                return parsed
    return None


def extract_context_window(
    payload: Any,
    *,
    candidate_keys: Iterable[str] = (),
) -> int | None:
    normalized_candidates = {
        _normalize_context_key(key)
        for key in candidate_keys
        if isinstance(key, str) and key.strip()
    }

    def walk(value: Any) -> int | None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                normalized_key = _normalize_context_key(str(key))
                if normalized_key in normalized_candidates:
                    coerced = coerce_positive_int(nested_value)
                    if coerced is not None:
                        return coerced
                found = walk(nested_value)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for nested_value in value:
                found = walk(nested_value)
                if found is not None:
                    return found
        return None

    return walk(payload)


def resolve_verified_context_window(
    model_name: str,
    *,
    provider_type: str | None = None,
) -> ContextWindowResolution:
    normalized_model = _normalize_context_key(model_name)
    normalized_provider = _normalize_context_key(provider_type or "")
    if normalized_provider and normalized_provider not in _VERIFIED_CONTEXT_WINDOW_PROVIDER_TYPES:
        return ContextWindowResolution(None, None)

    for predicate, limit, source in _VERIFIED_CONTEXT_WINDOW_RULES:
        if predicate(normalized_model):
            return ContextWindowResolution(limit, source)
    return ContextWindowResolution(None, None)


def _normalize_context_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


_VERIFIED_CONTEXT_WINDOW_PROVIDER_TYPES = {
    "anthropic",
    "custom",
    "fireworks",
    "google",
    "groq",
    "groqopenaicompatible",
    "mistral",
    "opencodezen",
    "openai",
    "openaicompatible",
    "openrouter",
    "perplexity",
    "together",
    "vllm",
}

_VERIFIED_CONTEXT_WINDOW_RULES: tuple[tuple[Callable[[str], bool], int, str], ...] = (
    (
        lambda model: model.startswith("minimaxm2"),
        204_800,
        "official_docs:minimax",
    ),
    (
        lambda model: model.startswith("nemotron3super") or model.startswith("nemotron4"),
        1_048_576,
        "official_docs:nvidia",
    ),
    (
        lambda model: model.startswith("qwen3coder480b") or model.startswith("qwen25coder"),
        256_000,
        "official_docs:qwen",
    ),
    (
        lambda model: model.startswith("qwen3") or model.startswith("qwen25"),
        128_000,
        "official_docs:qwen",
    ),
    (
        lambda model: model.startswith("deepseekr1") or model.startswith("deepseekv3"),
        64_000,
        "official_docs:deepseek",
    ),
    (
        lambda model: model.startswith("deepseekv25") or model.startswith("deepseekcoder"),
        128_000,
        "official_docs:deepseek",
    ),
    (
        lambda model: model.startswith("kimik25")
        or model
        in {
            "kimik20905preview",
            "kimik2turbopreview",
            "kimik2thinking",
            "kimik2thinkingturbo",
            "kimik25",
            "kimik25pro",
        },
        256_000,
        "official_docs:moonshot",
    ),
    (
        lambda model: model.startswith("gemini3") or model.startswith("gemini25"),
        1_048_576,
        "official_docs:google",
    ),
    (
        lambda model: model.startswith("gemma4") or model.startswith("gemma3"),
        128_000,
        "official_docs:google",
    ),
    (
        lambda model: model
        in {
            "claudeopus4",
            "claudeopus41",
            "claudesonnet4",
            "claudesonnet41",
            "claudesonnet45",
            "claudecode4",
        },
        200_000,
        "official_docs:anthropic",
    ),
    (
        lambda model: model.startswith("claude37") or model.startswith("claude37"),
        200_000,
        "official_docs:anthropic",
    ),
    (
        lambda model: model
        in {
            "gpt51",
            "gpt51codex",
            "gpt51codexmax",
            "gpt51codexmini",
            "gpt5",
            "gpt5codex",
            "gpt5codexmax",
            "gpt5codexmini",
            "gpt41reasoning",
            "gpt4oreasoning",
        },
        400_000,
        "official_docs:openai",
    ),
    (
        lambda model: model
        in {
            "gpt51chatlatest",
            "gpt5chatlatest",
            "gpt41",
            "gpt4o",
            "gpt4omini",
        },
        128_000,
        "official_docs:openai",
    ),
    (
        lambda model: model.startswith("o1") or model.startswith("o3") or model.startswith("o4"),
        200_000,
        "official_docs:openai",
    ),
    (
        lambda model: model.startswith("llama31")
        or model.startswith("llama32")
        or model.startswith("llama33"),
        128_000,
        "official_docs:meta",
    ),
    (
        lambda model: model.startswith("llama4"),
        256_000,
        "official_docs:meta",
    ),
    (
        lambda model: model.startswith("mistrallarge") or model.startswith("mistralreasoning"),
        128_000,
        "official_docs:mistral",
    ),
)
