"""Read-only source adapters for the tenant storage lifecycle index.

The adapters intentionally copy no payloads, secrets, private reasoning, or
object keys. Source tables remain authoritative; this index is only used for
activity, dependency protection, and reconciliation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.orm import Session

from app.auth.models.user import User
from app.deepspace.models.agent_memory import AgentMemory
from app.deepspace.models.agent_memory_preferences import AgentMemoryPreferences
from app.deepspace.models.agent_todo import AgentTodo
from app.deepspace.models.artifact_job import DeepSpaceArtifactJob
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.deepspace.models.message import Message
from app.deepspace.models.message_version import MessageVersion
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.collection import CollectionChatMessage, DocumentCollection
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.platform.database.session import set_db_tenant_context
from app.query.models.query import Query
from app.system.models.storage_lifecycle import (
    StorageLifecycleItem,
    StorageReconciliationRun,
)
from app.system.services.storage_lifecycle import StorageLifecycleService
from app.system.services.storage_quota import StorageQuotaService


def _uuid(value: object) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _at(row: object) -> datetime:
    value = getattr(row, "updated_at", None) or getattr(row, "created_at", None)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _size(*values: object) -> int:
    return StorageQuotaService.estimate_bytes(*values)


class StorageLifecycleAdapterService:
    """Populate and reconcile lifecycle identities without destructive writes."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.lifecycle = StorageLifecycleService(db)

    def sync_tenant(self, *, tenant_id: uuid.UUID) -> dict[str, int]:
        totals: dict[str, int] = {}
        self._documents(tenant_id, totals)
        self._library(tenant_id, totals)
        self._artifacts(tenant_id, totals)
        self._conversations(tenant_id, totals)
        self._memory(tenant_id, totals)
        self._queries(tenant_id, totals)
        self._collections(tenant_id, totals)
        self._queues(tenant_id, totals)
        self.db.flush()
        # Include identities created by the normal write-path activity hooks
        # (for example ``chat_history``) in the reconciliation total.
        grouped = self.db.execute(
            select(
                StorageLifecycleItem.category,
                func.coalesce(func.sum(StorageLifecycleItem.size_bytes), 0),
            )
            .where(StorageLifecycleItem.tenant_id == tenant_id)
            .group_by(StorageLifecycleItem.category)
        ).all()
        return {str(category): int(total or 0) for category, total in grouped}

    def reconcile_tenant(self, *, tenant_id: uuid.UUID) -> StorageReconciliationRun:
        started = datetime.now(UTC)
        # The maintenance worker runs under ``aks_app`` with RLS enabled;
        # establish the same tenant context used by normal API paths before
        # inserting the reconciliation record.
        set_db_tenant_context(self.db, tenant_id)
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"storage-reconciliation:{tenant_id}"},
        )
        run = StorageReconciliationRun(tenant_id=tenant_id, status="running", started_at=started)
        self.db.add(run)
        self.db.flush()
        try:
            adapter_totals = self.sync_tenant(tenant_id=tenant_id)
            metrics = {
                metric.key: metric.bytes
                for metric in StorageQuotaService(self.db).metrics(tenant_id=tenant_id)
                if metric.included_in_quota
            }
            category_to_metric = {
                "files": "documents",
                "library": "library",
                "artifacts": "artifacts",
                "chat_history": "chat_history",
                "memory": "memory",
                "queries": "grounded_queries",
                "collections": "collections",
                "queues": "queues_and_tasks",
            }
            comparison: dict[str, dict[str, int]] = {}
            mismatches = 0
            for category, measured in adapter_totals.items():
                quota_key = category_to_metric.get(category)
                if quota_key is None:
                    # Preserve unknown legacy metadata without turning it into
                    # an archive or quota mismatch signal.
                    continue
                quota_bytes = int(metrics.get(quota_key, 0))
                comparison[category] = {"lifecycle_bytes": measured, "quota_bytes": quota_bytes}
                if measured != quota_bytes:
                    mismatches += 1
            run.category_totals_json = comparison
            run.mismatch_count = mismatches
            run.status = "complete"
            run.completed_at = datetime.now(UTC)
            self.db.commit()
            return run
        except Exception as exc:
            self.db.rollback()
            run.status = "failed"
            run.category_totals_json = {"error": type(exc).__name__}
            run.completed_at = datetime.now(UTC)
            self.db.add(run)
            self.db.commit()
            raise

    def _record(
        self,
        tenant_id: uuid.UUID,
        totals: dict[str, int],
        *,
        category: str,
        row: object,
        source_type: str,
        size: int,
        owner: object | None = None,
        dependency: str | None = None,
    ) -> None:
        source_id = getattr(row, "id", None)
        if source_id is None:
            return
        owner_uuid = _uuid(owner)
        if owner_uuid is not None:
            owner_uuid = self.db.execute(
                select(User.id).where(User.id == owner_uuid, User.tenant_id == tenant_id)
            ).scalar_one_or_none()
        item = self.lifecycle.record_activity(
            tenant_id=tenant_id,
            category=category,
            source_type=source_type,
            source_id=str(source_id),
            activity_kind="reconciliation",
            size_bytes=size,
            owner_user_id=owner_uuid,
            dependency_group_id=dependency,
            at=_at(row),
            replace_size=True,
        )
        totals[category] = totals.get(category, 0) + max(0, int(item.size_bytes))

    def _rows(self, model: Any, tenant_id: uuid.UUID) -> list[Any]:
        value = (
            tenant_id
            if model not in {AgentMemory, AgentMemoryPreferences, AgentTodo}
            else str(tenant_id)
        )
        return list(self.db.execute(select(model).where(model.tenant_id == value)).scalars().all())

    def _db_size(self, model: Any, row_id: object, *columns: object) -> int:
        expression = sum(func.coalesce(func.length(column), 0) for column in columns)
        value: Any = self.db.execute(
            select(func.coalesce(expression, 0)).where(model.id == row_id)
        ).scalar_one()
        return max(0, int(value or 0))

    def _documents(self, tenant_id: uuid.UUID, totals: dict[str, int]) -> None:
        for row in self._rows(Document, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="files",
                row=row,
                source_type="document",
                size=int(getattr(row, "size_bytes", 0) or 0),
                owner=getattr(row, "owner_id", None),
            )

    def _library(self, tenant_id: uuid.UUID, totals: dict[str, int]) -> None:
        for row in self._rows(DeepSpaceWorkspaceFile, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="library",
                row=row,
                source_type="workspace_file",
                size=int(getattr(row, "size_bytes", 0) or 0),
                owner=getattr(row, "user_id", None),
                dependency=str(getattr(row, "conversation_id", "")),
            )

    def _artifacts(self, tenant_id: uuid.UUID, totals: dict[str, int]) -> None:
        for row in self._rows(DeepSpaceMediaArtifact, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="artifacts",
                row=row,
                source_type="media_artifact",
                size=int(getattr(row, "size_bytes", 0) or 0),
                owner=getattr(row, "user_id", None),
                dependency=str(getattr(row, "conversation_id", "")),
            )
        for row in self._rows(DeepSpaceArtifactJob, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="artifacts",
                row=row,
                source_type="artifact_job",
                size=_size(
                    getattr(row, "filename", None),
                    getattr(row, "content", None),
                    getattr(row, "metadata_json", None),
                ),
                owner=getattr(row, "user_id", None),
                dependency=str(getattr(row, "conversation_id", "")),
            )

    def _conversations(self, tenant_id: uuid.UUID, totals: dict[str, int]) -> None:
        for row in self._rows(Conversation, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="chat_history",
                row=row,
                source_type="conversation",
                size=self._db_size(
                    Conversation, row.id, Conversation.title, Conversation.content_html
                ),
                owner=getattr(row, "user_id", None),
            )
        messages = list(
            self.db.execute(
                select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Conversation.tenant_id == tenant_id)
            )
            .scalars()
            .all()
        )
        for row in messages:
            self._record(
                tenant_id,
                totals,
                category="chat_history",
                row=row,
                source_type="message",
                size=self._db_size(
                    Message,
                    row.id,
                    Message.content,
                    cast(Message.metadata_json, Text),
                ),
            )
        versions = list(
            self.db.execute(
                select(MessageVersion)
                .join(Message, Message.id == MessageVersion.message_id)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Conversation.tenant_id == tenant_id)
            )
            .scalars()
            .all()
        )
        for row in versions:
            self._record(
                tenant_id,
                totals,
                category="chat_history",
                row=row,
                source_type="message_version",
                size=self._db_size(
                    MessageVersion,
                    row.id,
                    MessageVersion.content,
                    cast(MessageVersion.metadata_json, Text),
                ),
            )

    def _memory(self, tenant_id: uuid.UUID, totals: dict[str, int]) -> None:
        for row in self._rows(AgentMemory, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="memory",
                row=row,
                source_type="agent_memory",
                size=self._db_size(
                    AgentMemory,
                    row.id,
                    AgentMemory.key,
                    AgentMemory.value,
                    cast(AgentMemory.metadata_json, Text),
                    cast(AgentMemory.tags, Text),
                ),
                owner=row.user_id,
                dependency=str(getattr(row, "conversation_id", "")) or None,
            )
        for row in self._rows(AgentMemoryPreferences, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="memory",
                row=row,
                source_type="memory_preferences",
                size=self._db_size(
                    AgentMemoryPreferences,
                    row.id,
                    cast(AgentMemoryPreferences.automatic_capture_enabled, Text),
                ),
                owner=row.user_id,
            )

    def _queries(self, tenant_id: uuid.UUID, totals: dict[str, int]) -> None:
        for row in self._rows(Query, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="queries",
                row=row,
                source_type="grounded_query",
                size=_size(row.query_text, row.normalized_query, row.filters, row.answer),
                owner=row.user_id,
            )

    def _collections(self, tenant_id: uuid.UUID, totals: dict[str, int]) -> None:
        for row in self._rows(DocumentCollection, tenant_id):
            size = _size(row.name, row.description)
            self._record(
                tenant_id,
                totals,
                category="collections",
                row=row,
                source_type="collection",
                size=size,
            )
        for row in self._rows(DocumentChunk, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="collections",
                row=row,
                source_type="document_chunk",
                size=_size(row.content, row.chunk_metadata),
                dependency=str(row.document_id),
            )
        for row in self._rows(ChunkEmbedding, tenant_id):
            # The vector itself is measured from the configured dimension;
            # values are never copied into the lifecycle registry.
            vector_size = len(getattr(row, "embedding", None) or ()) * 4
            self._record(
                tenant_id,
                totals,
                category="collections",
                row=row,
                source_type="chunk_embedding",
                size=vector_size + _size(row.provider, row.model),
                dependency=str(row.document_id),
            )
        chat_rows = list(
            self.db.execute(
                select(CollectionChatMessage)
                .join(
                    DocumentCollection, DocumentCollection.id == CollectionChatMessage.collection_id
                )
                .where(DocumentCollection.tenant_id == tenant_id)
            )
            .scalars()
            .all()
        )
        for row in chat_rows:
            self._record(
                tenant_id,
                totals,
                category="collections",
                row=row,
                source_type="collection_chat",
                size=_size(row.message, row.reactions),
                owner=row.user_id,
                dependency=str(row.collection_id),
            )

    def _queues(self, tenant_id: uuid.UUID, totals: dict[str, int]) -> None:
        for row in self._rows(DeepSpaceQueuedTurn, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="queues",
                row=row,
                source_type="queued_turn",
                size=self._db_size(
                    DeepSpaceQueuedTurn,
                    row.id,
                    DeepSpaceQueuedTurn.prompt,
                    DeepSpaceQueuedTurn.error,
                    cast(DeepSpaceQueuedTurn.roles_json, Text),
                    cast(DeepSpaceQueuedTurn.permissions_json, Text),
                ),
                owner=row.user_id,
                dependency=str(row.conversation_id),
            )
        for row in self._rows(AgentTodo, tenant_id):
            self._record(
                tenant_id,
                totals,
                category="queues",
                row=row,
                source_type="agent_todo",
                size=self._db_size(
                    AgentTodo,
                    row.id,
                    AgentTodo.content,
                    AgentTodo.active_form,
                    cast(AgentTodo.metadata_json, Text),
                ),
                owner=row.user_id,
                dependency=str(getattr(row, "thread_id", "")) or None,
            )
