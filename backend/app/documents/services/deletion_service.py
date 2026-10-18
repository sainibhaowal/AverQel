from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.collection import (
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
)
from app.documents.models.data_deletion import DataDeletion
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.documents.repositories.data_deletions import DataDeletionsRepository
from app.ingestion.models.ingestion_job import IngestionJob
from app.query.models.comment import Comment
from app.query.models.conversation import Conversation
from app.query.models.dataset_index import QueryDatasetIndex
from app.query.models.message import Message
from app.query.models.message_version import MessageVersion
from app.query.models.pinned_finding import PinnedFinding
from app.query.models.query import Query
from app.query.models.query_citation import QueryCitation
from app.system.models.idempotency_key import IdempotencyKey
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.services.audit_service import AuditService
from app.system.services.metrics_service import observe_db_query
from app.system.services.storage_service import StorageService

logger = logging.getLogger(__name__)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


@dataclass(slots=True)
class DeletionRequestResult:
    deletion_id: uuid.UUID
    status: str


class DeletionService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repo = DataDeletionsRepository(db)
        self.audit = AuditService(db)
        self.storage = StorageService(settings)

    def request_deletion(
        self,
        *,
        tenant_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
        reason: str,
    ) -> DeletionRequestResult:
        row = DataDeletion(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            status="awaiting_approval",
            scope="tenant_data",
            reason=reason,
            result_counts={},
        )
        self.repo.create(row=row)

        self.audit.write_event(
            tenant_id=tenant_id,
            action="deletion.requested",
            resource_type="data_deletion",
            resource_id=str(row.id),
            actor_user_id=requested_by_user_id,
        )

        deletion_id = row.id
        status = row.status
        self.db.commit()
        return DeletionRequestResult(deletion_id=deletion_id, status=status)

    def approve_deletion(
        self,
        *,
        tenant_id: uuid.UUID,
        deletion_id: uuid.UUID,
        approved_by_user_id: uuid.UUID,
    ) -> DeletionRequestResult:
        row = self.repo.get_by_id(tenant_id=tenant_id, deletion_id=deletion_id, for_update=True)
        if row is None:
            raise ApiError(
                code="DATA_DELETION_NOT_FOUND",
                message="Deletion request was not found for tenant.",
                status_code=404,
            )
        if row.requested_by_user_id == approved_by_user_id:
            raise ApiError(
                code="SECOND_APPROVER_REQUIRED",
                message="A different authorized administrator must approve this workspace deletion.",
                status_code=403,
            )
        if row.status != "awaiting_approval":
            raise ApiError(
                code="DATA_DELETION_NOT_AWAITING_APPROVAL",
                message="This deletion request is no longer awaiting approval.",
                status_code=409,
            )

        row.status = "queued"
        row.approved_by_user_id = approved_by_user_id
        row.approved_at = datetime.now(UTC)
        self.audit.write_event(
            tenant_id=tenant_id,
            action="deletion.approved",
            resource_type="data_deletion",
            resource_id=str(row.id),
            actor_user_id=approved_by_user_id,
        )
        self.db.commit()
        return DeletionRequestResult(deletion_id=row.id, status=row.status)

    def mark_enqueue_failed(
        self,
        *,
        tenant_id: uuid.UUID,
        deletion_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> None:
        row = self.get_status(tenant_id=tenant_id, deletion_id=deletion_id)
        self.repo.mark_failed(
            tenant_id=tenant_id,
            row=row,
            error_code="DELETION_QUEUE_UNAVAILABLE",
            error_message="Deletion request could not be queued. Retry when the service is available.",
        )
        self.audit.write_event(
            tenant_id=tenant_id,
            action="deletion.queue_failed",
            resource_type="data_deletion",
            resource_id=str(row.id),
            actor_user_id=actor_user_id,
            status="failed",
            details={"error_code": "DELETION_QUEUE_UNAVAILABLE"},
        )
        self.db.commit()

    def get_status(self, *, tenant_id: uuid.UUID, deletion_id: uuid.UUID) -> DataDeletion:
        row = self.repo.get_by_id(tenant_id=tenant_id, deletion_id=deletion_id)
        if row is None:
            raise ApiError(
                code="DATA_DELETION_NOT_FOUND",
                message="Deletion request was not found for tenant.",
                status_code=404,
            )
        return row

    def list_statuses(self, *, tenant_id: uuid.UUID, limit: int = 20) -> list[DataDeletion]:
        return self.repo.list_by_tenant(tenant_id=tenant_id, limit=limit)

    def process_deletion(self, *, tenant_id: uuid.UUID, deletion_id: uuid.UUID) -> None:
        row = self.get_status(tenant_id=tenant_id, deletion_id=deletion_id)

        if row.status in {"completed", "processing", "awaiting_approval"}:
            return

        if row.status == "queued" and (
            row.approved_by_user_id is None or row.approved_by_user_id == row.requested_by_user_id
        ):
            row.status = "awaiting_approval"
            row.approved_by_user_id = None
            row.approved_at = None
            self.audit.write_event(
                tenant_id=tenant_id,
                action="deletion.execution_blocked",
                resource_type="data_deletion",
                resource_id=str(row.id),
                actor_user_id=None,
                status="failed",
                details={"error_code": "SECOND_APPROVER_REQUIRED"},
            )
            self.db.commit()
            logger.warning(
                "Skipped workspace deletion task without a distinct administrator approval.",
                extra={"tenant_id": str(tenant_id), "deletion_id": str(row.id)},
            )
            return

        self.repo.mark_processing(tenant_id=tenant_id, row=row)
        self.db.commit()

        try:
            result_counts = self._purge_tenant_data(tenant_id=tenant_id)

            self.repo.mark_completed(
                tenant_id=tenant_id,
                row=row,
                result_counts=result_counts,
            )
            self.audit.write_event(
                tenant_id=tenant_id,
                action="deletion.completed",
                resource_type="data_deletion",
                resource_id=str(row.id),
                actor_user_id=row.requested_by_user_id,
                details={"scope": row.scope},
            )
            self.db.commit()

        except Exception:  # noqa: BLE001
            logger.exception(
                "Tenant deletion failed.",
                extra={
                    "tenant_id": str(tenant_id),
                    "deletion_id": str(row.id),
                },
            )
            self.repo.mark_failed(
                tenant_id=tenant_id,
                row=row,
                error_code="DELETION_FAILED",
                error_message="Deletion could not be completed. Contact support with the request ID.",
            )
            self.audit.write_event(
                tenant_id=tenant_id,
                action="deletion.failed",
                resource_type="data_deletion",
                resource_id=str(row.id),
                actor_user_id=row.requested_by_user_id,
                status="failed",
                details={"error_code": "DELETION_FAILED"},
            )
            self.db.commit()
            raise

    def _purge_tenant_data(self, *, tenant_id: uuid.UUID) -> dict[str, int]:
        self.repo.apply_tenant_scope(tenant_id)

        with observe_db_query("deletion.fetch_storage_objects"):
            objects = list(
                self.db.execute(
                    select(
                        Document.storage_bucket,
                        Document.storage_object_key,
                        Document.uploaded_by_user_id,
                    ).where(Document.tenant_id == tenant_id)
                ).all()
            )

        with observe_db_query("deletion.fetch_grounded_dataset_objects"):
            dataset_objects = list(
                self.db.execute(
                    select(
                        QueryDatasetIndex.derivative_bucket,
                        QueryDatasetIndex.derivative_object_key,
                        Document.uploaded_by_user_id,
                    )
                    .join(Document, Document.id == QueryDatasetIndex.document_id)
                    .where(
                        QueryDatasetIndex.tenant_id == tenant_id,
                        Document.tenant_id == tenant_id,
                    )
                ).all()
            )

        for bucket, object_key, owner_user_id in objects:
            try:
                self.storage.delete_object(
                    bucket=str(bucket), object_key=str(object_key), raise_on_error=True
                )
            except Exception:  # noqa: BLE001
                self.db.add(
                    StorageCleanupJob(
                        tenant_id=tenant_id,
                        owner_user_id=owner_user_id,
                        bucket=str(bucket),
                        object_key=str(object_key),
                        last_error="workspace_deletion_storage_cleanup_pending",
                    )
                )
                logger.warning(
                    "Workspace deletion object cleanup queued for retry.",
                    extra={
                        "tenant_id": str(tenant_id),
                    },
                )

        for bucket, object_key, owner_user_id in dataset_objects:
            if not bucket or not object_key:
                continue
            try:
                self.storage.delete_tenant_object(
                    tenant_id=tenant_id,
                    bucket=str(bucket),
                    object_key=str(object_key),
                    raise_on_error=True,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Tenant purge could not remove a Grounded Query derivative; queuing cleanup.",
                    extra={"tenant_id": str(tenant_id)},
                )
                self.db.add(
                    StorageCleanupJob(
                        tenant_id=tenant_id,
                        owner_user_id=owner_user_id,
                        bucket=str(bucket),
                        object_key=str(object_key),
                    )
                )

        counts: dict[str, int] = {}

        with observe_db_query("deletion.count_message_versions"):
            message_versions_count = self.db.execute(
                select(func.count())
                .select_from(MessageVersion)
                .join(Message, Message.id == MessageVersion.message_id)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Conversation.tenant_id == tenant_id)
            ).scalar_one()
            counts["message_versions"] = int(message_versions_count or 0)

        with observe_db_query("deletion.count_messages"):
            messages_count = self.db.execute(
                select(func.count())
                .select_from(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Conversation.tenant_id == tenant_id)
            ).scalar_one()
            counts["messages"] = int(messages_count or 0)

        with observe_db_query("deletion.count_conversations"):
            conversations_count = self.db.execute(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.tenant_id == tenant_id)
            ).scalar_one()
            counts["conversations"] = int(conversations_count or 0)

        with observe_db_query("deletion.count_collection_documents"):
            collection_documents_count = self.db.execute(
                select(func.count())
                .select_from(CollectionDocument)
                .join(
                    DocumentCollection,
                    DocumentCollection.id == CollectionDocument.collection_id,
                )
                .where(DocumentCollection.tenant_id == tenant_id)
            ).scalar_one()
            counts["collection_documents"] = int(collection_documents_count or 0)

        with observe_db_query("deletion.count_collection_permissions"):
            collection_permissions_count = self.db.execute(
                select(func.count())
                .select_from(CollectionPermission)
                .join(
                    DocumentCollection,
                    DocumentCollection.id == CollectionPermission.collection_id,
                )
                .where(DocumentCollection.tenant_id == tenant_id)
            ).scalar_one()
            counts["collection_permissions"] = int(collection_permissions_count or 0)

        with observe_db_query("deletion.count_document_collections"):
            document_collections_count = self.db.execute(
                select(func.count())
                .select_from(DocumentCollection)
                .where(DocumentCollection.tenant_id == tenant_id)
            ).scalar_one()
            counts["document_collections"] = int(document_collections_count or 0)

        with observe_db_query("deletion.count_comments"):
            comments_count = self.db.execute(
                select(func.count()).select_from(Comment).where(Comment.tenant_id == tenant_id)
            ).scalar_one()
            counts["comments"] = int(comments_count or 0)

        with observe_db_query("deletion.count_pinned_findings"):
            pinned_findings_count = self.db.execute(
                select(func.count())
                .select_from(PinnedFinding)
                .where(PinnedFinding.tenant_id == tenant_id)
            ).scalar_one()
            counts["pinned_findings"] = int(pinned_findings_count or 0)

        with observe_db_query("deletion.delete_query_citations"):
            query_citations_deleted = self.db.execute(
                delete(QueryCitation).where(QueryCitation.tenant_id == tenant_id)
            )
            counts["query_citations"] = int(query_citations_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_queries"):
            queries_deleted = self.db.execute(delete(Query).where(Query.tenant_id == tenant_id))
            counts["queries"] = int(queries_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_pinned_findings"):
            pinned_findings_deleted = self.db.execute(
                delete(PinnedFinding).where(PinnedFinding.tenant_id == tenant_id)
            )
            counts["pinned_findings"] = int(pinned_findings_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_comments"):
            comments_deleted = self.db.execute(
                delete(Comment).where(Comment.tenant_id == tenant_id)
            )
            counts["comments"] = int(comments_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_chunk_embeddings"):
            chunk_embeddings_deleted = self.db.execute(
                delete(ChunkEmbedding).where(ChunkEmbedding.tenant_id == tenant_id)
            )
            counts["chunk_embeddings"] = int(chunk_embeddings_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_document_chunks"):
            document_chunks_deleted = self.db.execute(
                delete(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id)
            )
            counts["document_chunks"] = int(document_chunks_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_ingestion_jobs"):
            ingestion_jobs_deleted = self.db.execute(
                delete(IngestionJob).where(IngestionJob.tenant_id == tenant_id)
            )
            counts["ingestion_jobs"] = int(ingestion_jobs_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_query_dataset_indexes"):
            dataset_indexes_deleted = self.db.execute(
                delete(QueryDatasetIndex).where(QueryDatasetIndex.tenant_id == tenant_id)
            )
            counts["query_dataset_indexes"] = int(dataset_indexes_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_documents"):
            documents_deleted = self.db.execute(
                delete(Document).where(Document.tenant_id == tenant_id)
            )
            counts["documents"] = int(documents_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_idempotency_keys"):
            idempotency_deleted = self.db.execute(
                delete(IdempotencyKey).where(IdempotencyKey.tenant_id == tenant_id)
            )
            counts["idempotency_keys"] = int(idempotency_deleted.rowcount or 0)  # type: ignore[attr-defined]

        with observe_db_query("deletion.delete_conversations"):
            conversations_deleted = self.db.execute(
                delete(Conversation).where(Conversation.tenant_id == tenant_id)
            )
            deleted_count = int(conversations_deleted.rowcount or 0)  # type: ignore[attr-defined]
            if deleted_count != counts["conversations"]:
                counts["conversations"] = deleted_count

        with observe_db_query("deletion.delete_document_collections"):
            document_collections_deleted = self.db.execute(
                delete(DocumentCollection).where(DocumentCollection.tenant_id == tenant_id)
            )
            deleted_count = int(document_collections_deleted.rowcount or 0)  # type: ignore[attr-defined]
            if deleted_count != counts["document_collections"]:
                counts["document_collections"] = deleted_count

        return counts
