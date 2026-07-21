from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.query.schemas.structured_response import StructuredAnswerResponse


class QueryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[UUID] | None = Field(default=None, max_length=50)
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None
    source_types: list[str] | None = Field(default=None, max_length=10)
    min_extraction_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    max_extraction_coverage: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_range(self) -> QueryFilters:
        if (
            self.created_at_from is not None
            and self.created_at_to is not None
            and self.created_at_from > self.created_at_to
        ):
            raise ValueError(
                "created_at_from must be less than or equal to created_at_to"
            )
        if (
            self.min_extraction_coverage is not None
            and self.max_extraction_coverage is not None
            and self.min_extraction_coverage > self.max_extraction_coverage
        ):
            raise ValueError(
                "min_extraction_coverage must be less than or equal to max_extraction_coverage"
            )
        return self


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(ge=1, le=100)
    conversation_id: UUID | None = None
    conversation_kind: str = Field(default="query", pattern="^(query|deepspace)$")
    search_mode: str = Field(default="hybrid", pattern="^(hybrid|semantic|keyword)$")
    thinking_enabled: bool = False
    filters: QueryFilters = Field(default_factory=QueryFilters)

    model_config = ConfigDict(extra="forbid")

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized


class QueryCitationResponse(BaseModel):
    document_id: UUID
    chunk_id: UUID
    filename: str
    snippet: str
    similarity_score: float
    source_type: str = "text"
    section_header: str | None = None
    page_number: int | None = None

    model_config = ConfigDict(extra="forbid")


class QueryResponse(BaseModel):
    answer: str | StructuredAnswerResponse
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[QueryCitationResponse]
    trace_id: str
    cached: bool
    conversation_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class QueryPersistedPayload(BaseModel):
    query_id: UUID
    cache_hit: bool
    top_k: int
    filters: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class CitationFeedbackRequest(BaseModel):
    score: int = Field(ge=-1, le=1)  # 1 for helpful, -1 for unhelpful

    model_config = ConfigDict(extra="forbid")


class CitationFeedbackResponse(BaseModel):
    query_id: UUID
    chunk_id: UUID
    score: int

    model_config = ConfigDict(extra="forbid")


class ChatCapabilitiesResponse(BaseModel):
    provider_type: str | None = None
    model_name: str | None = None
    context_limit: int | None = None
    context_limit_source: str | None = None
    supports_thinking: bool = False
    supports_thinking_toggle: bool = False
    reasoning_visibility: str = "hidden"
    request_controls_on: list[str] = Field(default_factory=list)
    request_controls_off: list[str] = Field(default_factory=list)
    supported_reasoning_efforts: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
