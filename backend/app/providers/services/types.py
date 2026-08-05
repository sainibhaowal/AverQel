from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID


@dataclass(slots=True, frozen=True)
class ChatGenerateRequest:
    model: str
    messages: list[dict[str, Any]]
    temperature: float
    max_tokens: int
    base_url: str
    api_key: str | None = None
    stream: bool = False
    reasoning_enabled: bool = False
    reasoning_effort: str | None = None
    reasoning_visibility: str | None = None
    images: list[str] | None = None  # Base64 encoded images
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ChatGenerateResponse:
    content: str
    thinking_content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class EmbeddingRequest:
    texts: list[str]
    model: str
    batch_size: int
    normalize: bool
    dimension: int
    timeout_seconds: int
    provider_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class EmbeddingResponse:
    vectors: list[list[float]]


@dataclass(slots=True, frozen=True)
class RerankRequest:
    query: str
    documents: list[str]
    model: str
    top_n: int
    timeout_seconds: int
    provider_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RerankResultItem:
    index: int
    score: float


@dataclass(slots=True, frozen=True)
class RerankResponse:
    results: list[RerankResultItem]


@dataclass(slots=True, frozen=True)
class WebSearchRequest:
    query: str
    max_results: int
    timeout_seconds: int
    search_depth: str = "basic"
    include_answer: bool = True
    include_raw_content: bool = False
    provider_name: str = "web-search"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class WebSearchResultItem:
    title: str
    url: str
    content: str
    score: float | None = None
    raw_content: str | None = None
    favicon: str | None = None
    published_date: str | None = None
    source: str | None = None


@dataclass(slots=True, frozen=True)
class WebSearchResponse:
    query: str
    answer: str | None
    results: list[WebSearchResultItem]
    response_time: float | None = None
    request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ProviderModelInfo:
    name: str
    kind: Literal["chat", "embedding", "reranker", "vision", "other"]
    context_window: int | None = None
    context_window_source: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    display_name: str | None = None


@dataclass(slots=True, frozen=True)
class HealthCheckResult:
    status: Literal["healthy", "degraded", "unhealthy"]
    latency_ms: int | None = None
    error_code: str | None = None
    error_message_redacted: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SyncStreamingChatProvider:
    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        raise NotImplementedError


class AsyncStreamingChatProvider:
    def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        raise NotImplementedError


@dataclass(slots=True, frozen=True)
class ProviderSelectionCandidate:
    provider_type: str
    model_name: str
    feature_scope: str
    source: Literal[
        "workspace",
        "tenant",
        "workspace_fallback",
        "tenant_fallback",
        "env_fallback",
        "builtin",
    ]
    provider_config_id: UUID | None = None
    tenant_id: UUID | None = None
    workspace_id: UUID | None = None
    base_url: str | None = None
    api_key: str | None = None
    auth_mode: str | None = None
    context_window: int | None = None
    context_window_source: str | None = None
    priority: int = 100
    health_status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ProviderSelectionResult:
    feature_scope: str
    candidates: list[ProviderSelectionCandidate]
    selection_notes: list[str] = field(default_factory=list)
