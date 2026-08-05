from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.collection import (
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
)
from app.documents.models.document import Document
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.query.models.comment import Comment
from app.query.models.conversation import Conversation
from app.query.models.message import Message
from app.query.models.message_version import MessageVersion
from app.query.models.pinned_finding import PinnedFinding
from app.query.models.query import Query
from app.query.repositories.chat import ChatRepository
from app.system.services.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser, _generate_test_collection_code


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _patch_storage(monkeypatch: MonkeyPatch) -> None:
    in_memory_objects: dict[tuple[str, str], bytes] = {}

    def fake_put(
        self: StorageService,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> StoredObject:
        object_key = f"{tenant_id}/{document_id}/{filename}"
        in_memory_objects[(self.settings.minio_bucket, object_key)] = payload
        return StoredObject(
            bucket=self.settings.minio_bucket,
            object_key=object_key,
            etag="etag",
            size_bytes=len(payload),
            content_type=content_type,
        )

    def fake_get(self: StorageService, *, bucket: str, object_key: str) -> bytes:
        return in_memory_objects[(bucket, object_key)]

    def fake_delete(self: StorageService, *, bucket: str, object_key: str) -> None:
        in_memory_objects.pop((bucket, object_key), None)

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)
    monkeypatch.setattr(StorageService, "delete_object", fake_delete)


def test_data_deletion_workflow_completes_and_purges_tenant_documents(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)
    seeded = seed_user(
        "tenant-del-flow",
        "admin-del-flow@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [seeded.email]
    token = _login(client, seeded)

    upload = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-del-flow-1",
        },
        files={"file": ("delete-me.txt", b"delete workflow content", "text/plain")},
    )
    assert upload.status_code == 200

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        chat_repo = ChatRepository(session)
        conversation = chat_repo.create_conversation(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            title="Deletion conversation",
        )
        message = chat_repo.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            role="user",
            content="Delete this chat too",
        )
        chat_repo.create_message_version(
            tenant_id=seeded.tenant_id,
            message_id=message.id,
            content="Delete this edited chat too",
            source_type="edit",
        )

        document_id = session.execute(
            select(Document.id).where(Document.tenant_id == seeded.tenant_id)
        ).scalar_one()

        collection = DocumentCollection(
            tenant_id=seeded.tenant_id,
            name="Deletion collection",
            description="Should be purged",
            connection_code=_generate_test_collection_code(),
        )
        session.add(collection)
        session.flush()
        session.add(CollectionDocument(collection_id=collection.id, document_id=document_id))
        session.add(
            CollectionPermission(
                collection_id=collection.id,
                user_id=seeded.user_id,
                role="owner",
            )
        )

        query = Query(
            id=generate_uuid7_with_fallback(),
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            query_text="Delete query workspace data",
            normalized_query="delete query workspace data",
            filters={},
            top_k=3,
            cache_hit=False,
            answer="Temporary answer",
            confidence=0.5,
            trace_id="trace-delete-workflow",
            shared_with=[],
        )
        session.add(query)
        session.flush()

        session.add(
            Comment(
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                target_type="query",
                target_id=query.id,
                content="Delete this comment too",
            )
        )
        session.add(
            PinnedFinding(
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                query_id=query.id,
                chunk_id=generate_uuid7_with_fallback(),
                notes="Delete this pinned finding too",
            )
        )
        session.commit()
    finally:
        session.execute(text("RESET ROLE"))
        session.close()

    create = client.post(
        "/api/v1/admin/data-deletions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"reason": "tenant cleanup request"},
    )
    assert create.status_code == 200
    deletion_id = create.json()["deletion_id"]

    status = client.get(
        f"/api/v1/admin/data-deletions/{deletion_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] in {"completed", "processing", "queued"}

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        doc_count = session.execute(
            select(func.count()).select_from(Document).where(Document.tenant_id == seeded.tenant_id)
        ).scalar_one()
        conversation_count = session.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.tenant_id == seeded.tenant_id)
        ).scalar_one()
        message_count = session.execute(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.tenant_id == seeded.tenant_id)
        ).scalar_one()
        message_version_count = session.execute(
            select(func.count())
            .select_from(MessageVersion)
            .join(Message, Message.id == MessageVersion.message_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.tenant_id == seeded.tenant_id)
        ).scalar_one()
        collection_count = session.execute(
            select(func.count())
            .select_from(DocumentCollection)
            .where(DocumentCollection.tenant_id == seeded.tenant_id)
        ).scalar_one()
        collection_document_count = session.execute(
            select(func.count())
            .select_from(CollectionDocument)
            .join(
                DocumentCollection,
                DocumentCollection.id == CollectionDocument.collection_id,
            )
            .where(DocumentCollection.tenant_id == seeded.tenant_id)
        ).scalar_one()
        collection_permission_count = session.execute(
            select(func.count())
            .select_from(CollectionPermission)
            .join(
                DocumentCollection,
                DocumentCollection.id == CollectionPermission.collection_id,
            )
            .where(DocumentCollection.tenant_id == seeded.tenant_id)
        ).scalar_one()
        comment_count = session.execute(
            select(func.count()).select_from(Comment).where(Comment.tenant_id == seeded.tenant_id)
        ).scalar_one()
        pinned_finding_count = session.execute(
            select(func.count())
            .select_from(PinnedFinding)
            .where(PinnedFinding.tenant_id == seeded.tenant_id)
        ).scalar_one()
        assert doc_count == 0
        assert conversation_count == 0
        assert message_count == 0
        assert message_version_count == 0
        assert collection_count == 0
        assert collection_document_count == 0
        assert collection_permission_count == 0
        assert comment_count == 0
        assert pinned_finding_count == 0
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
