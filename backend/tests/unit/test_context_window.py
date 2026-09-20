from app.providers.services.context_window import resolve_verified_context_window


def test_gpt_oss_context_window_is_available_for_live_context_meter() -> None:
    result = resolve_verified_context_window(
        "openai/gpt-oss-20b", provider_type="groq-openai-compatible"
    )

    assert result.context_window == 131_072
    assert result.source == "official_docs:groq"


def test_deepseek_v4_models_have_official_one_million_token_context_windows() -> None:
    for model_name in ("deepseek-flash", "deepseek-v4-pro"):
        result = resolve_verified_context_window(model_name, provider_type="deepseek")
        assert result.context_window == 1_048_576
        assert result.source == "official_docs:deepseek"
