from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

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
from app.models.ingestion.ingestion_job import IngestionJob
from app.models.query.comment import Comment
from app.models.query.conversation import Conversation
from app.models.query.message import Message
from app.models.query.message_version import MessageVersion
from app.models.query.pinned_finding import PinnedFinding
from app.models.query.query import Query
from app.models.query.query_citation import QueryCitation
from app.models.system.idempotency_key import IdempotencyKey
from app.documents.repositories.data_deletions import DataDeletionsRepository
from app.services.system.audit_service import AuditService
from app.services.system.metrics_service import observe_db_query
from app.services.system.storage_service import StorageService

logger = logging.getLogger(__name__)


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
        reason: str | None,
    ) -> DeletionRequestResult:
        row = DataDeletion(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            status="queued",
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
            details={"reason": reason or ""},
        )

        deletion_id = row.id
        status = row.status
        self.db.commit()
        return DeletionRequestResult(deletion_id=deletion_id, status=status)

    def get_status(
        self, *, tenant_id: uuid.UUID, deletion_id: uuid.UUID
    ) -> DataDeletion:
        row = self.repo.get_by_id(tenant_id=tenant_id, deletion_id=deletion_id)
        if row is None:
            raise ApiError(
                code="DATA_DELETION_NOT_FOUND",
                message="Deletion request was not found for tenant.",
                status_code=404,
            )
        return row

    def list_statuses(
        self, *, tenant_id: uuid.UUID, limit: int = 20
    ) -> list[DataDeletion]:
        return self.repo.list_by_tenant(tenant_id=tenant_id, limit=limit)

    def process_deletion(self, *, tenant_id: uuid.UUID, deletion_id: uuid.UUID) -> None:
        row = self.get_status(tenant_id=tenant_id, deletion_id=deletion_id)

        if row.status in {"completed", "processing"}:
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
                details={k: str(v) for k, v in result_counts.items()},
            )
            self.db.commit()

        except Exception as exc:  # noqa: BLE001
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
                error_message=str(exc),
            )
            self.audit.write_event(
                tenant_id=tenant_id,
                action="deletion.failed",
                resource_type="data_deletion",
                resource_id=str(row.id),
                actor_user_id=row.requested_by_user_id,
                status="failed",
                details={"error": str(exc)},
            )
            self.db.commit()
            raise

    def _purge_tenant_data(self, *, tenant_id: uuid.UUID) -> dict[str, int]:
        self.repo.apply_tenant_scope(tenant_id)

        with observe_db_query("deletion.fetch_storage_objects"):
            objects = list(
                self.db.execute(
                    select(Document.storage_bucket, Document.storage_object_key).where(
                        Document.tenant_id == tenant_id
                    )
                ).all()
            )

        for bucket, object_key in objects:
            try:
                self.storage.delete_object(
                    bucket=str(bucket), object_key=str(object_key)
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Data deletion object-storage cleanup failed.",
                    extra={
                        "tenant_id": str(tenant_id),
                        "bucket": str(bucket),
                        "object_key": str(object_key),
                    },
                    exc_info=True,
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
                select(func.count())
                .select_from(Comment)
                .where(Comment.tenant_id == tenant_id)
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
            queries_deleted = self.db.execute(
                delete(Query).where(Query.tenant_id == tenant_id)
            )
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
                delete(DocumentCollection).where(
                    DocumentCollection.tenant_id == tenant_id
                )
            )
            deleted_count = int(document_collections_deleted.rowcount or 0)  # type: ignore[attr-defined]
            if deleted_count != counts["document_collections"]:
                counts["document_collections"] = deleted_count

        return counts
