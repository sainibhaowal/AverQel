from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class MessageVersionSchema(BaseModel):
    id: uuid.UUID
    version_index: int
    content: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    source_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class MessageEditRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")


class RegenerateRequest(BaseModel):
    top_k: int = Field(default=5, ge=1, le=100)
    search_mode: str = Field(default="hybrid", pattern="^(hybrid|semantic|keyword)$")
    document_id: uuid.UUID | None = None
    thinking_enabled: bool = False
    agentic_mode: bool = True

    model_config = ConfigDict(extra="forbid")


class ConversationSchema(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    created_at: datetime
    updated_at: datetime
    content_html: str | None = None
    # Server-authoritative mission state used by history tiles. Optional keeps
    # the schema compatible with non-agent conversations and client storage.
    live_status: str | None = None
    live_mission_id: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="Untitled Note", min_length=1, max_length=100)
    content_html: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> str:
        title = str(value or "").strip()
        return title or "Untitled Note"


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content_html: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> str | None:
        if value is None:
            return None
        title = str(value).strip()
        return title or None


class ChatHistoryResponse(BaseModel):
    messages: list[MessageSchema]

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


class MemoryRetentionPolicySchema(BaseModel):
    session_retention_days: int
    decay_half_life_days: float

    model_config = ConfigDict(extra="forbid")


class MemoryRetentionQuerySchema(BaseModel):
    query: str
    matches: int
    top_score: float

    model_config = ConfigDict(extra="forbid")


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

    model_config = ConfigDict(extra="forbid")


class MemoryLifecycleReportSchema(MemoryRetentionReportSchema):
    stale_memory_ids: list[str] = Field(default_factory=list)
    stale_preview_count: int = 0
    attention_memories: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ConversationListResponse(BaseModel):
    items: list[ConversationSchema]
    total: int

    model_config = ConfigDict(extra="forbid")


class BulkDeleteRequest(BaseModel):
    conversation_ids: list[uuid.UUID]

    model_config = ConfigDict(extra="forbid")


class TodoTaskSchema(BaseModel):
    id: str
    content: str
    status: str
    active_form: str = Field(alias="activeForm")
    priority: int = 0
    thread_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    automation_json: dict[str, Any] = Field(default_factory=dict)
    is_recurring: bool = False
    enabled: bool = True
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", populate_by_name=True
    )


class ProactiveTaskSummarySchema(BaseModel):
    total: int
    pending: int
    in_progress: int
    completed: int
    recurring: int
    enabled: int
    paused: int
    due: int
    approval_required: int
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    recent_activity_count: int = 0
    recent_error_count: int = 0
    recent_cycle_count: int = 0
    recent_cycle_failure_count: int = 0
    gmail_scan_failure_count: int = 0
    gmail_message_failure_count: int = 0
    last_cycle_at: datetime | None = None
    last_cycle_status: str | None = None

    model_config = ConfigDict(extra="forbid")


class TodoTaskUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    active_form: str | None = Field(
        default=None, alias="activeForm", min_length=1, max_length=4000
    )
    status: str | None = Field(
        default=None, pattern="^(pending|in_progress|completed)$"
    )
    priority: int | None = Field(default=None, ge=0, le=100)
    thread_id: str | None = None
    metadata_json: dict[str, Any] | None = None
    automation_json: dict[str, Any] | None = None
    is_recurring: bool | None = None
    enabled: bool | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TodoTaskCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    active_form: str = Field(alias="activeForm", min_length=1, max_length=4000)
    status: str = Field(default="pending", pattern="^(pending|in_progress|completed)$")
    priority: int = Field(default=0, ge=0, le=100)
    thread_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    automation_json: dict[str, Any] = Field(default_factory=dict)
    is_recurring: bool = False
    enabled: bool = True
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SubagentRunSchema(BaseModel):
    run_id: str
    tenant_id: str
    user_id: str
    parent_id: str = ""
    subagent_type: str
    prompt: str
    status: str
    slot_index: int = 0
    created_at: datetime | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    cancel_requested: bool = False
    last_event_type: str | None = None
    last_event_message: str | None = None
    summary: str = ""
    final_output: str = ""
    error: str = ""
    step_count: int = 0
    duration_ms: int = 0
    last_tool_name: str = ""
    last_tool_id: str = ""
    last_tool_output: str = ""
    heartbeat_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class SubagentSummarySchema(BaseModel):
    backend_available: bool
    max_concurrency: int
    active_count: int
    live_count: int
    running_count: int
    terminating_count: int
    cancelled_count: int
    stale_count: int
    pressure_count: int
    pressure_ratio: float
    daemon_heartbeat: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")
