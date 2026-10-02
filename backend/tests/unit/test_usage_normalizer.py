from app.providers.services.usage_normalizer import normalize_chat_usage


def test_normalize_openai_cached_usage() -> None:
    result = normalize_chat_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 80},
        }
    )
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 20
    assert result["cached_input_tokens"] == 80


def test_normalize_anthropic_cache_usage() -> None:
    result = normalize_chat_usage(
        {
            "input_tokens": 120,
            "output_tokens": 30,
            "cache_read_input_tokens": 90,
            "cache_creation_input_tokens": 30,
        }
    )
    assert result["cached_input_tokens"] == 90
    assert result["cache_write_input_tokens"] == 30


def test_unknown_usage_is_not_invented() -> None:
    result = normalize_chat_usage({})
    assert result["input_tokens"] is None
    assert result["cached_input_tokens"] is None
    assert result["usage_source"] == "unavailable"


def test_normalize_gemini_usage_metadata() -> None:
    result = normalize_chat_usage(
        {
            "promptTokenCount": 200,
            "candidatesTokenCount": 40,
            "cachedContentTokenCount": 150,
        }
    )
    assert result == {
        "input_tokens": 200,
        "output_tokens": 40,
        "cached_input_tokens": 150,
        "cache_write_input_tokens": None,
        "usage_source": "provider",
    }


def test_normalize_openresponses_nested_cache_details() -> None:
    result = normalize_chat_usage(
        {
            "input_tokens": 100,
            "output_tokens": 10,
            "input_token_details": {"cached_tokens": 75},
        }
    )
    assert result["cached_input_tokens"] == 75
    assert result["usage_source"] == "provider"
