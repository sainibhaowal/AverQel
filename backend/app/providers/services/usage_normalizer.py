"""Provider-neutral usage normalization for cache-aware diagnostics."""

from __future__ import annotations

from typing import Any


def _first_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    return None


def normalize_chat_usage(usage: object) -> dict[str, int | None | str]:
    """Normalize common OpenAI, Anthropic, Gemini, and OpenResponses fields."""
    raw = usage if isinstance(usage, dict) else {}
    prompt_details = raw.get("prompt_tokens_details") or raw.get("input_token_details")
    completion_details = raw.get("completion_tokens_details") or raw.get("output_token_details")
    prompt = _first_int(raw, "prompt_tokens", "input_tokens", "promptTokenCount", "inputTokenCount")
    output = _first_int(
        raw, "completion_tokens", "output_tokens", "candidatesTokenCount", "outputTokenCount"
    )
    cached = _first_int(
        raw,
        "cached_tokens",
        "cache_read_input_tokens",
        "cache_read_tokens",
        "cachedContentTokenCount",
        "cache_read",
    )
    written = _first_int(
        raw,
        "cache_creation_input_tokens",
        "cache_write_input_tokens",
        "cache_creation_tokens",
        "cache_write",
    )
    if isinstance(prompt_details, dict):
        cached = (
            cached
            if cached is not None
            else _first_int(prompt_details, "cached_tokens", "cache_read")
        )
    if isinstance(completion_details, dict):
        output = (
            output
            if output is not None
            else _first_int(completion_details, "tokens", "output_tokens")
        )
    return {
        "input_tokens": prompt,
        "output_tokens": output,
        "cached_input_tokens": cached,
        "cache_write_input_tokens": written,
        "usage_source": (
            "provider"
            if any(value is not None for value in (prompt, output, cached, written))
            else "unavailable"
        ),
    }
