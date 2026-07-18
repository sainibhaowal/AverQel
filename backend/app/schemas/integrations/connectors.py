import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.integrations.connector import ConnectorStatus


class ConnectorOAuthStatus(BaseModel):
    configured: bool
    message: str
    missing: list[str] = Field(default_factory=list)
    provider_key: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class IntegrationRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    ui_metadata: dict[str, Any]
    is_active: bool
    oauth_status: ConnectorOAuthStatus | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ConnectorBase(BaseModel):
    name: str
    integration_id: uuid.UUID
    collection_id: uuid.UUID | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    sync_frequency: str = "daily"


class ConnectorCreate(ConnectorBase):
    credentials: dict[str, str] = Field(default_factory=dict)


class ConnectorRead(ConnectorBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    status: ConnectorStatus
    last_sync_at: datetime | None
    next_sync_at: datetime | None
    last_error: str | None
    error_count: int
    health_status: str | None = None
    last_checked_at: datetime | None = None
    last_good_at: datetime | None = None
    circuit_open_until: datetime | None = None
    consecutive_failures: int = 0
    health_metadata: dict[str, Any] = Field(default_factory=dict)
    last_success_snapshot: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SyncResult(BaseModel):
    status: str
    message: str | None = None
    document_id: uuid.UUID | None = None

    model_config = ConfigDict(extra="forbid")


class ConnectorSummary(BaseModel):
    connector: ConnectorRead
    health: dict[str, Any] = Field(default_factory=dict)
    sync_checkpoint: dict[str, Any] = Field(default_factory=dict)
    last_sync_audit: dict[str, Any] | None = None
    live_status: str | None = None
    retry_state: str | None = None
    retryable: bool | None = None
    retry_after_at: datetime | None = None
    retry_after_seconds: int | None = None
    error_domain: str | None = None
    health_age_seconds: int | None = None
    sync_checkpoint_age_seconds: int | None = None
    recent_audit_count: int = 0

    model_config = ConfigDict(extra="forbid")


class ConnectorFleetSummary(BaseModel):
    total_connectors: int
    active_count: int
    syncing_count: int
    paused_count: int
    error_count: int
    healthy_count: int
    stale_count: int
    retryable_count: int
    due_sync_count: int
    recent_audit_count: int
    status_breakdown: dict[str, int] = Field(default_factory=dict)
    integration_breakdown: dict[str, int] = Field(default_factory=dict)
    error_domain_breakdown: dict[str, int] = Field(default_factory=dict)
    health_status_breakdown: dict[str, int] = Field(default_factory=dict)
    retry_state_breakdown: dict[str, int] = Field(default_factory=dict)
    attention_connectors: list[dict[str, Any]] = Field(default_factory=list)
    daemon_heartbeat: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class ConnectorSyncAuditEntry(BaseModel):
    id: uuid.UUID
    action: str
    status: str
    phase: str | None = None
    error_code: str | None = None
    error_domain: str | None = None
    retryable: bool | None = None
    retry_after_at: datetime | None = None
    retry_after_seconds: int | None = None
    attempt: int | None = None
    duration_ms: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class ConnectorOAuthStartResponse(BaseModel):
    available: bool
    authorization_url: str | None = None
    message: str
    connector_id: uuid.UUID | None = None
    integration_slug: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")
