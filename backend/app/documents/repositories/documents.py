from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import func, select, update

from app.db.session import set_db_tenant_context
from app.documents.models.collection import CollectionDocument, CollectionPermission
from app.documents.models.document import Document
from app.repositories.system.base import BaseRepository
from app.ingestion.services.extractors.base import ExtractionResult
from app.services.system.metrics_service import observe_db_query

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class DocumentsRepository(BaseRepository):
    def _apply_bypass_scope(self) -> None:
        set_db_tenant_context(self.db, "bypass")

    def create(self, document: Document) -> Document:
        self.apply_tenant_scope(document.tenant_id)
        with observe_db_query("documents.create"):
            self.db.add(document)
            self.db.flush()
        return document

    def get_by_id(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        self.apply_tenant_scope(tenant_id)
        query = select(Document).where(
            Document.tenant_id == tenant_id,
            Document.id == document_id,
            Document.is_deleted.is_(False),
        )
        with observe_db_query("documents.get_by_id"):
            return self.db.execute(query).scalar_one_or_none()

    def get_accessible_by_id(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        include_quarantined: bool = False,
    ) -> Document | None:
        self.apply_tenant_scope(tenant_id)
        accessible_ids = self.get_accessible_document_ids(
            tenant_id=tenant_id,
            user_id=user_id,
            include_quarantined=include_quarantined,
        )
        if document_id not in accessible_ids:
            return None
        return self.get_by_id(tenant_id=tenant_id, document_id=document_id)

    def set_status(
        self, *, tenant_id: uuid.UUID, document: Document, status: str
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("documents.set_status"):
            document.status = status
            document.updated_at = datetime.now(tz=UTC)

    def set_extraction_metadata(
        self,
        *,
        tenant_id: uuid.UUID,
        document: Document,
        extraction: ExtractionResult,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("documents.set_extraction_metadata"):
            document.extraction_method = extraction.extraction_method
            document.extraction_coverage_score = extraction.coverage_score
            document.extraction_ocr_used = extraction.ocr_used
            document.extraction_vision_used = extraction.vision_used
            document.extraction_warnings = list(extraction.warnings)
            document.updated_at = datetime.now(tz=UTC)

    def count_by_tenant(self, *, tenant_id: uuid.UUID) -> int:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
            )
        )
        with observe_db_query("documents.count_by_tenant"):
            return self.db.execute(query).scalar() or 0

    def sum_storage_by_tenant(self, *, tenant_id: uuid.UUID) -> int:
        self.apply_tenant_scope(tenant_id)
        query = select(func.sum(Document.size_bytes)).where(
            Document.tenant_id == tenant_id,
            Document.is_deleted.is_(False),
        )
        with observe_db_query("documents.sum_storage_by_tenant"):
            return self.db.execute(query).scalar() or 0

    def count_quarantined_by_tenant(self, *, tenant_id: uuid.UUID) -> int:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
                Document.quarantined.is_(True),
            )
        )
        with observe_db_query("documents.count_quarantined_by_tenant"):
            return self.db.execute(query).scalar() or 0

    def count_error_by_tenant(self, *, tenant_id: uuid.UUID) -> int:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
                Document.status.in_(("failed", "dead_lettered", "needs_reingestion")),
            )
        )
        with observe_db_query("documents.count_error_by_tenant"):
            return self.db.execute(query).scalar() or 0

    def status_counts_by_tenant(self, *, tenant_id: uuid.UUID) -> dict[str, int]:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(Document.status, func.count())
            .where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
            )
            .group_by(Document.status)
            .order_by(Document.status.asc())
        )
        with observe_db_query("documents.status_counts_by_tenant"):
            return {str(status): int(count) for status, count in self.db.execute(query)}

    def list_by_tenant(
        self,
        *,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        with observe_db_query("documents.list_by_tenant"):
            return list(self.db.execute(query).scalars().all())

    def list_accessible_for_user(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        include_quarantined: bool = False,
    ) -> list[Document]:
        self.apply_tenant_scope(tenant_id)
        q_uploaded = select(Document.id).where(
            Document.tenant_id == tenant_id,
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        q_collected = (
            select(CollectionDocument.document_id)
            .join(Document, Document.id == CollectionDocument.document_id)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == CollectionDocument.collection_id,
            )
            .where(
                Document.tenant_id == tenant_id,
                CollectionPermission.user_id == user_id,
                CollectionPermission.role.in_(["member", "owner", "shared"]),
                Document.is_deleted.is_(False),
            )
        )
        if not include_quarantined:
            q_uploaded = q_uploaded.where(Document.quarantined.is_(False))
            q_collected = q_collected.where(Document.quarantined.is_(False))

        accessible_ids = sa.union(q_uploaded, q_collected).subquery()
        query = (
            select(Document)
            .join(accessible_ids, Document.id == accessible_ids.c.id)
            .where(
                Document.tenant_id == tenant_id,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        with observe_db_query("documents.list_accessible_for_user"):
            return list(self.db.execute(query).scalars().all())

    def list_by_ids(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[Document]:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return []

        query = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.id.in_(document_ids),
                Document.is_deleted.is_(False),
            )
            .order_by(Document.created_at.desc())
        )
        with observe_db_query("documents.list_by_ids"):
            return list(self.db.execute(query).scalars().all())

    def get_by_hash(
        self,
        *,
        tenant_id: uuid.UUID,
        sha256_hash: str,
        user_id: uuid.UUID | None = None,
    ) -> Document | None:
        self.apply_tenant_scope(tenant_id)
        query = select(Document).where(
            Document.tenant_id == tenant_id,
            Document.sha256_hash == sha256_hash,
            Document.is_deleted.is_(False),
        )
        if user_id is not None:
            query = query.where(Document.uploaded_by_user_id == user_id)
        with observe_db_query("documents.get_by_hash"):
            return self.db.execute(query).scalar_one_or_none()

    def get_latest_by_filename(
        self,
        *,
        tenant_id: uuid.UUID,
        filename: str,
        user_id: uuid.UUID | None = None,
    ) -> Document | None:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.filename == filename,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.version.desc())
            .limit(1)
        )
        if user_id is not None:
            query = query.where(Document.uploaded_by_user_id == user_id)
        with observe_db_query("documents.get_latest_by_filename"):
            return self.db.execute(query).scalar_one_or_none()

    def get_version_history(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[Document]:
        self.apply_tenant_scope(tenant_id)

        target = self.get_by_id(tenant_id=tenant_id, document_id=document_id)
        if not target:
            return []

        root = target
        while root.parent_document_id:
            parent = self.get_by_id(
                tenant_id=tenant_id, document_id=root.parent_document_id
            )
            if not parent:
                break
            root = parent

        query = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.filename == root.filename,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.version.desc())
        )
        with observe_db_query("documents.get_version_history"):
            return list(self.db.execute(query).scalars().all())

    def get_accessible_document_ids(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        include_quarantined: bool = False,
    ) -> set[uuid.UUID]:
        self.apply_tenant_scope(tenant_id)

        q_uploaded = select(Document.id).where(
            Document.tenant_id == tenant_id,
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        if not include_quarantined:
            q_uploaded = q_uploaded.where(Document.quarantined.is_(False))

        q_collected = (
            select(CollectionDocument.document_id)
            .join(Document, Document.id == CollectionDocument.document_id)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == CollectionDocument.collection_id,
            )
            .where(
                Document.tenant_id == tenant_id,
                CollectionPermission.user_id == user_id,
                Document.is_deleted.is_(False),
            )
        )
        if not include_quarantined:
            q_collected = q_collected.where(Document.quarantined.is_(False))

        query = sa.union(q_uploaded, q_collected)
        with observe_db_query("documents.get_accessible_document_ids"):
            return set(self.db.execute(query).scalars().all())

    def get_accessible_document_ids_global(
        self,
        *,
        user_id: uuid.UUID,
        include_quarantined: bool = False,
    ) -> set[uuid.UUID]:
        self._apply_bypass_scope()

        q_uploaded = select(Document.id).where(
            Document.uploaded_by_user_id == user_id,
            Document.is_deleted.is_(False),
        )
        if not include_quarantined:
            q_uploaded = q_uploaded.where(Document.quarantined.is_(False))

        q_collected = (
            select(CollectionDocument.document_id)
            .join(Document, Document.id == CollectionDocument.document_id)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == CollectionDocument.collection_id,
            )
            .where(
                CollectionPermission.user_id == user_id,
                CollectionPermission.role.in_(["member", "owner", "shared"]),
                Document.is_deleted.is_(False),
            )
        )
        if not include_quarantined:
            q_collected = q_collected.where(Document.quarantined.is_(False))

        query = sa.union(q_uploaded, q_collected)
        with observe_db_query("documents.get_accessible_document_ids_global"):
            return set(self.db.execute(query).scalars().all())

    def list_by_ids_global(
        self,
        *,
        document_ids: list[uuid.UUID],
    ) -> list[Document]:
        self._apply_bypass_scope()
        if not document_ids:
            return []
        query = (
            select(Document)
            .where(
                Document.id.in_(document_ids),
                Document.is_deleted.is_(False),
            )
            .order_by(Document.created_at.desc())
        )
        with observe_db_query("documents.list_by_ids_global"):
            return list(self.db.execute(query).scalars().all())

    def soft_delete_batch(
        self, *, tenant_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return

        query = (
            update(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.id.in_(document_ids),
            )
            .values(
                is_deleted=True,
                updated_at=datetime.now(tz=UTC),
            )
        )
        with observe_db_query("documents.soft_delete_batch"):
            self.db.execute(query)

    def set_processing_progress(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        progress: int,
        status: str | None = None,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        doc = self.get_by_id(tenant_id=tenant_id, document_id=document_id)
        if doc:
            doc.processing_progress = progress
            if status is not None:
                doc.status = status
            doc.updated_at = datetime.now(tz=UTC)

    def set_quarantined(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        quarantined: bool,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        doc = self.get_by_id(tenant_id=tenant_id, document_id=document_id)
        if doc:
            doc.quarantined = quarantined
            doc.updated_at = datetime.now(tz=UTC)
