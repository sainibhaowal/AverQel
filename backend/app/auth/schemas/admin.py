from __future__ import annotations

from datetime import datetime
from typing import Literal
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
    created_at: datetime

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
    reason: Literal["workspace_offboarding", "security_incident"]
    target_tenant_id: UUID | None = None
    target_confirmation: str = Field(min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid")


class DataDeletionRequestResponse(BaseModel):
    deletion_id: UUID
    status: str

    model_config = ConfigDict(extra="forbid")


class DataDeletionStatusResponse(BaseModel):
    deletion_id: UUID
    tenant_id: UUID
    status: str
    scope: str
    reason: str | None
    can_approve: bool = False
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


class AdminUserSummaryResponse(BaseModel):
    user_id: UUID
    tenant_id: UUID
    tenant_name: str | None = None
    email: str
    is_active: bool
    totp_enabled: bool
    roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AdminUserListResponse(BaseModel):
    items: list[AdminUserSummaryResponse]

    model_config = ConfigDict(extra="forbid")


class AdminUserDetailResponse(BaseModel):
    user: AdminUserSummaryResponse

    model_config = ConfigDict(extra="forbid")


class AdminStaffRoleUpdateRequest(BaseModel):
    roles: list[Literal["feedback_manager", "collection_moderator", "support_manager"]] = Field(
        default_factory=list, max_length=3
    )

    model_config = ConfigDict(extra="forbid")


class AdminUserActionResponse(BaseModel):
    success: bool = True

    model_config = ConfigDict(extra="forbid")


class AdminUserDeleteResponse(BaseModel):
    success: bool = True
    deleted_user_id: UUID

    model_config = ConfigDict(extra="forbid")


class StorageCleanupJobResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    status: str
    attempts: int
    next_attempt_at: datetime
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class StorageCleanupListResponse(BaseModel):
    items: list[StorageCleanupJobResponse]

    model_config = ConfigDict(extra="forbid")


class AdminTenantSummaryResponse(BaseModel):
    tenant_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    status: str = "active"
    seats_used: int

    model_config = ConfigDict(extra="forbid")


class AdminTenantListResponse(BaseModel):
    items: list[AdminTenantSummaryResponse]

    model_config = ConfigDict(extra="forbid")


class AdminDocumentTenantSummaryResponse(BaseModel):
    tenant_id: UUID
    quarantined_count: int
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
