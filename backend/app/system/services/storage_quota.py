"""Role-based tenant storage plans and safe quota accounting."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import String as SqlString
from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from app.auth.models.role import Role
from app.auth.models.tenant import Tenant
from app.auth.models.user_role import UserRole
from app.auth.roles import canonicalize_role_names
from app.core.config import get_settings
from app.deepspace.models.agent_activity import AgentActivity
from app.deepspace.models.agent_memory import AgentMemory
from app.deepspace.models.agent_memory_preferences import AgentMemoryPreferences
from app.deepspace.models.agent_runtime import (
    DeepSpaceAgentRun,
    DeepSpaceAgentStep,
    DeepSpaceRunEvent,
)
from app.deepspace.models.agent_todo import AgentTodo
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.conversation_context_summary import DeepSpaceConversationContextSummary
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.deepspace.models.message import Message as DeepSpaceMessage
from app.deepspace.models.message_version import MessageVersion as DeepSpaceMessageVersion
from app.deepspace.models.mission_snapshot import DeepSpaceMissionSnapshot
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.models.request_metric import DeepSpaceRequestMetric
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.models.workspace_folder import DeepSpaceWorkspaceFolder
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.collection import CollectionChatMessage, DocumentCollection
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.integrations.models.connector import Connector
from app.integrations.models.connector_secret import ConnectorSecret
from app.integrations.models.mcp_server import MCPEvent, MCPOAuthToken, MCPServer
from app.platform.database.session import set_db_tenant_context
from app.providers.models.provider_config import ProviderConfig
from app.providers.models.provider_secret import ProviderSecret
from app.query.models.query import Query
from app.system.models.storage_lifecycle import StorageQuotaReservation
from app.system.models.tenant_storage_allocation import TenantStorageAllocation
from app.system.models.usage_record import UsageRecord
from app.system.services.metrics_service import STORAGE_QUOTA_RESERVATIONS_TOTAL

BYTES_PER_MB: Final[int] = 1024 * 1024
FREE_STORAGE_BYTES: Final[int] = 500 * BYTES_PER_MB
EDITOR_STORAGE_BYTES: Final[int] = 1024 * BYTES_PER_MB
EMBEDDING_BYTES_PER_VECTOR: Final[int] = 4 * int(get_settings().embedding_dimension)
ACTIVE_UPLOAD_STATUSES: Final[tuple[str, ...]] = (
    "pending",
    "uploading",
    "queued",
    "processing",
)


@dataclass(frozen=True, slots=True)
class StoragePlan:
    id: str
    name: str
    storage_limit_bytes: int
    description: str
    features: tuple[str, ...]
    admin_only: bool = False


@dataclass(frozen=True, slots=True)
class StorageUsage:
    documents_bytes: int
    library_bytes: int
    artifacts_bytes: int
    pending_upload_bytes: int
    account_data_bytes: int = 0

    @property
    def total_bytes(self) -> int:
        return (
            self.documents_bytes
            + self.library_bytes
            + self.artifacts_bytes
            + self.pending_upload_bytes
            + self.account_data_bytes
        )


@dataclass(frozen=True, slots=True)
class StorageMetric:
    """A tenant-scoped storage inventory item.

    Some database-backed records are reported as logical text bytes and are
    intentionally not included in the object-storage quota until a physical
    database metering policy exists. This distinction prevents the UI from
    pretending that a character count is PostgreSQL disk usage.
    """

    key: str
    label: str
    description: str
    bytes: int
    record_count: int
    included_in_quota: bool
    measurement: str
    tokens: int | None = None


class StorageQuotaExceededError(ValueError):
    """Raised before a new durable tenant-owned object would exceed its plan."""

    def __init__(self, *, plan: StoragePlan, usage_bytes: int, requested_bytes: int) -> None:
        self.plan = plan
        self.usage_bytes = max(0, usage_bytes)
        self.requested_bytes = max(0, requested_bytes)
        super().__init__(
            f"{plan.name} storage limit reached. "
            f"Available: {max(0, plan.storage_limit_bytes - self.usage_bytes)} bytes."
        )


class StorageReservationError(ValueError):
    """Raised when an atomic in-flight capacity reservation cannot fit."""


PLANS: Final[dict[str, StoragePlan]] = {
    "free": StoragePlan(
        id="free",
        name="Free",
        storage_limit_bytes=FREE_STORAGE_BYTES,
        description="Essential AverQel workspace storage.",
        features=(
            "Tags and folders",
            "Documents and collections",
            "DeepSpace workspace",
            "Tenant-isolated storage",
            "500 MB shared workspace storage",
        ),
    ),
    "editor": StoragePlan(
        id="editor",
        name="Editor",
        storage_limit_bytes=EDITOR_STORAGE_BYTES,
        description="Expanded workspace storage for editor accounts.",
        features=(
            "Everything in Free",
            "Saved views",
            "Classification rules",
            "Automation schedules",
            "Tenant-isolated storage",
            "1 GB shared workspace storage",
        ),
    ),
    "admin": StoragePlan(
        id="admin",
        name="Admin",
        storage_limit_bytes=EDITOR_STORAGE_BYTES,
        description="Administrative workspace access and 1 GB storage.",
        features=(
            "Everything in Editor",
            "Webhooks and delivery history",
            "Smart collections",
            "Advanced document operations",
            "Administrative workspace controls",
            "Tenant-isolated storage",
            "1 GB shared workspace storage",
        ),
        admin_only=True,
    ),
}


def resolve_storage_plan(roles: object) -> StoragePlan:
    raw_roles = roles if isinstance(roles, list | set | tuple | frozenset) else ()
    canonical_roles = canonicalize_role_names(tuple(str(role) for role in raw_roles))
    if "admin" in canonical_roles:
        return PLANS["admin"]
    if "editor" in canonical_roles:
        return PLANS["editor"]
    return PLANS["free"]


class StorageQuotaService:
    """Compute tenant usage and enforce plan capacity at write boundaries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def estimate_bytes(*values: Any) -> int:
        """Estimate durable payload bytes without exposing or persisting secrets."""
        total = 0
        for value in values:
            if value is None:
                continue
            if isinstance(value, bytes):
                total += len(value)
                continue
            if isinstance(value, str):
                total += len(value.encode("utf-8"))
                continue
            total += len(
                json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode(
                    "utf-8"
                )
            )
        return total

    def _exact_usage(self, *, tenant_id: uuid.UUID) -> StorageUsage:
        document_bytes = self._sum(
            select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
            )
        )
        library_bytes = self._sum(
            select(func.coalesce(func.sum(DeepSpaceWorkspaceFile.size_bytes), 0)).where(
                DeepSpaceWorkspaceFile.tenant_id == tenant_id,
            )
        )
        artifacts_bytes = self._sum(
            select(func.coalesce(func.sum(DeepSpaceMediaArtifact.size_bytes), 0)).where(
                DeepSpaceMediaArtifact.tenant_id == tenant_id,
                DeepSpaceMediaArtifact.status != "deleted",
            )
        )
        pending_upload_bytes = self._sum(
            select(func.coalesce(func.sum(DeepSpaceLibraryUpload.expected_size), 0)).where(
                DeepSpaceLibraryUpload.tenant_id == tenant_id,
                DeepSpaceLibraryUpload.status.in_(ACTIVE_UPLOAD_STATUSES),
            )
        )
        return StorageUsage(
            documents_bytes=document_bytes,
            library_bytes=library_bytes,
            artifacts_bytes=artifacts_bytes,
            pending_upload_bytes=pending_upload_bytes,
        )

    def usage(self, *, tenant_id: uuid.UUID) -> StorageUsage:
        """Return the live logical quota usage for one tenant."""
        exact = self._exact_usage(tenant_id=tenant_id)
        inventory = self.metrics(tenant_id=tenant_id)
        exact_keys = {"documents", "library", "artifacts", "pending_uploads"}
        account_data_bytes = sum(
            metric.bytes
            for metric in inventory
            if metric.included_in_quota and metric.key not in exact_keys
        )
        return StorageUsage(
            documents_bytes=exact.documents_bytes,
            library_bytes=exact.library_bytes,
            artifacts_bytes=exact.artifacts_bytes,
            pending_upload_bytes=exact.pending_upload_bytes,
            account_data_bytes=account_data_bytes,
        )

    def metrics(self, *, tenant_id: uuid.UUID) -> tuple[StorageMetric, ...]:
        """Return safe tenant-scoped inventory metrics for the Storage page."""
        usage = self._exact_usage(tenant_id=tenant_id)
        collection_metric = self._collection_index_metric(tenant_id=tenant_id)
        return (
            StorageMetric(
                key="documents",
                label="Uploaded documents",
                description="Original document objects uploaded for this tenant.",
                bytes=usage.documents_bytes,
                record_count=self._count(Document, tenant_id),
                included_in_quota=True,
                measurement="Exact object size",
            ),
            StorageMetric(
                key="library",
                label="DeepSpace Library",
                description="Current user and agent-created Library files.",
                bytes=usage.library_bytes,
                record_count=self._count(DeepSpaceWorkspaceFile, tenant_id),
                included_in_quota=True,
                measurement="Exact logical file size",
            ),
            StorageMetric(
                key="artifacts",
                label="Generated artifacts",
                description="Saved charts, media, and other DeepSpace artifacts.",
                bytes=usage.artifacts_bytes,
                record_count=self._count(DeepSpaceMediaArtifact, tenant_id),
                included_in_quota=True,
                measurement="Exact object size",
            ),
            StorageMetric(
                key="pending_uploads",
                label="Pending uploads",
                description="Reserved space for uploads that have not finished yet.",
                bytes=usage.pending_upload_bytes,
                record_count=self._count(
                    DeepSpaceLibraryUpload,
                    tenant_id,
                    status_in=ACTIVE_UPLOAD_STATUSES,
                ),
                included_in_quota=True,
                measurement="Exact reserved upload size",
            ),
            self._chat_history_metric(tenant_id=tenant_id),
            self._text_metric(
                key="grounded_queries",
                label="Grounded query history",
                description="Saved grounded questions, generated answers, and normalized query text.",
                model=Query,
                columns=(
                    Query.query_text,
                    Query.normalized_query,
                    Query.answer,
                    cast(Query.filters, Text),
                ),
                tenant_id=tenant_id,
                included_in_quota=True,
                measurement="Estimated logical saved text bytes",
            ),
            self._text_metric(
                key="memory",
                label="Saved memory",
                description="Durable DeepSpace memory values and keys.",
                model=AgentMemory,
                columns=(
                    AgentMemory.key,
                    AgentMemory.value,
                    cast(AgentMemory.metadata_json, Text),
                    cast(AgentMemory.tags, Text),
                ),
                tenant_id=tenant_id,
                extra_models=(
                    (
                        AgentMemoryPreferences,
                        (cast(AgentMemoryPreferences.automatic_capture_enabled, Text),),
                    ),
                ),
                included_in_quota=True,
                measurement="Estimated logical text and metadata bytes",
            ),
            collection_metric,
            self._text_metric(
                key="activity_and_runs",
                label="Agent activity and run history",
                description="Tool activity descriptions, run steps, and reconnectable event frames.",
                model=AgentActivity,
                columns=(AgentActivity.description, cast(AgentActivity.metadata_json, Text)),
                tenant_id=tenant_id,
                extra_models=(
                    (
                        DeepSpaceAgentRun,
                        (cast(DeepSpaceAgentRun.checkpoint, Text), DeepSpaceAgentRun.last_error),
                    ),
                    (
                        DeepSpaceAgentStep,
                        (
                            DeepSpaceAgentStep.step_type,
                            DeepSpaceAgentStep.tool_name,
                            cast(DeepSpaceAgentStep.input_json, Text),
                            cast(DeepSpaceAgentStep.result_json, Text),
                        ),
                    ),
                    (DeepSpaceRunEvent, (DeepSpaceRunEvent.frame,)),
                    (
                        DeepSpaceConversationContextSummary,
                        (
                            DeepSpaceConversationContextSummary.summary_text,
                            cast(DeepSpaceConversationContextSummary.summary_json, Text),
                        ),
                    ),
                    (
                        DeepSpaceRequestMetric,
                        (
                            DeepSpaceRequestMetric.provider_type,
                            DeepSpaceRequestMetric.model_name,
                            DeepSpaceRequestMetric.error_code,
                            cast(DeepSpaceRequestMetric.metadata_json, Text),
                        ),
                    ),
                    (
                        DeepSpaceMissionSnapshot,
                        (
                            DeepSpaceMissionSnapshot.status,
                            cast(DeepSpaceMissionSnapshot.payload, Text),
                        ),
                    ),
                ),
                included_in_quota=True,
                measurement="Estimated logical text and JSON bytes",
            ),
            self._text_metric(
                key="queues_and_tasks",
                label="Queues and task records",
                description="Queued prompts and durable task error/status records.",
                model=DeepSpaceQueuedTurn,
                columns=(
                    DeepSpaceQueuedTurn.prompt,
                    DeepSpaceQueuedTurn.error,
                    cast(DeepSpaceQueuedTurn.roles_json, Text),
                    cast(DeepSpaceQueuedTurn.permissions_json, Text),
                ),
                tenant_id=tenant_id,
                extra_models=(
                    (
                        AgentTodo,
                        (
                            AgentTodo.content,
                            AgentTodo.active_form,
                            cast(AgentTodo.metadata_json, Text),
                        ),
                    ),
                ),
                included_in_quota=True,
                measurement="Estimated logical text and JSON bytes",
            ),
            self._text_metric(
                key="workspace_structure",
                label="Workspace structure",
                description="Folders and workspace organization metadata.",
                model=DeepSpaceWorkspaceFolder,
                columns=(DeepSpaceWorkspaceFolder.name,),
                tenant_id=tenant_id,
                included_in_quota=True,
                measurement="Estimated logical metadata bytes",
            ),
            self._text_metric(
                key="providers_and_connections",
                label="Provider and MCP profiles",
                description="Provider profiles, MCP servers, connectors, and protected connection records.",
                model=ProviderConfig,
                columns=(
                    ProviderConfig.display_name,
                    ProviderConfig.provider_type,
                    ProviderConfig.auth_mode,
                    ProviderConfig.api_base_url,
                    ProviderConfig.default_chat_model,
                    ProviderConfig.default_embedding_model,
                    ProviderConfig.default_reranker_model,
                ),
                tenant_id=tenant_id,
                extra_models=(
                    (
                        MCPServer,
                        (
                            MCPServer.name,
                            MCPServer.transport,
                            MCPServer.status,
                            cast(MCPServer.config, Text),
                            cast(MCPServer.account_identity, Text),
                            MCPServer.last_error,
                        ),
                    ),
                    (MCPEvent, (MCPEvent.event_type, cast(MCPEvent.payload, Text))),
                    (
                        MCPOAuthToken,
                        (
                            MCPOAuthToken.secret_ciphertext,
                            MCPOAuthToken.secret_nonce,
                            MCPOAuthToken.secret_kid,
                            cast(MCPOAuthToken.granted_scopes, Text),
                        ),
                    ),
                    (
                        Connector,
                        (
                            Connector.name,
                            Connector.sync_frequency,
                            Connector.last_error,
                            cast(Connector.config, Text),
                        ),
                    ),
                    (
                        ConnectorSecret,
                        (
                            ConnectorSecret.secret_ciphertext,
                            ConnectorSecret.secret_nonce,
                            ConnectorSecret.secret_kid,
                            cast(ConnectorSecret.metadata_json, Text),
                        ),
                    ),
                    (
                        ProviderSecret,
                        (
                            ProviderSecret.secret_ciphertext,
                            ProviderSecret.secret_nonce,
                            ProviderSecret.secret_kid,
                        ),
                    ),
                ),
                included_in_quota=True,
                measurement="Estimated logical metadata and encrypted-payload bytes; secret values are never exposed",
            ),
            StorageMetric(
                key="token_usage",
                label="Model token usage",
                description="Token activity is shown for transparency, not as file storage.",
                bytes=0,
                record_count=self._count(UsageRecord, tenant_id),
                included_in_quota=False,
                measurement="Token count, not storage bytes",
                tokens=self._sum_column(UsageRecord, UsageRecord.total_tokens, tenant_id),
            ),
        )

    def ensure_capacity(
        self,
        *,
        tenant_id: uuid.UUID,
        roles: object = (),
        user_id: uuid.UUID | None = None,
        additional_bytes: int,
        replacing_bytes: int = 0,
    ) -> StorageUsage:
        """Lock the tenant row, then reject a write that would exceed its plan.

        The tenant-row lock closes the check/write race for the existing
        request transaction. It does not alter any existing tenant data.
        """
        safe_additional = max(0, int(additional_bytes))
        safe_replacing = max(0, int(replacing_bytes))
        set_db_tenant_context(self.db, tenant_id)
        self.db.execute(
            select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        ).scalar_one()
        plan = (
            resolve_storage_plan(roles)
            if roles
            else self.plan_for_user(tenant_id=tenant_id, user_id=user_id)
        )
        allocation = self.ensure_allocation(tenant_id=tenant_id, requested_plan=plan)
        usage = self.usage(tenant_id=tenant_id)
        effective_usage = max(0, usage.total_bytes - safe_replacing)
        allocated_plan = PLANS.get(allocation.plan_id, plan)
        if effective_usage + safe_additional > allocation.allocated_bytes:
            raise StorageQuotaExceededError(
                plan=allocated_plan,
                usage_bytes=effective_usage,
                requested_bytes=safe_additional,
            )
        allocation.measured_bytes = effective_usage
        allocation.measured_at = datetime.now(UTC)
        return usage

    def reserve_capacity(
        self,
        *,
        tenant_id: uuid.UUID,
        reservation_key: str,
        reserved_bytes: int,
        roles: object = (),
        user_id: uuid.UUID | None = None,
        ttl_seconds: int = 900,
    ) -> StorageQuotaReservation:
        """Reserve bytes atomically for a multi-step write.

        The allocation row is locked for the whole transaction. Repeating the
        same key is idempotent while its reservation is active, which lets
        retries safely reuse a reservation instead of double-counting it.
        The caller owns commit/rollback; this method never commits payload
        work on its own.
        """
        key = str(reservation_key).strip()
        amount = max(0, int(reserved_bytes))
        if not key or len(key) > 255:
            raise StorageReservationError("A bounded reservation key is required.")
        if amount <= 0:
            raise StorageReservationError("Reserved bytes must be greater than zero.")
        ttl = max(1, min(int(ttl_seconds), 24 * 60 * 60))
        set_db_tenant_context(self.db, tenant_id)
        self.db.execute(
            select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        ).scalar_one()
        plan = (
            resolve_storage_plan(roles)
            if roles
            else self.plan_for_user(tenant_id=tenant_id, user_id=user_id)
        )
        allocation = self.ensure_allocation(tenant_id=tenant_id, requested_plan=plan)
        now = datetime.now(UTC)
        existing = self.db.execute(
            select(StorageQuotaReservation)
            .where(
                StorageQuotaReservation.tenant_id == tenant_id,
                StorageQuotaReservation.reservation_key == key,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if existing is not None and existing.status == "active" and existing.expires_at > now:
            return existing
        if existing is not None and existing.status == "active":
            existing.status = "expired"
            existing.released_at = now

        self.db.execute(
            StorageQuotaReservation.__table__.update()
            .where(
                StorageQuotaReservation.tenant_id == tenant_id,
                StorageQuotaReservation.status == "active",
                StorageQuotaReservation.expires_at <= now,
            )
            .values(status="expired", released_at=now)
        )
        reserved = self.db.execute(
            select(func.coalesce(func.sum(StorageQuotaReservation.reserved_bytes), 0)).where(
                StorageQuotaReservation.tenant_id == tenant_id,
                StorageQuotaReservation.status == "active",
                StorageQuotaReservation.expires_at > now,
            )
        ).scalar_one()
        usage = self.usage(tenant_id=tenant_id)
        if usage.total_bytes + int(reserved or 0) + amount > allocation.allocated_bytes:
            STORAGE_QUOTA_RESERVATIONS_TOTAL.labels("rejected").inc()
            raise StorageQuotaExceededError(
                plan=PLANS.get(allocation.plan_id, plan),
                usage_bytes=usage.total_bytes + int(reserved or 0),
                requested_bytes=amount,
            )
        if existing is None:
            existing = StorageQuotaReservation(
                tenant_id=tenant_id,
                owner_user_id=user_id,
                reservation_key=key,
                reserved_bytes=amount,
                status="active",
                expires_at=now + timedelta(seconds=ttl),
            )
            self.db.add(existing)
        else:
            existing.owner_user_id = user_id or existing.owner_user_id
            existing.reserved_bytes = amount
            existing.status = "active"
            existing.expires_at = now + timedelta(seconds=ttl)
            existing.released_at = None
        self.db.flush()
        STORAGE_QUOTA_RESERVATIONS_TOTAL.labels("reserved").inc()
        return existing

    def release_capacity(
        self, *, tenant_id: uuid.UUID, reservation_key: str, status: str = "released"
    ) -> bool:
        """Release or commit a reservation idempotently inside the caller transaction."""
        if status not in {"released", "committed"}:
            raise StorageReservationError("Reservation status must be released or committed.")
        set_db_tenant_context(self.db, tenant_id)
        reservation = self.db.execute(
            select(StorageQuotaReservation)
            .where(
                StorageQuotaReservation.tenant_id == tenant_id,
                StorageQuotaReservation.reservation_key == str(reservation_key),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if reservation is None:
            return False
        if reservation.status == "active":
            reservation.status = status
            reservation.released_at = datetime.now(UTC)
            STORAGE_QUOTA_RESERVATIONS_TOTAL.labels(status).inc()
        return True

    def ensure_allocation(
        self,
        *,
        tenant_id: uuid.UUID,
        requested_plan: StoragePlan,
    ) -> TenantStorageAllocation:
        """Create or safely upgrade the durable tenant allocation."""
        self.db.execute(
            select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        ).scalar_one()
        allocation = self.db.execute(
            select(TenantStorageAllocation)
            .where(TenantStorageAllocation.tenant_id == tenant_id)
            .with_for_update()
        ).scalar_one_or_none()
        if allocation is None:
            allocation = TenantStorageAllocation(
                tenant_id=tenant_id,
                plan_id=requested_plan.id,
                allocated_bytes=requested_plan.storage_limit_bytes,
            )
            self.db.add(allocation)
            self.db.flush()
            return allocation
        current = PLANS.get(allocation.plan_id, PLANS["free"])
        if requested_plan.storage_limit_bytes > current.storage_limit_bytes:
            allocation.plan_id = requested_plan.id
            allocation.allocated_bytes = requested_plan.storage_limit_bytes
        return allocation

    def plan_for_user(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None) -> StoragePlan:
        if user_id is None:
            return PLANS["free"]
        roles = self.db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.tenant_id == tenant_id, UserRole.user_id == user_id)
        ).scalars()
        return resolve_storage_plan(tuple(roles))

    def _sum(self, statement) -> int:
        value = self.db.execute(statement).scalar_one()
        return max(0, int(value or 0))

    def _count(
        self, model, tenant_id: uuid.UUID, *, status_in: tuple[str, ...] | None = None
    ) -> int:
        conditions = [model.tenant_id == self._tenant_value(model, tenant_id)]
        if status_in is not None:
            conditions.append(model.status.in_(status_in))
        value = self.db.execute(
            select(func.count()).select_from(model).where(*conditions)
        ).scalar_one()
        return max(0, int(value or 0))

    def _sum_column(self, model, column, tenant_id: uuid.UUID) -> int:
        value = self.db.execute(
            select(func.coalesce(func.sum(column), 0)).where(
                model.tenant_id == self._tenant_value(model, tenant_id)
            )
        ).scalar_one()
        return max(0, int(value or 0))

    def _text_metric(
        self,
        *,
        key: str,
        label: str,
        description: str,
        model,
        columns: tuple,
        tenant_id: uuid.UUID,
        included_in_quota: bool,
        measurement: str,
        extra_models: tuple[tuple[object, tuple], ...] = (),
    ) -> StorageMetric:
        byte_expression = sum(func.coalesce(func.length(column), 0) for column in columns)
        bytes_used = self._sum(
            select(func.coalesce(func.sum(byte_expression), 0)).where(
                model.tenant_id == self._tenant_value(model, tenant_id)
            )
        )
        record_count = self._count(model, tenant_id)
        for extra_model, extra_columns in extra_models:
            extra_expression = sum(
                func.coalesce(func.length(column), 0) for column in extra_columns
            )
            bytes_used += self._sum(
                select(func.coalesce(func.sum(extra_expression), 0)).where(
                    extra_model.tenant_id == self._tenant_value(extra_model, tenant_id)
                )
            )
            record_count += self._count(extra_model, tenant_id)
        return StorageMetric(
            key=key,
            label=label,
            description=description,
            bytes=bytes_used,
            record_count=record_count,
            included_in_quota=included_in_quota,
            measurement=measurement,
        )

    def _chat_history_metric(self, *, tenant_id: uuid.UUID) -> StorageMetric:
        """Measure chat rows through their conversation tenant ownership."""
        base = self._text_metric(
            key="chat_history",
            label="Chat history and notes",
            description="Conversation titles, notes, messages, and message versions.",
            model=Conversation,
            columns=(Conversation.title, Conversation.content_html),
            tenant_id=tenant_id,
            included_in_quota=True,
            measurement="Estimated logical text bytes",
        )
        message_bytes = self._joined_text_sum(
            DeepSpaceMessage,
            (DeepSpaceMessage.content, cast(DeepSpaceMessage.metadata_json, Text)),
            Conversation,
            DeepSpaceMessage.conversation_id == Conversation.id,
            tenant_id,
        )
        message_count = self._joined_count(
            DeepSpaceMessage,
            Conversation,
            DeepSpaceMessage.conversation_id == Conversation.id,
            tenant_id,
        )
        version_bytes = self._joined_text_sum(
            DeepSpaceMessageVersion,
            (DeepSpaceMessageVersion.content, cast(DeepSpaceMessageVersion.metadata_json, Text)),
            DeepSpaceMessage,
            DeepSpaceMessageVersion.message_id == DeepSpaceMessage.id,
            tenant_id,
            join_target=Conversation,
            join_target_condition=DeepSpaceMessage.conversation_id == Conversation.id,
        )
        version_count = self._joined_count(
            DeepSpaceMessageVersion,
            DeepSpaceMessage,
            DeepSpaceMessageVersion.message_id == DeepSpaceMessage.id,
            tenant_id,
            join_target=Conversation,
            join_target_condition=DeepSpaceMessage.conversation_id == Conversation.id,
        )
        return StorageMetric(
            key=base.key,
            label=base.label,
            description=base.description,
            bytes=base.bytes + message_bytes + version_bytes,
            record_count=base.record_count + message_count + version_count,
            included_in_quota=base.included_in_quota,
            measurement=base.measurement,
        )

    def _collection_index_metric(self, *, tenant_id: uuid.UUID) -> StorageMetric:
        """Measure collection metadata, indexed text, vectors, and collection chat."""
        base = self._text_metric(
            key="collections_and_index",
            label="Collections and search index",
            description="Collection metadata, indexed document chunks, embeddings, and collection chat.",
            model=DocumentChunk,
            columns=(DocumentChunk.content, cast(DocumentChunk.chunk_metadata, Text)),
            tenant_id=tenant_id,
            extra_models=(
                (DocumentCollection, (DocumentCollection.name, DocumentCollection.description)),
            ),
            included_in_quota=True,
            measurement="Estimated logical text, metadata, and vector bytes",
        )
        embedding_bytes = self._sum(
            select(func.count(ChunkEmbedding.id) * EMBEDDING_BYTES_PER_VECTOR).where(
                ChunkEmbedding.tenant_id == tenant_id
            )
        )
        chat_bytes = self._joined_text_sum(
            CollectionChatMessage,
            (CollectionChatMessage.message, CollectionChatMessage.reactions),
            DocumentCollection,
            CollectionChatMessage.collection_id == DocumentCollection.id,
            tenant_id,
            tenant_model=DocumentCollection,
        )
        chat_count = self._joined_count(
            CollectionChatMessage,
            DocumentCollection,
            CollectionChatMessage.collection_id == DocumentCollection.id,
            tenant_id,
            tenant_model=DocumentCollection,
        )
        return StorageMetric(
            key=base.key,
            label=base.label,
            description=base.description,
            bytes=base.bytes + embedding_bytes + chat_bytes,
            record_count=base.record_count + self._count(ChunkEmbedding, tenant_id) + chat_count,
            included_in_quota=True,
            measurement=base.measurement,
        )

    def _joined_text_sum(
        self,
        model,
        columns: tuple,
        join_model,
        join_condition,
        tenant_id: uuid.UUID,
        *,
        join_target=None,
        join_target_condition=None,
        tenant_model=None,
    ) -> int:
        expression = sum(func.coalesce(func.length(column), 0) for column in columns)
        statement = select(func.coalesce(func.sum(expression), 0)).select_from(model)
        statement = statement.join(join_model, join_condition)
        if join_target is not None:
            statement = statement.join(join_target, join_target_condition)
        owner_model = tenant_model or Conversation
        statement = statement.where(
            owner_model.tenant_id == self._tenant_value(owner_model, tenant_id)
        )
        return self._sum(statement)

    def _joined_count(
        self,
        model,
        join_model,
        join_condition,
        tenant_id: uuid.UUID,
        *,
        join_target=None,
        join_target_condition=None,
        tenant_model=None,
    ) -> int:
        statement = select(func.count()).select_from(model).join(join_model, join_condition)
        if join_target is not None:
            statement = statement.join(join_target, join_target_condition)
        owner_model = tenant_model or Conversation
        statement = statement.where(
            owner_model.tenant_id == self._tenant_value(owner_model, tenant_id)
        )
        value = self.db.execute(statement).scalar_one()
        return max(0, int(value or 0))

    @staticmethod
    def _tenant_value(model, tenant_id: uuid.UUID) -> uuid.UUID | str:
        """Support legacy DeepSpace tables whose tenant key is textual."""
        return str(tenant_id) if isinstance(model.tenant_id.type, SqlString) else tenant_id


def ensure_capacity_if_supported(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    additional_bytes: int,
    replacing_bytes: int = 0,
) -> StorageUsage | None:
    """Apply quota checks for real SQLAlchemy sessions while preserving pure unit doubles."""
    if not isinstance(db, Session):
        return None
    set_db_tenant_context(db, tenant_id)
    if db.execute(select(Tenant.id).where(Tenant.id == tenant_id)).scalar_one_or_none() is None:
        return None
    return StorageQuotaService(db).ensure_capacity(
        tenant_id=tenant_id,
        user_id=user_id,
        additional_bytes=additional_bytes,
        replacing_bytes=replacing_bytes,
    )
