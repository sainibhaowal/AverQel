from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select, text

from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.collection import (
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
)
from app.documents.models.data_deletion import DataDeletion
from app.documents.models.document import Document
from app.documents.services.deletion_service import DeletionService
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.query.models.comment import Comment
from app.query.models.conversation import Conversation
from app.query.models.message import Message
from app.query.models.message_version import MessageVersion
from app.query.models.pinned_finding import PinnedFinding
from app.query.models.query import Query
from app.query.repositories.chat import ChatRepository
from app.system.models.storage_cleanup import StorageCleanupJob
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

    def fake_delete(
        self: StorageService,
        *,
        bucket: str,
        object_key: str,
        raise_on_error: bool = False,
    ) -> None:
        in_memory_objects.pop((bucket, object_key), None)

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)
    monkeypatch.setattr(StorageService, "delete_object", fake_delete)


def test_worker_returns_unapproved_queued_deletion_to_approval(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    seeded = seed_user(
        "tenant-del-guard",
        "admin-del-guard@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        row = DataDeletion(
            id=generate_uuid7_with_fallback(),
            tenant_id=seeded.tenant_id,
            requested_by_user_id=seeded.user_id,
            status="queued",
            scope="tenant_data",
            reason="workspace_offboarding",
        )
        session.add(row)
        session.commit()

        def fail_if_purged(self: DeletionService, *, tenant_id: uuid.UUID) -> dict[str, int]:
            raise AssertionError(f"unapproved purge ran for {tenant_id}")

        monkeypatch.setattr(DeletionService, "_purge_tenant_data", fail_if_purged)
        DeletionService(session, get_settings()).process_deletion(
            tenant_id=seeded.tenant_id,
            deletion_id=row.id,
        )
        session.refresh(row)
        assert row.status == "awaiting_approval"
        assert row.approved_by_user_id is None
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


def test_single_admin_deletion_requires_delay_and_worker_checks_approval(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta

    seeded = seed_user(
        "tenant-del-single-admin",
        "admin-del-single@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = DeletionService(session, get_settings())
        requested = service.request_deletion(
            tenant_id=seeded.tenant_id,
            requested_by_user_id=seeded.user_id,
            reason="security_incident",
        )
        assert requested.self_approval_not_before is not None
        assert requested.self_approval_not_before > datetime.now(UTC) + timedelta(hours=23)

        with pytest.raises(ApiError) as early_approval:
            service.self_approve_deletion(
                tenant_id=seeded.tenant_id,
                deletion_id=requested.deletion_id,
                approved_by_user_id=seeded.user_id,
            )
        assert early_approval.value.code == "DELETION_SELF_APPROVAL_DELAY_ACTIVE"

        row = service.get_status(tenant_id=seeded.tenant_id, deletion_id=requested.deletion_id)
        row.self_approval_not_before = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        approved = service.self_approve_deletion(
            tenant_id=seeded.tenant_id,
            deletion_id=requested.deletion_id,
            approved_by_user_id=seeded.user_id,
        )
        assert approved.status == "queued"

        monkeypatch.setattr(
            DeletionService,
            "_purge_tenant_data",
            lambda self, *, tenant_id: {"documents": 2},
        )
        service.process_deletion(
            tenant_id=seeded.tenant_id,
            deletion_id=requested.deletion_id,
        )
        session.refresh(row)
        assert row.status == "completed"
        assert row.approval_mode == "single_admin_delayed"
        assert row.approved_by_user_id == seeded.user_id
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


def test_requesting_admin_can_cancel_before_purge_is_approved(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-del-cancel",
        "admin-del-cancel@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = DeletionService(session, get_settings())
        requested = service.request_deletion(
            tenant_id=seeded.tenant_id,
            requested_by_user_id=seeded.user_id,
            reason="workspace_offboarding",
        )
        cancelled = service.cancel_deletion(
            tenant_id=seeded.tenant_id,
            deletion_id=requested.deletion_id,
            actor_user_id=seeded.user_id,
        )
        assert cancelled.status == "cancelled"

        service.process_deletion(
            tenant_id=seeded.tenant_id,
            deletion_id=requested.deletion_id,
        )
        row = service.get_status(tenant_id=seeded.tenant_id, deletion_id=requested.deletion_id)
        assert row.status == "cancelled"
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


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
    approver_id = generate_uuid7_with_fallback()
    approver_email = "admin-del-flow-approver@tenant.example"
    approver_password = "StrongPass!5678"
    session = get_session_factory()()
    try:
        session.execute(text("RESET ROLE"))
        set_db_tenant_context(session, seeded.tenant_id)
        admin_role = session.execute(select(Role).where(Role.name == "admin")).scalar_one()
        approver = User(
            id=approver_id,
            tenant_id=seeded.tenant_id,
            email=approver_email,
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password(approver_password),
            is_active=True,
        )
        session.add(approver)
        session.flush()
        session.add(
            UserRole(
                tenant_id=seeded.tenant_id,
                user_id=approver.id,
                role_id=admin_role.id,
            )
        )
        session.commit()
    finally:
        session.rollback()
        session.close()
    approver_seeded = SeededUser(
        tenant_id=seeded.tenant_id,
        user_id=approver_id,
        collection_code="unused",
        email=approver_email,
        password=approver_password,
    )
    get_settings().bootstrap_super_admin_emails = [seeded.email, approver_email]
    token = _login(client, seeded)
    approver_token = _login(client, approver_seeded)

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

    invalid_confirmation = client.post(
        "/api/v1/admin/data-deletions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={
            "reason": "workspace_offboarding",
            "target_confirmation": "DELETE wrong-workspace",
        },
    )
    assert invalid_confirmation.status_code == 400
    assert invalid_confirmation.json()["error"]["code"] == "INVALID_REQUEST"

    create = client.post(
        "/api/v1/admin/data-deletions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={
            "reason": "workspace_offboarding",
            "target_confirmation": f"DELETE {seeded.tenant_id}",
        },
    )
    assert create.status_code == 200
    deletion_id = create.json()["deletion_id"]
    assert create.json()["status"] == "awaiting_approval"

    self_approval = client.post(
        f"/api/v1/admin/data-deletions/{deletion_id}/approve",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert self_approval.status_code == 403
    assert self_approval.json()["error"]["code"] == "SECOND_APPROVER_REQUIRED"

    approval = client.post(
        f"/api/v1/admin/data-deletions/{deletion_id}/approve",
        headers={
            "Authorization": f"Bearer {approver_token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert approval.status_code == 200
    assert approval.json()["status"] == "queued"

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


def test_self_account_deletion_queues_failed_document_object_cleanup(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)
    seeded = seed_user(
        "tenant-self-delete-cleanup",
        "self-delete-cleanup@example.org",
        "StrongPass!1234",
        ("user",),
    )
    token = _login(client, seeded)
    upload = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-self-delete-cleanup-1",
        },
        files={"file": ("private-self-delete.txt", b"cleanup regression content", "text/plain")},
    )
    assert upload.status_code == 200

    def fail_delete(
        self: StorageService,
        *,
        bucket: str,
        object_key: str,
        raise_on_error: bool = False,
    ) -> None:
        raise RuntimeError("private storage provider failure text")

    monkeypatch.setattr(StorageService, "delete_object", fail_delete)
    response = client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"password": seeded.password},
    )
    assert response.status_code == 200

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        jobs = (
            session.execute(
                select(StorageCleanupJob).where(
                    StorageCleanupJob.tenant_id == seeded.tenant_id,
                    StorageCleanupJob.owner_user_id == seeded.user_id,
                )
            )
            .scalars()
            .all()
        )
        assert len(jobs) == 1
        assert jobs[0].last_error == "document_storage_delete_failed"
        assert jobs[0].status == "pending"
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
