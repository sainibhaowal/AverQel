from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogItem(BaseModel):
    id: UUID
    tenant_id: UUID
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    status: str
    trace_id: str
    ip_address: str | None = None
    created_at: datetime
    details: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class CursorPage(BaseModel):
    next_cursor: str | None
    has_more: bool

    model_config = ConfigDict(extra="forbid")


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    page: CursorPage

    model_config = ConfigDict(extra="forbid")


class DataDeletionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)
    target_tenant_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class DataDeletionRequestResponse(BaseModel):
    deletion_id: UUID
    status: str

    model_config = ConfigDict(extra="forbid")


class DataDeletionStatusResponse(BaseModel):
    deletion_id: UUID
    tenant_id: UUID
    requested_by_user_id: UUID
    status: str
    scope: str
    reason: str | None
    result_counts: dict[str, int] = Field(default_factory=dict)
    error_code: str | None
    error_message: str | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None

    model_config = ConfigDict(extra="forbid")


class DataDeletionListResponse(BaseModel):
    items: list[DataDeletionStatusResponse]

    model_config = ConfigDict(extra="forbid")


class AdminUserStatsResponse(BaseModel):
    documents_count: int
    queries_count: int
    conversations_count: int
    comments_count: int
    pinned_findings_count: int
    providers_count: int
    storage_bytes: int

    model_config = ConfigDict(extra="forbid")


class AdminUserSummaryResponse(BaseModel):
    user_id: UUID
    tenant_id: UUID
    tenant_name: str | None = None
    email: str
    is_active: bool
    totp_enabled: bool
    roles: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    stats: AdminUserStatsResponse

    model_config = ConfigDict(extra="forbid")


class AdminUserListResponse(BaseModel):
    items: list[AdminUserSummaryResponse]

    model_config = ConfigDict(extra="forbid")


class AdminUserDetailResponse(BaseModel):
    user: AdminUserSummaryResponse
    recent_activity: list[AuditLogItem]

    model_config = ConfigDict(extra="forbid")


class AdminUserActionResponse(BaseModel):
    success: bool = True

    model_config = ConfigDict(extra="forbid")


class AdminUserDeleteResponse(BaseModel):
    success: bool = True
    deleted_user_id: UUID
    deleted_email: str
    deleted_counts: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class StorageCleanupJobResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    bucket: str
    object_key: str
    status: str
    attempts: int
    last_error: str | None
    next_attempt_at: datetime
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class StorageCleanupListResponse(BaseModel):
    items: list[StorageCleanupJobResponse]

    model_config = ConfigDict(extra="forbid")


class AdminTenantStatsResponse(BaseModel):
    users_count: int
    active_users_count: int
    documents_count: int
    queries_count: int
    collections_count: int

    model_config = ConfigDict(extra="forbid")


class AdminTenantSummaryResponse(BaseModel):
    tenant_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    status: str = "active"
    last_activity_at: datetime | None = None
    stats: AdminTenantStatsResponse

    model_config = ConfigDict(extra="forbid")


class AdminTenantListResponse(BaseModel):
    items: list[AdminTenantSummaryResponse]

    model_config = ConfigDict(extra="forbid")


class AdminDocumentStatusCountResponse(BaseModel):
    status: str
    count: int

    model_config = ConfigDict(extra="forbid")


class AdminDocumentTenantSummaryResponse(BaseModel):
    tenant_id: UUID
    documents_count: int
    storage_bytes: int
    quarantined_count: int
    status_counts: list[AdminDocumentStatusCountResponse] = Field(default_factory=list)
    error_count: int

    model_config = ConfigDict(extra="forbid")


class AdminDocumentSummaryListResponse(BaseModel):
    items: list[AdminDocumentTenantSummaryResponse]

    model_config = ConfigDict(extra="forbid")


class BreakGlassGrantRequest(BaseModel):
    target_user_id: UUID
    target_tenant_id: UUID
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: str | None = Field(default=None, max_length=128)
    reason: str = Field(min_length=12, max_length=1000)
    duration_minutes: int = Field(default=30, ge=1, le=60)

    model_config = ConfigDict(extra="forbid")


class BreakGlassGrantResponse(BaseModel):
    grant_id: UUID
    tenant_id: UUID
    actor_user_id: UUID
    target_user_id: UUID
    resource_type: str
    resource_id: str | None
    status: str
    expires_at: datetime

    model_config = ConfigDict(extra="forbid")


class BreakGlassRevokeResponse(BaseModel):
    success: bool = True
    grant_id: UUID

    model_config = ConfigDict(extra="forbid")
