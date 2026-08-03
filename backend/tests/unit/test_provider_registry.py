from __future__ import annotations

from app.core.config import get_settings
from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.google_provider import GoogleProvider
from app.providers.services.lmstudio_provider import LMStudioProvider
from app.providers.services.local_deterministic_provider import (
    LocalDeterministicEmbeddingProvider,
)
from app.providers.services.ollama_provider import OllamaProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.opencode_zen_provider import OpenCodeZenProvider
from app.providers.services.registry import ProviderRegistry
from app.providers.services.sentence_transformers_provider import (
    SentenceTransformersEmbeddingProvider,
)


def test_provider_registry_resolves_env_backed_chat_and_embedding_providers(
    monkeypatch,
):
    monkeypatch.setenv("AKS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("AKS_LLM_API_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    get_settings.cache_clear()
    registry = ProviderRegistry(get_settings())
    assert isinstance(registry.get_chat_provider(), OpenAICompatibleProvider)
    assert isinstance(
        registry.get_embedding_provider(), LocalDeterministicEmbeddingProvider
    )

    monkeypatch.setenv("AKS_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AKS_LLM_API_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "sentence-transformers")
    monkeypatch.setattr(
        "app.providers.services.url_resolution.os.path.exists",
        lambda path: path == "/.dockerenv",
    )
    get_settings.cache_clear()
    registry = ProviderRegistry(get_settings())
    ollama_provider = registry.get_chat_provider()
    embedding_provider = registry.get_embedding_provider()
    assert isinstance(ollama_provider, OllamaProvider)
    assert isinstance(embedding_provider, SentenceTransformersEmbeddingProvider)
    assert ollama_provider.base_url == "http://host.docker.internal:11434/v1"
    assert embedding_provider.base_url == "http://host.docker.internal:11434/v1"

    monkeypatch.setenv("AKS_LLM_PROVIDER", "lmstudio")
    monkeypatch.setenv("AKS_LLM_API_BASE_URL", "http://localhost:1234/v1")
    get_settings.cache_clear()
    registry = ProviderRegistry(get_settings())
    lmstudio_provider = registry.get_chat_provider()
    assert isinstance(lmstudio_provider, LMStudioProvider)
    assert lmstudio_provider.base_url == "http://host.docker.internal:1234/v1"

    assert isinstance(registry.get_chat_provider("anthropic"), AnthropicProvider)
    assert isinstance(registry.get_chat_provider("google"), GoogleProvider)
    assert isinstance(registry.get_chat_provider("opencode-zen"), OpenCodeZenProvider)
    groq_provider = registry.get_chat_provider("groq")
    assert isinstance(groq_provider, OpenAICompatibleProvider)
    assert groq_provider.provider_name == "groq"
    assert isinstance(
        registry.get_model_discovery_provider("opencode-zen"), OpenCodeZenProvider
    )
    get_settings.cache_clear()


def test_provider_registry_supports_sentence_transformers_model_discovery(monkeypatch):
    monkeypatch.setenv("AKS_LLM_API_BASE_URL", "http://localhost:1234/v1")
    get_settings.cache_clear()
    registry = ProviderRegistry(get_settings())

    discovery = registry.get_model_discovery_provider("sentence-transformers")

    assert isinstance(discovery, SentenceTransformersEmbeddingProvider)
    embedding_models = discovery.list_embedding_models()
    assert [model.name for model in embedding_models] == [
        "BAAI/bge-small-en-v1.5",
        "intfloat/multilingual-e5-small",
    ]
    get_settings.cache_clear()
