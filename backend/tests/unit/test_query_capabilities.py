from __future__ import annotations

from app.query.api.queries import _merge_chat_reasoning_capabilities


def test_merge_chat_reasoning_capabilities_fills_missing_reasoning_flags_from_inference() -> None:
    cached = {
        "supports_structured_output": True,
    }
    inferred = {
        "supports_reasoning": True,
        "supports_thinking_toggle": True,
        "reasoning_visibility": "provider_exposed",
        "request_controls_on": ["enable_thinking_true"],
        "request_controls_off": ["enable_thinking_false"],
        "supported_reasoning_efforts": ["low", "medium", "high"],
    }

    merged = _merge_chat_reasoning_capabilities(cached, inferred)

    assert merged["supports_structured_output"] is True
    assert merged["supports_reasoning"] is True
    assert merged["supports_thinking_toggle"] is True
    assert merged["reasoning_visibility"] == "provider_exposed"
    assert merged["request_controls_on"] == ["enable_thinking_true"]
    assert merged["request_controls_off"] == ["enable_thinking_false"]
    assert merged["supported_reasoning_efforts"] == ["low", "medium", "high"]


def test_merge_chat_reasoning_capabilities_preserves_cached_lists_and_unions_inferred_values() -> (
    None
):
    cached = {
        "supports_reasoning": True,
        "supports_thinking_toggle": False,
        "reasoning_visibility": "provider_exposed",
        "request_controls_on": ["cached_on"],
        "request_controls_off": ["cached_off"],
        "supported_reasoning_efforts": ["medium"],
    }
    inferred = {
        "supports_reasoning": True,
        "supports_thinking_toggle": True,
        "reasoning_visibility": "provider_exposed",
        "request_controls_on": ["enable_thinking_true"],
        "request_controls_off": ["enable_thinking_false"],
        "supported_reasoning_efforts": ["low", "medium", "high"],
    }

    merged = _merge_chat_reasoning_capabilities(cached, inferred)

    assert merged["supports_reasoning"] is True
    assert merged["supports_thinking_toggle"] is True
    assert merged["request_controls_on"] == ["cached_on", "enable_thinking_true"]
    assert merged["request_controls_off"] == ["cached_off", "enable_thinking_false"]
    assert merged["supported_reasoning_efforts"] == ["medium", "low", "high"]
