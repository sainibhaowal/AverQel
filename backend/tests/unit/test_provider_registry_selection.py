from __future__ import annotations

from uuid import UUID

from app.core.config import get_settings
from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.google_provider import GoogleProvider
from app.providers.services.ollama_provider import OllamaProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.registry import ProviderRegistry
from app.providers.services.types import ProviderSelectionCandidate


def test_registry_resolves_chat_provider_from_selection(monkeypatch) -> None:
    monkeypatch.setenv("AKS_LLM_PROVIDER", "disabled")
    monkeypatch.setattr(
        "app.providers.services.url_resolution.os.path.exists",
        lambda path: path == "/.dockerenv",
    )
    get_settings.cache_clear()
    registry = ProviderRegistry(get_settings())

    openai_candidate = ProviderSelectionCandidate(
        provider_type="openai",
        model_name="gpt-4.1-mini",
        feature_scope="chat",
        source="tenant",
        provider_config_id=UUID("11111111-1111-7111-8111-111111111111"),
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
        base_url="https://api.openai.com/v1",
    )
    assert isinstance(
        registry.get_chat_provider_from_selection(openai_candidate),
        OpenAICompatibleProvider,
    )

    ollama_candidate = ProviderSelectionCandidate(
        provider_type="ollama",
        model_name="llama3",
        feature_scope="chat",
        source="tenant",
        provider_config_id=UUID("22222222-2222-7222-8222-222222222222"),
        tenant_id=UUID("22222222-2222-7222-8222-222222222222"),
        base_url="http://localhost:11434",
    )
    ollama_provider = registry.get_chat_provider_from_selection(ollama_candidate)
    assert isinstance(ollama_provider, OllamaProvider)
    assert ollama_provider.base_url == "http://host.docker.internal:11434"
    assert isinstance(registry.get_chat_provider("anthropic"), AnthropicProvider)
    assert isinstance(registry.get_chat_provider("google"), GoogleProvider)
    get_settings.cache_clear()


def test_registry_resolves_embedding_provider_from_selection(monkeypatch) -> None:
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    get_settings.cache_clear()
    registry = ProviderRegistry(get_settings())

    candidate = ProviderSelectionCandidate(
        provider_type="openai",
        model_name="text-embedding-3-small",
        feature_scope="embeddings",
        source="tenant",
        provider_config_id=UUID("33333333-3333-7333-8333-333333333333"),
        tenant_id=UUID("33333333-3333-7333-8333-333333333333"),
        base_url="https://api.openai.com/v1",
    )
    assert isinstance(
        registry.get_embedding_provider_from_selection(candidate),
        OpenAICompatibleProvider,
    )
    get_settings.cache_clear()
