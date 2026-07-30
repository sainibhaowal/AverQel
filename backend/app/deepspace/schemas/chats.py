"""DeepSpace chat API contracts.

These contracts intentionally do not depend on the Query package. The table
shape is compatible with existing chat history so existing notes survive the
separation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageVersionSchema(BaseModel):
    id: uuid.UUID
    version_index: int
    content: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    source_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class MessageSchema(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    active_version_id: uuid.UUID | None = None
    active_version_index: int = 1
    version_count: int = 1
    versions: list[MessageVersionSchema] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ConversationSchema(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    created_at: datetime
    updated_at: datetime
    content_html: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="Untitled Note", min_length=1, max_length=100)
    content_html: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> str:
        return str(value or "").strip() or "Untitled Note"


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content_html: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value).strip() or None


class ChatHistoryResponse(BaseModel):
    messages: list[MessageSchema]


class ConversationListResponse(BaseModel):
    items: list[ConversationSchema]
    total: int


class BulkDeleteRequest(BaseModel):
    conversation_ids: list[uuid.UUID]


class MessageEditRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class RegenerateRequest(BaseModel):
    thinking_enabled: bool = False


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|denied)$")

    model_config = ConfigDict(extra="forbid")


class MemoryFactSchema(BaseModel):
    id: str
    key: str
    value: str
    scope: str
    tags: list[str] = Field(default_factory=list)
    importance_score: float | None = None
    access_count: int | None = None
    last_accessed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None
    pgvector_ready: bool | None = None
    decay_score: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class MemoryWriteRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=10000)
    scope: str = Field(default="user", max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    importance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class MemoryUpdateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=10000)
    scope: str = Field(default="user", max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    importance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class MemoryRetentionQuerySchema(BaseModel):
    query: str
    matches: int
    top_score: float


class MemoryRetentionPolicySchema(BaseModel):
    session_retention_days: int
    decay_half_life_days: float


class MemoryRetentionReportSchema(BaseModel):
    memory_count: int
    embedded_count: int
    pgvector_count: int
    embedding_coverage: float
    duplicate_count: int
    scope_breakdown: dict[str, int] = Field(default_factory=dict)
    retention_breakdown: dict[str, int] = Field(default_factory=dict)
    stale_count: int = 0
    stale_session_count: int = 0
    average_decay_score: float = 0.0
    memory_health_score: float = 0.0
    retention_risk_count: int = 0
    sample_queries: list[MemoryRetentionQuerySchema] = Field(default_factory=list)
    retention_policy: MemoryRetentionPolicySchema
    session_retention_days: int
