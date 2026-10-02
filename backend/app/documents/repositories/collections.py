from __future__ import annotations

import uuid
from datetime import datetime
from typing import TypedDict

from sqlalchemy import delete, func, select

from app.documents.models.collection import (
    CollectionChatMessage,
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
)
from app.documents.models.document import Document
from app.platform.database.session import set_db_tenant_context
from app.system.repositories.base import BaseRepository
from app.system.services.metrics_service import observe_db_query
from app.system.services.storage_lifecycle import StorageLifecycleService
from app.system.services.storage_quota import StorageQuotaService


class CollectionPermissionPayload(TypedDict):
    user_id: uuid.UUID
    role: str


class CollectionsRepository(BaseRepository):
    def _apply_bypass_scope(self) -> None:
        set_db_tenant_context(self.db, "bypass")

    def list_accessible_for_user(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[DocumentCollection]:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(DocumentCollection)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == DocumentCollection.id,
            )
            .where(
                DocumentCollection.tenant_id == tenant_id,
                CollectionPermission.user_id == user_id,
            )
            .order_by(DocumentCollection.created_at.desc(), DocumentCollection.id.desc())
        )
        with observe_db_query("collections.list_accessible_for_user"):
            return list(self.db.execute(query).scalars().all())

    def list_accessible_for_user_global(
        self,
        *,
        user_id: uuid.UUID,
    ) -> list[DocumentCollection]:
        self._apply_bypass_scope()
        query = (
            select(DocumentCollection)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == DocumentCollection.id,
            )
            .where(
                CollectionPermission.user_id == user_id,
                CollectionPermission.role.in_(["member", "owner", "shared"]),
            )
            .order_by(DocumentCollection.created_at.desc(), DocumentCollection.id.desc())
        )
        with observe_db_query("collections.list_accessible_for_user_global"):
            return list(self.db.execute(query).scalars().all())

    def list_pending_for_user_global(
        self,
        *,
        user_id: uuid.UUID,
    ) -> list[DocumentCollection]:
        self._apply_bypass_scope()
        query = (
            select(DocumentCollection)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == DocumentCollection.id,
            )
            .where(
                CollectionPermission.user_id == user_id,
                CollectionPermission.role == "pending",
            )
            .order_by(DocumentCollection.created_at.desc(), DocumentCollection.id.desc())
        )
        with observe_db_query("collections.list_pending_for_user_global"):
            return list(self.db.execute(query).scalars().all())

    def create(self, collection: DocumentCollection) -> DocumentCollection:
        self.apply_tenant_scope(collection.tenant_id)
        with observe_db_query("collections.create"):
            self.db.add(collection)
            self.db.flush()
        StorageLifecycleService(self.db).touch_source(
            tenant_id=collection.tenant_id,
            category="collections",
            source_type="collection",
            source_id=str(collection.id),
            dependency_group_id=str(collection.id),
            activity_kind="collection_created",
        )
        return collection

    def get_by_id(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> DocumentCollection | None:
        self.apply_tenant_scope(tenant_id)
        query = select(DocumentCollection).where(
            DocumentCollection.tenant_id == tenant_id,
            DocumentCollection.id == collection_id,
        )
        with observe_db_query("collections.get_by_id"):
            return self.db.execute(query).scalar_one_or_none()

    def get_by_id_global(
        self,
        *,
        collection_id: uuid.UUID,
    ) -> DocumentCollection | None:
        self._apply_bypass_scope()
        query = select(DocumentCollection).where(DocumentCollection.id == collection_id)
        with observe_db_query("collections.get_by_id_global"):
            return self.db.execute(query).scalar_one_or_none()

    def get_by_connection_code_global(
        self,
        *,
        connection_code: str,
    ) -> DocumentCollection | None:
        self._apply_bypass_scope()
        query = select(DocumentCollection).where(
            DocumentCollection.connection_code == connection_code.upper()
        )
        with observe_db_query("collections.get_by_connection_code_global"):
            return self.db.execute(query).scalar_one_or_none()

    def delete(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> bool:
        self.apply_tenant_scope(tenant_id)
        stmt = delete(DocumentCollection).where(
            DocumentCollection.tenant_id == tenant_id,
            DocumentCollection.id == collection_id,
        )
        with observe_db_query("collections.delete"):
            result = self.db.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    def list_by_tenant(self, *, tenant_id: uuid.UUID) -> list[DocumentCollection]:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(DocumentCollection)
            .where(DocumentCollection.tenant_id == tenant_id)
            .order_by(DocumentCollection.created_at.desc(), DocumentCollection.id.desc())
        )
        with observe_db_query("collections.list_by_tenant"):
            return list(self.db.execute(query).scalars().all())

    def add_documents(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return

        valid_document_ids = set(
            self.db.execute(
                select(Document.id).where(
                    Document.tenant_id == tenant_id,
                    Document.id.in_(document_ids),
                )
            )
            .scalars()
            .all()
        )
        existing_document_ids = set(
            self.db.execute(
                select(CollectionDocument.document_id).where(
                    CollectionDocument.collection_id == collection_id,
                    CollectionDocument.document_id.in_(document_ids),
                )
            )
            .scalars()
            .all()
        )

        with observe_db_query("collections.add_documents"):
            for doc_id in document_ids:
                if doc_id not in valid_document_ids or doc_id in existing_document_ids:
                    continue
                cd = CollectionDocument(
                    collection_id=collection_id,
                    document_id=doc_id,
                )
                self.db.add(cd)
        StorageLifecycleService(self.db).touch_source(
            tenant_id=tenant_id,
            category="collections",
            source_type="collection",
            source_id=str(collection_id),
            dependency_group_id=str(collection_id),
            activity_kind="collection_documents_changed",
        )

    def add_documents_for_user_global(
        self,
        *,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> None:
        self._apply_bypass_scope()
        if not document_ids:
            return

        tenant_id = self.db.execute(
            select(DocumentCollection.tenant_id).where(DocumentCollection.id == collection_id)
        ).scalar_one_or_none()
        if tenant_id is None:
            return

        valid_document_ids = set(
            self.db.execute(
                select(Document.id).where(
                    Document.uploaded_by_user_id == user_id,
                    Document.id.in_(document_ids),
                    Document.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        existing_document_ids = set(
            self.db.execute(
                select(CollectionDocument.document_id).where(
                    CollectionDocument.collection_id == collection_id,
                    CollectionDocument.document_id.in_(document_ids),
                )
            )
            .scalars()
            .all()
        )

        with observe_db_query("collections.add_documents_for_user_global"):
            for doc_id in document_ids:
                if doc_id not in valid_document_ids or doc_id in existing_document_ids:
                    continue
                self.db.add(
                    CollectionDocument(
                        collection_id=collection_id,
                        document_id=doc_id,
                    )
                )
        StorageLifecycleService(self.db).touch_source(
            tenant_id=tenant_id,
            category="collections",
            source_type="collection",
            source_id=str(collection_id),
            dependency_group_id=str(collection_id),
            activity_kind="collection_documents_changed",
        )

    def remove_documents(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return

        stmt = delete(CollectionDocument).where(
            CollectionDocument.collection_id == collection_id,
            CollectionDocument.document_id.in_(document_ids),
        )
        with observe_db_query("collections.remove_documents"):
            self.db.execute(stmt)

    def remove_documents_for_user_global(
        self,
        *,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> None:
        self._apply_bypass_scope()
        if not document_ids:
            return

        removable_document_ids = [
            item.id
            for item in self.list_manageable_documents_for_user(
                collection_id=collection_id,
                user_id=user_id,
                document_ids=document_ids,
            )
        ]
        if not removable_document_ids:
            return

        stmt = delete(CollectionDocument).where(
            CollectionDocument.collection_id == collection_id,
            CollectionDocument.document_id.in_(removable_document_ids),
        )
        with observe_db_query("collections.remove_documents_for_user_global"):
            self.db.execute(stmt)

    def list_documents(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> list[Document]:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(Document)
            .join(CollectionDocument, CollectionDocument.document_id == Document.id)
            .join(
                DocumentCollection,
                DocumentCollection.id == CollectionDocument.collection_id,
            )
            .where(
                DocumentCollection.tenant_id == tenant_id,
                CollectionDocument.collection_id == collection_id,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.created_at.desc())
        )
        with observe_db_query("collections.list_documents"):
            return list(self.db.execute(query).scalars().all())

    def list_documents_for_user(
        self,
        *,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 200,
        before: datetime | None = None,
    ) -> list[Document]:
        self._apply_bypass_scope()
        query = (
            select(Document)
            .join(CollectionDocument, CollectionDocument.document_id == Document.id)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == CollectionDocument.collection_id,
            )
            .where(
                CollectionDocument.collection_id == collection_id,
                CollectionPermission.user_id == user_id,
                CollectionPermission.role.in_(["member", "owner", "shared"]),
                Document.is_deleted.is_(False),
            )
        )
        if before is not None:
            query = query.where(Document.created_at < before)
        query = query.order_by(Document.created_at.desc()).limit(max(1, min(limit, 200)))
        with observe_db_query("collections.list_documents_for_user"):
            return list(self.db.execute(query).scalars().all())

    def list_document_ids_for_user(
        self,
        *,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """Return the complete authorized ID scope for collection queries.

        This deliberately has no UI page-size cap: query authorization must not
        silently truncate a collection with more than one page of documents.
        """
        self._apply_bypass_scope()
        query = (
            select(Document.id)
            .join(CollectionDocument, CollectionDocument.document_id == Document.id)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == CollectionDocument.collection_id,
            )
            .where(
                CollectionDocument.collection_id == collection_id,
                CollectionPermission.user_id == user_id,
                CollectionPermission.role.in_(["member", "owner", "shared"]),
                Document.is_deleted.is_(False),
            )
            .order_by(Document.id)
        )
        with observe_db_query("collections.list_document_ids_for_user"):
            return list(self.db.execute(query).scalars().all())

    def list_manageable_documents_for_user(
        self,
        *,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID] | None = None,
    ) -> list[Document]:
        self._apply_bypass_scope()
        query = (
            select(Document)
            .join(CollectionDocument, CollectionDocument.document_id == Document.id)
            .where(
                CollectionDocument.collection_id == collection_id,
                Document.uploaded_by_user_id == user_id,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.created_at.desc())
        )
        if document_ids:
            query = query.where(Document.id.in_(document_ids))
        with observe_db_query("collections.list_manageable_documents_for_user"):
            return list(self.db.execute(query).scalars().all())

    def add_permissions(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
        permissions: list[CollectionPermissionPayload],
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        user_ids = [perm["user_id"] for perm in permissions]
        existing_user_ids = set(
            self.db.execute(
                select(CollectionPermission.user_id).where(
                    CollectionPermission.collection_id == collection_id,
                    CollectionPermission.user_id.in_(user_ids),
                )
            )
            .scalars()
            .all()
        )
        with observe_db_query("collections.add_permissions"):
            for perm in permissions:
                if perm["user_id"] in existing_user_ids:
                    continue
                cp = CollectionPermission(
                    collection_id=collection_id,
                    user_id=perm["user_id"],
                    role=perm["role"],
                )
                self.db.add(cp)

    def remove_permissions(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
        user_ids: list[uuid.UUID],
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        if not user_ids:
            return

        stmt = delete(CollectionPermission).where(
            CollectionPermission.collection_id == collection_id,
            CollectionPermission.user_id.in_(user_ids),
        )
        with observe_db_query("collections.remove_permissions"):
            self.db.execute(stmt)

    def get_permissions(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> list[CollectionPermission]:
        self.apply_tenant_scope(tenant_id)
        collection = self.get_by_id(tenant_id=tenant_id, collection_id=collection_id)
        if collection is None:
            return []

        query = select(CollectionPermission).where(
            CollectionPermission.collection_id == collection_id
        )
        with observe_db_query("collections.get_permissions"):
            return list(self.db.execute(query).scalars().all())

    def get_permissions_global(
        self,
        *,
        collection_id: uuid.UUID,
    ) -> list[CollectionPermission]:
        self._apply_bypass_scope()
        query = select(CollectionPermission).where(
            CollectionPermission.collection_id == collection_id
        )
        with observe_db_query("collections.get_permissions_global"):
            return list(self.db.execute(query).scalars().all())

    def count_connected_members_global(
        self,
        *,
        collection_id: uuid.UUID,
    ) -> int:
        self._apply_bypass_scope()
        query = select(CollectionPermission.id).where(
            CollectionPermission.collection_id == collection_id,
            CollectionPermission.role.in_(["member", "owner", "shared"]),
        )
        with observe_db_query("collections.count_connected_members_global"):
            return len(list(self.db.execute(query).scalars().all()))

    def has_pending_invite_global(
        self,
        *,
        collection_id: uuid.UUID,
    ) -> bool:
        self._apply_bypass_scope()
        query = select(CollectionPermission.id).where(
            CollectionPermission.collection_id == collection_id,
            CollectionPermission.role == "pending",
        )
        with observe_db_query("collections.has_pending_invite_global"):
            return self.db.execute(query).scalar_one_or_none() is not None

    def get_user_permission(
        self,
        *,
        tenant_id: uuid.UUID,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CollectionPermission | None:
        self.apply_tenant_scope(tenant_id)
        query = select(CollectionPermission).where(
            CollectionPermission.collection_id == collection_id,
            CollectionPermission.user_id == user_id,
        )
        with observe_db_query("collections.get_user_permission"):
            return self.db.execute(query).scalar_one_or_none()

    def get_user_permission_global(
        self,
        *,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CollectionPermission | None:
        self._apply_bypass_scope()
        query = select(CollectionPermission).where(
            CollectionPermission.collection_id == collection_id,
            CollectionPermission.user_id == user_id,
        )
        with observe_db_query("collections.get_user_permission_global"):
            return self.db.execute(query).scalar_one_or_none()

    def update_permission_role_global(
        self,
        *,
        collection_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
    ) -> None:
        self._apply_bypass_scope()
        permission = self.get_user_permission_global(
            collection_id=collection_id,
            user_id=user_id,
        )
        if permission is not None:
            permission.role = role

    def get_document_collection_names(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[str]]:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return {}

        query = (
            select(CollectionDocument.document_id, DocumentCollection.name)
            .join(
                DocumentCollection,
                DocumentCollection.id == CollectionDocument.collection_id,
            )
            .where(
                DocumentCollection.tenant_id == tenant_id,
                CollectionDocument.document_id.in_(document_ids),
            )
            .order_by(DocumentCollection.name.asc())
        )
        with observe_db_query("collections.get_document_collection_names"):
            rows = self.db.execute(query).all()

        result: dict[uuid.UUID, list[str]] = {}
        for document_id, name in rows:
            result.setdefault(document_id, []).append(str(name))
        return result

    def get_document_collection_names_global(
        self,
        *,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[str]]:
        self._apply_bypass_scope()
        if not document_ids:
            return {}

        query = (
            select(CollectionDocument.document_id, DocumentCollection.name)
            .join(
                DocumentCollection,
                DocumentCollection.id == CollectionDocument.collection_id,
            )
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == CollectionDocument.collection_id,
            )
            .where(
                CollectionDocument.document_id.in_(document_ids),
                CollectionPermission.user_id == user_id,
                CollectionPermission.role.in_(["member", "owner", "shared"]),
            )
            .order_by(DocumentCollection.name.asc())
        )
        with observe_db_query("collections.get_document_collection_names_global"):
            rows = self.db.execute(query).all()

        result: dict[uuid.UUID, list[str]] = {}
        for document_id, name in rows:
            result.setdefault(document_id, []).append(str(name))
        return result

    def get_collection_document_counts(
        self,
        *,
        collection_ids: list[uuid.UUID],
        user_id: uuid.UUID,
    ) -> dict[uuid.UUID, int]:
        self._apply_bypass_scope()
        if not collection_ids:
            return {}

        query = (
            select(CollectionDocument.collection_id, func.count(Document.id))
            .join(Document, Document.id == CollectionDocument.document_id)
            .join(
                CollectionPermission,
                CollectionPermission.collection_id == CollectionDocument.collection_id,
            )
            .where(
                CollectionDocument.collection_id.in_(collection_ids),
                CollectionPermission.user_id == user_id,
                CollectionPermission.role.in_(["member", "owner", "shared"]),
                Document.is_deleted.is_(False),
            )
            .group_by(CollectionDocument.collection_id)
        )
        with observe_db_query("collections.get_collection_document_counts"):
            rows = self.db.execute(query).all()

        return {row[0]: int(row[1]) for row in rows}

    def list_chat_messages(
        self,
        *,
        collection_id: uuid.UUID,
        limit: int = 100,
        before: datetime | None = None,
    ) -> list[tuple[CollectionChatMessage, str, str | None]]:
        self._apply_bypass_scope()
        from app.auth.models.user import User

        query = (
            select(CollectionChatMessage, User.email, User.avatar)
            .join(User, User.id == CollectionChatMessage.user_id)
            .where(CollectionChatMessage.collection_id == collection_id)
        )
        if before is not None:
            query = query.where(CollectionChatMessage.created_at < before)
        query = query.order_by(
            CollectionChatMessage.created_at.desc(), CollectionChatMessage.id.desc()
        ).limit(max(1, min(limit, 200)))
        with observe_db_query("collections.list_chat_messages"):
            rows = list(self.db.execute(query).all())
        rows.reverse()
        return rows

    def create_chat_message(
        self,
        *,
        chat_message: CollectionChatMessage,
    ) -> CollectionChatMessage:
        self._apply_bypass_scope()
        tenant_id = self.db.execute(
            select(DocumentCollection.tenant_id).where(
                DocumentCollection.id == chat_message.collection_id
            )
        ).scalar_one()
        StorageQuotaService(self.db).ensure_capacity(
            tenant_id=tenant_id,
            user_id=chat_message.user_id,
            additional_bytes=StorageQuotaService.estimate_bytes(
                chat_message.message,
                chat_message.reactions,
            ),
        )
        with observe_db_query("collections.create_chat_message"):
            self.db.add(chat_message)
            self.db.flush()
        StorageLifecycleService(self.db).touch_source(
            tenant_id=tenant_id,
            category="collections",
            source_type="collection_chat",
            source_id=str(chat_message.id),
            owner_user_id=chat_message.user_id,
            dependency_group_id=str(chat_message.collection_id),
            activity_kind="collection_chat_created",
        )
        return chat_message
