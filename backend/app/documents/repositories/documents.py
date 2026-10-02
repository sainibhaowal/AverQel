from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import func, select, update

from app.documents.models.collection import CollectionDocument, CollectionPermission
from app.documents.models.document import Document
from app.documents.models.organization import DocumentShare, DocumentTagAssignment
from app.ingestion.services.extractors.base import ExtractionResult
from app.platform.database.session import set_db_tenant_context
from app.system.repositories.base import BaseRepository
from app.system.services.metrics_service import observe_db_query
from app.system.services.storage_lifecycle import StorageLifecycleService

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class DocumentsRepository(BaseRepository):
    def _apply_bypass_scope(self) -> None:
        set_db_tenant_context(self.db, "bypass")

    def create(self, document: Document) -> Document:
        self.apply_tenant_scope(document.tenant_id)
        with observe_db_query("documents.create"):
            self.db.add(document)
            self.db.flush()
        self._touch_lifecycle(document, activity_kind="document_created")
        return document

    def get_by_id(self, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
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

    def set_status(self, *, tenant_id: uuid.UUID, document: Document, status: str) -> None:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("documents.set_status"):
            document.status = status
            document.updated_at = datetime.now(tz=UTC)
        self._touch_lifecycle(document, activity_kind="document_status_changed")

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
        self._touch_lifecycle(document, activity_kind="document_extraction_changed")

    def _touch_lifecycle(self, document: Document, *, activity_kind: str) -> None:
        """Mark a durable document write as meaningful retention activity."""
        StorageLifecycleService(self.db).touch_source(
            tenant_id=document.tenant_id,
            category="files",
            source_type="document",
            source_id=str(document.id),
            owner_user_id=document.uploaded_by_user_id,
            activity_kind=activity_kind,
        )

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
        q_shared = select(DocumentShare.document_id).where(
            DocumentShare.tenant_id == tenant_id,
            DocumentShare.user_id == user_id,
        )
        if not include_quarantined:
            q_uploaded = q_uploaded.where(Document.quarantined.is_(False))
            q_collected = q_collected.where(Document.quarantined.is_(False))
            q_shared = q_shared.join(Document, Document.id == DocumentShare.document_id).where(
                Document.quarantined.is_(False)
            )

        accessible_ids = sa.union(q_uploaded, q_collected, q_shared).subquery()
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

    def search_accessible_for_user(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query_text: str | None = None,
        statuses: list[str] | None = None,
        content_type: str | None = None,
        ocr_used: bool | None = None,
        quarantined: bool | None = None,
        owner_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        tag_ids: list[uuid.UUID] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Document], int]:
        """Search only documents the user can already access within the tenant."""
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
        q_shared = select(DocumentShare.document_id).where(
            DocumentShare.tenant_id == tenant_id,
            DocumentShare.user_id == user_id,
        )
        accessible_ids = sa.union(q_uploaded, q_collected, q_shared).subquery()
        conditions = [
            Document.tenant_id == tenant_id,
            Document.is_deleted.is_(False),
            Document.id == accessible_ids.c.id,
        ]
        if query_text:
            conditions.append(Document.filename.ilike(f"%{query_text.strip()}%"))
        if statuses:
            conditions.append(Document.status.in_(statuses))
        if content_type:
            conditions.append(Document.content_type == content_type)
        if ocr_used is not None:
            conditions.append(Document.extraction_ocr_used.is_(ocr_used))
        if quarantined is not None:
            conditions.append(Document.quarantined.is_(quarantined))
        if owner_id is not None:
            conditions.append(Document.uploaded_by_user_id == owner_id)
        if created_from is not None:
            conditions.append(Document.created_at >= created_from)
        if created_to is not None:
            conditions.append(Document.created_at <= created_to)
        if tag_ids:
            tagged_documents = select(DocumentTagAssignment.document_id).where(
                DocumentTagAssignment.tenant_id == tenant_id,
                DocumentTagAssignment.tag_id.in_(tag_ids),
            )
            conditions.append(Document.id.in_(tagged_documents))

        base = select(Document).where(*conditions)
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = list(
            self.db.execute(
                base.order_by(Document.created_at.desc(), Document.id.desc())
                .offset(max(skip, 0))
                .limit(max(min(limit, 500), 1))
            )
            .scalars()
            .all()
        )
        return rows, total

    def list_accessible_duplicate_groups(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[list[Document]]:
        """Return duplicate groups without exposing inaccessible tenant rows."""
        rows, _ = self.search_accessible_for_user(
            tenant_id=tenant_id, user_id=user_id, skip=0, limit=500
        )
        groups: dict[str, list[Document]] = {}
        for document in rows:
            if document.sha256_hash:
                groups.setdefault(document.sha256_hash, []).append(document)
        return [group for group in groups.values() if len(group) > 1]

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
            parent = self.get_by_id(tenant_id=tenant_id, document_id=root.parent_document_id)
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
        q_shared = select(DocumentShare.document_id).where(
            DocumentShare.tenant_id == tenant_id,
            DocumentShare.user_id == user_id,
        )
        if not include_quarantined:
            q_collected = q_collected.where(Document.quarantined.is_(False))
            q_shared = q_shared.join(Document, Document.id == DocumentShare.document_id).where(
                Document.quarantined.is_(False)
            )

        query = sa.union(q_uploaded, q_collected, q_shared)
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
        q_shared = select(DocumentShare.document_id).where(DocumentShare.user_id == user_id)
        if not include_quarantined:
            q_collected = q_collected.where(Document.quarantined.is_(False))
            q_shared = q_shared.join(Document, Document.id == DocumentShare.document_id).where(
                Document.quarantined.is_(False)
            )

        query = sa.union(q_uploaded, q_collected, q_shared)
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

    def get_updated_at_by_ids_global(
        self,
        *,
        document_ids: set[uuid.UUID] | list[uuid.UUID],
    ) -> list[tuple[uuid.UUID, datetime]]:
        """Return current document versions for a permission-scoped cache key.

        Query answers may be cached only when the cache identity reflects both
        the user's accessible set and the current indexed document versions.
        This lightweight projection avoids loading full document rows while
        preserving the global repository's existing authorization boundary.
        """
        self._apply_bypass_scope()
        if not document_ids:
            return []
        query = (
            select(Document.id, Document.updated_at)
            .where(
                Document.id.in_(document_ids),
                Document.is_deleted.is_(False),
            )
            .order_by(Document.id.asc())
        )
        with observe_db_query("documents.get_updated_at_by_ids_global"):
            return [
                (document_id, updated_at)
                for document_id, updated_at in self.db.execute(query).all()
            ]

    def soft_delete_batch(self, *, tenant_id: uuid.UUID, document_ids: list[uuid.UUID]) -> None:
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
