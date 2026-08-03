from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.providers.models.provider_config import ProviderConfig
from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.base import (
    ChatProvider,
    EmbeddingProvider,
    ModelDiscoveryProvider,
    ModelInstallProvider,
    RerankerProvider,
    WebSearchProvider,
)
from app.providers.services.cohere_provider import CohereProvider
from app.providers.services.google_provider import GoogleProvider
from app.providers.services.lmstudio_provider import LMStudioProvider
from app.providers.services.local_deterministic_provider import (
    LocalDeterministicEmbeddingProvider,
)
from app.providers.services.ollama_provider import OllamaProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.opencode_zen_provider import OpenCodeZenProvider
from app.providers.services.openrouter_provider import OpenRouterProvider
from app.providers.services.searxng_provider import SearXNGProvider
from app.providers.services.sentence_transformers_provider import (
    SentenceTransformersEmbeddingProvider,
)
from app.providers.services.tavily_provider import TavilyProvider
from app.providers.services.types import ProviderSelectionCandidate
from app.providers.services.url_resolution import resolve_provider_base_url

OPENAI_COMPATIBLE_PROVIDER_TYPES = {
    "openai",
    "groq",
    "groq-openai-compatible",
    "mistral",
    "together",
    "fireworks",
    "perplexity",
    "vllm",
    "custom",
}


@dataclass
class ProviderRegistry:
    settings: Settings

    @staticmethod
    def _bind_chat_provider(
        provider: str,
        *,
        base_url: str | None,
        api_key: str | None,
    ) -> ChatProvider:
        if provider == "opencode-zen":
            return OpenCodeZenProvider().bind(base_url or "", api_key)
        if provider == "openrouter":
            return OpenRouterProvider(
                base_url=resolve_provider_base_url(base_url, provider_type=provider),
                api_key=api_key,
            )
        if provider in OPENAI_COMPATIBLE_PROVIDER_TYPES:
            return OpenAICompatibleProvider(
                base_url=resolve_provider_base_url(base_url, provider_type=provider),
                api_key=api_key,
                provider_name=provider,
            )
        if provider == "ollama":
            return OllamaProvider().bind(base_url or "")
        if provider == "lmstudio":
            return LMStudioProvider().bind(base_url or "", api_key)
        if provider == "anthropic":
            return AnthropicProvider().bind(base_url or "", api_key)
        if provider == "google":
            return GoogleProvider().bind(base_url or "", api_key)
        raise ValueError(f"Unsupported chat provider: {provider}")

    @staticmethod
    def _bind_embedding_provider(
        provider: str,
        *,
        base_url: str | None,
        api_key: str | None,
    ) -> EmbeddingProvider:
        if provider == "local-deterministic":
            return LocalDeterministicEmbeddingProvider()
        if provider == "sentence-transformers":
            return SentenceTransformersEmbeddingProvider(
                base_url=resolve_provider_base_url(base_url, provider_type=provider)
            )
        if provider == "openrouter":
            return OpenRouterProvider(
                supports_embeddings=True,
                base_url=resolve_provider_base_url(base_url, provider_type=provider),
                api_key=api_key,
            )
        if provider == "ollama":
            return OllamaProvider().bind(base_url or "")
        if provider == "lmstudio":
            return LMStudioProvider().bind(base_url or "", api_key)
        if provider in OPENAI_COMPATIBLE_PROVIDER_TYPES:
            return OpenAICompatibleProvider(
                supports_embeddings=True,
                base_url=resolve_provider_base_url(base_url, provider_type=provider),
                api_key=api_key,
                provider_name=provider,
            )
        raise ValueError(f"Unsupported embedding provider: {provider}")

    def get_chat_provider(self, provider_type: str | None = None) -> ChatProvider:
        resolved = provider_type or self.settings.llm_provider
        return self._bind_chat_provider(
            resolved,
            base_url=self.settings.llm_api_base_url,
            api_key=self.settings.llm_api_key,
        )

    def get_embedding_provider(
        self, provider_type: str | None = None
    ) -> EmbeddingProvider:
        resolved = provider_type or self.settings.embedding_provider
        return self._bind_embedding_provider(
            resolved,
            base_url=self.settings.llm_api_base_url,
            api_key=self.settings.llm_api_key,
        )

    @staticmethod
    def _bind_reranker_provider(
        provider: str,
        *,
        base_url: str | None,
        api_key: str | None,
    ) -> RerankerProvider:
        if provider == "sentence-transformers":
            return SentenceTransformersEmbeddingProvider(base_url=base_url)
        if provider == "cohere":
            return CohereProvider().bind(base_url or "", api_key)
        raise ValueError(f"Unsupported reranker provider: {provider}")

    def get_chat_provider_from_selection(
        self, selection: ProviderSelectionCandidate
    ) -> ChatProvider:
        return self._bind_chat_provider(
            selection.provider_type,
            base_url=selection.base_url,
            api_key=selection.api_key,
        )

    def get_embedding_provider_from_selection(
        self,
        selection: ProviderSelectionCandidate,
    ) -> EmbeddingProvider:
        return self._bind_embedding_provider(
            selection.provider_type,
            base_url=selection.base_url,
            api_key=selection.api_key,
        )

    def get_reranker_provider_from_selection(
        self,
        selection: ProviderSelectionCandidate,
    ) -> RerankerProvider:
        return self._bind_reranker_provider(
            selection.provider_type,
            base_url=selection.base_url,
            api_key=selection.api_key,
        )

    @staticmethod
    def _bind_web_search_provider(
        provider: str,
        *,
        base_url: str | None,
        api_key: str | None,
        settings: Settings | None = None,
        metadata: dict[str, object] | None = None,
    ) -> WebSearchProvider:
        if provider == "tavily":
            return TavilyProvider(base_url=base_url, api_key=api_key)
        if provider == "searxng":
            return SearXNGProvider(
                base_url=base_url,
                api_key=api_key,
                settings=settings,
                metadata=metadata,
            )
        raise ValueError(f"Unsupported web search provider: {provider}")

    def get_web_search_provider_from_selection(
        self,
        selection: ProviderSelectionCandidate,
    ) -> WebSearchProvider:
        return self._bind_web_search_provider(
            selection.provider_type,
            base_url=selection.base_url,
            api_key=selection.api_key,
            settings=self.settings,
            metadata=selection.metadata,
        )

    def get_web_search_provider_from_config(
        self,
        provider_config: ProviderConfig,
        *,
        api_key: str | None = None,
    ) -> WebSearchProvider:
        return self._bind_web_search_provider(
            provider_config.provider_type,
            base_url=provider_config.api_base_url,
            api_key=api_key,
            settings=self.settings,
            metadata=dict(provider_config.metadata_json or {}),
        )

    def get_model_discovery_provider(
        self, provider_type: str
    ) -> ModelDiscoveryProvider:
        if provider_type == "sentence-transformers":
            return SentenceTransformersEmbeddingProvider(
                base_url=self.settings.local_inference_base_url
            )
        if provider_type == "cohere":
            return CohereProvider().bind(
                self.settings.llm_api_base_url, self.settings.llm_api_key
            )
        if provider_type == "openrouter":
            return OpenRouterProvider(
                supports_embeddings=True,
                base_url=self.settings.llm_api_base_url
                or "https://openrouter.ai/api/v1",
                api_key=self.settings.llm_api_key,
            )
        if provider_type == "ollama":
            return OllamaProvider().bind(self.settings.llm_api_base_url)
        if provider_type == "lmstudio":
            return LMStudioProvider().bind(
                self.settings.llm_api_base_url, self.settings.llm_api_key
            )
        if provider_type == "opencode-zen":
            return OpenCodeZenProvider().bind(
                self.settings.llm_api_base_url or OpenCodeZenProvider.DEFAULT_BASE_URL,
                self.settings.llm_api_key,
            )
        if provider_type in OPENAI_COMPATIBLE_PROVIDER_TYPES:
            return OpenAICompatibleProvider(
                supports_embeddings=True,
                base_url=self.settings.llm_api_base_url,
                api_key=self.settings.llm_api_key,
                provider_name=provider_type,
            )
        raise ValueError(f"Unsupported discovery provider: {provider_type}")

    def get_install_provider(self, provider_type: str) -> ModelInstallProvider:
        if provider_type == "ollama":
            return OllamaProvider().bind(self.settings.llm_api_base_url)
        raise ValueError(f"Unsupported install provider: {provider_type}")

    def get_model_discovery_provider_from_config(
        self,
        provider_config: ProviderConfig,
        *,
        api_key: str | None = None,
    ) -> ModelDiscoveryProvider:
        if provider_config.provider_type == "sentence-transformers":
            return SentenceTransformersEmbeddingProvider(
                base_url=self.settings.local_inference_base_url
            )
        if provider_config.provider_type == "cohere":
            return CohereProvider().bind(
                provider_config.api_base_url or "https://api.cohere.com/v2",
                api_key,
            )
        if provider_config.provider_type == "openrouter":
            return OpenRouterProvider(
                supports_embeddings=provider_config.supports_embeddings,
                base_url=provider_config.api_base_url or "https://openrouter.ai/api/v1",
                api_key=api_key,
            )
        if provider_config.provider_type == "ollama":
            return OllamaProvider().bind(provider_config.api_base_url or "")
        if provider_config.provider_type == "lmstudio":
            return LMStudioProvider().bind(provider_config.api_base_url or "", api_key)
        if provider_config.provider_type == "opencode-zen":
            return OpenCodeZenProvider().bind(
                provider_config.api_base_url or OpenCodeZenProvider.DEFAULT_BASE_URL,
                api_key,
            )
        if provider_config.provider_type in OPENAI_COMPATIBLE_PROVIDER_TYPES:
            return OpenAICompatibleProvider(
                supports_embeddings=provider_config.supports_embeddings,
                base_url=provider_config.api_base_url or self.settings.llm_api_base_url,
                api_key=api_key,
                provider_name=provider_config.provider_type,
            )
        if provider_config.provider_type == "anthropic":
            return AnthropicProvider().bind(
                provider_config.api_base_url or self.settings.llm_api_base_url,
                api_key,
            )
        if provider_config.provider_type == "google":
            return GoogleProvider().bind(
                provider_config.api_base_url or self.settings.llm_api_base_url,
                api_key,
            )
        raise ValueError(
            f"Unsupported discovery provider: {provider_config.provider_type}"
        )

    def get_install_provider_from_config(
        self,
        provider_config: ProviderConfig,
        *,
        api_key: str | None = None,
    ) -> ModelInstallProvider:
        if provider_config.provider_type == "ollama":
            return OllamaProvider().bind(provider_config.api_base_url or "")
        raise ValueError(
            f"Unsupported install provider: {provider_config.provider_type}"
        )
