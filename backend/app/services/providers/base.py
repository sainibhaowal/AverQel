from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.services.providers.types import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResult,
    ProviderModelInfo,
    RerankRequest,
    RerankResponse,
    WebSearchRequest,
    WebSearchResponse,
)


class ProviderCapabilityError(RuntimeError):
    pass


@dataclass(slots=True)
class ProviderRequestError(RuntimeError):
    provider_name: str
    status_code: int
    message: str | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(
            self,
            self.message
            or f"{self.provider_name} provider request failed with status {self.status_code}",
        )


class ChatProvider(Protocol):
    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse: ...

    def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]: ...

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]: ...

    def list_models(self) -> Sequence[ProviderModelInfo]: ...

    def health_check(self) -> HealthCheckResult: ...


class EmbeddingProvider(Protocol):
    def embed_many(self, request: EmbeddingRequest) -> EmbeddingResponse: ...

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]: ...

    def health_check(self) -> HealthCheckResult: ...


class RerankerProvider(Protocol):
    def rerank(self, request: RerankRequest) -> RerankResponse: ...

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]: ...

    def health_check(self) -> HealthCheckResult: ...


class WebSearchProvider(Protocol):
    def search(self, request: WebSearchRequest) -> WebSearchResponse: ...

    def health_check(self) -> HealthCheckResult: ...


class ModelDiscoveryProvider(Protocol):
    def list_models(self) -> Sequence[ProviderModelInfo]: ...

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]: ...

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]: ...

    def health_check(self) -> HealthCheckResult: ...


class ModelInstallProvider(Protocol):
    def list_local_models(self) -> Sequence[ProviderModelInfo]: ...

    def pull_model(self, model_name: str) -> HealthCheckResult: ...

    def delete_model(self, model_name: str) -> HealthCheckResult: ...


class HealthCheckProvider(Protocol):
    def health_check(self) -> HealthCheckResult: ...
