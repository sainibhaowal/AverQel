from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.deepspace.memory.memory_service import MemoryService, TodoService
from app.deepspace.models.agent_runtime import DeepSpaceAgentRun, DeepSpaceRunEvent
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.deepspace.services.task_loop import DeepSpaceTaskLoopStore
from app.documents.models.collection import DocumentCollection
from app.documents.models.document import Document
from app.documents.repositories.collections import CollectionsRepository
from app.documents.repositories.documents import DocumentsRepository
from app.query.repositories.queries import QueriesRepository
from app.system.models.storage_lifecycle import (
    StorageArchiveManifest,
    StorageLifecycleItem,
    StorageRetentionRun,
)
from app.system.services.storage_lifecycle import StorageLifecycleService
from app.system.services.storage_quota import StorageQuotaService
from app.system.services.storage_service import StorageService
from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_reconciliation_is_read_only_for_source_data(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user("reconcile-tenant", "reconcile@example.com", "StrongPass!1234", ("user",))
    token = _login(client, seeded)
    response = client.post(
        "/api/v1/storage/reconcile",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "complete"


def test_primary_durable_writes_touch_their_lifecycle_identity(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    """Direct writes protect fresh user data before the monthly reconcile job."""
    seeded = seed_user(
        "direct-hooks-tenant", "direct-hooks@example.com", "StrongPass!1234", ("user",)
    )
    document = Document(
        tenant_id=seeded.tenant_id,
        uploaded_by_user_id=seeded.user_id,
        filename="notes.txt",
        content_type="text/plain",
        size_bytes=5,
        sha256_hash="a" * 64,
        storage_bucket="documents",
        storage_object_key=f"{seeded.tenant_id}/notes.txt",
        status="ready",
    )
    DocumentsRepository(db_session).create(document)

    query = QueriesRepository(db_session).create_query(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        query_text="What changed?",
        normalized_query="what changed",
        filters={},
        top_k=3,
        cache_hit=False,
        answer="A stored answer.",
        confidence=0.9,
        trace_id="retention-direct-hooks",
    )
    collection = CollectionsRepository(db_session).create(
        DocumentCollection(
            tenant_id=seeded.tenant_id,
            name="Retention test collection",
            connection_code="HOOKS-001",
        )
    )
    conversation = DeepSpaceChatRepository(db_session).create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Library lifecycle test",
        kind="deepspace",
    )
    DeepSpaceTaskLoopStore(db_session).write_workspace_file(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        filename="plan.md",
        content="# Plan",
    )
    TodoService(db_session).create_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Review archive protection",
        active_form="Review archive protection",
    )
    asyncio.run(
        MemoryService(db_session).get_preferences(
            tenant_id=str(seeded.tenant_id), user_id=str(seeded.user_id)
        )
    )

    identities = {
        (row.category, row.source_type, row.source_id)
        for row in db_session.query(StorageLifecycleItem)
        .filter(StorageLifecycleItem.tenant_id == seeded.tenant_id)
        .all()
    }
    assert ("files", "document", str(document.id)) in identities
    assert ("queries", "grounded_query", str(query.id)) in identities
    assert ("collections", "collection", str(collection.id)) in identities
    assert (
        "library",
        "workspace_file",
    ) in {identity[:2] for identity in identities}
    assert ("queues", "agent_todo") in {identity[:2] for identity in identities}
    assert ("memory", "memory_preferences") in {identity[:2] for identity in identities}


def test_archive_restore_is_reversible_and_does_not_purge(
    client: TestClient,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user("archive-tenant", "archive@example.com", "StrongPass!1234", ("user",))
    token = _login(client, seeded)
    item = StorageLifecycleService(db_session).record_activity(
        tenant_id=seeded.tenant_id,
        owner_user_id=seeded.user_id,
        category="memory",
        source_type="test_source",
        source_id=str(uuid.uuid4()),
        activity_kind="test",
        size_bytes=1,
    )
    item.state = "eligible"
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}

    archive = client.post(f"/api/v1/storage/archives/{item.id}", headers=headers)
    assert archive.status_code == 200
    assert archive.json()["state"] == "archived"

    restore = client.post(f"/api/v1/storage/archives/{item.id}/restore", headers=headers)
    assert restore.status_code == 200
    assert restore.json()["state"] == "restored"


def test_automatic_archive_path_only_archives_known_user_content(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "auto-archive-tenant", "auto-archive@example.com", "StrongPass!1234", ("user",)
    )
    lifecycle = StorageLifecycleService(db_session)
    item = lifecycle.record_activity(
        tenant_id=seeded.tenant_id,
        owner_user_id=seeded.user_id,
        category="memory",
        source_type="test_memory",
        source_id=str(uuid.uuid4()),
        activity_kind="test",
        size_bytes=12,
    )
    item.state = "eligible"
    run = StorageRetentionRun(
        tenant_id=seeded.tenant_id,
        policy_version=1,
        retention_mode="30",
        retention_days=30,
        status="running",
        operation="archive",
    )
    db_session.add(run)
    db_session.flush()

    archived = lifecycle.archive_eligible_items(
        tenant_id=seeded.tenant_id,
        policy_version=1,
        run_id=run.id,
    )
    db_session.commit()

    assert archived == 1
    assert item.state == "archived"
    assert (
        db_session.query(StorageArchiveManifest).filter_by(lifecycle_item_id=item.id).count() == 1
    )


def test_deepspace_archived_conversation_is_hidden_and_restorable(
    client: TestClient,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "deepspace-archive-tenant", "deepspace-archive@example.com", "StrongPass!1234", ("user",)
    )
    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Archived DeepSpace conversation",
        kind="deepspace",
    )
    item = StorageLifecycleService(db_session).record_activity(
        tenant_id=seeded.tenant_id,
        owner_user_id=seeded.user_id,
        category="chat_history",
        source_type="conversation",
        source_id=str(conversation.id),
        activity_kind="test",
        size_bytes=1,
    )
    item.state = "eligible"
    db_session.commit()
    StorageLifecycleService(db_session).archive_item(
        tenant_id=seeded.tenant_id,
        item_id=item.id,
        user_id=seeded.user_id,
    )
    db_session.commit()
    assert (
        repo.list_conversations(
            tenant_id=seeded.tenant_id, user_id=seeded.user_id, kind="deepspace"
        )
        == []
    )
    assert [
        row.id
        for row in repo.list_archived_conversations(
            tenant_id=seeded.tenant_id, user_id=seeded.user_id, kind="deepspace"
        )
    ] == [conversation.id]

    token = _login(client, seeded)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }
    assert client.get("/api/v1/deepspace/chats", headers=headers).json()["items"] == []
    archived_response = client.get("/api/v1/deepspace/chats/archived", headers=headers)
    assert archived_response.status_code == 200
    assert [row["id"] for row in archived_response.json()["items"]] == [str(conversation.id)]
    restore_response = client.post(
        f"/api/v1/deepspace/chats/{conversation.id}/restore", headers=headers
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["state"] == "active"

    assert [
        row.id
        for row in repo.list_conversations(
            tenant_id=seeded.tenant_id, user_id=seeded.user_id, kind="deepspace"
        )
    ] == [conversation.id]


def test_explicit_protections_and_expired_scan_lease_are_safe(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "retention-protection-tenant",
        "retention-protection@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    lifecycle = StorageLifecycleService(db_session)
    item = lifecycle.record_activity(
        tenant_id=seeded.tenant_id,
        owner_user_id=seeded.user_id,
        category="chat_history",
        source_type="conversation",
        source_id=str(uuid.uuid4()),
        activity_kind="test",
        size_bytes=1,
        at=datetime.now(UTC) - timedelta(days=90),
    )
    lifecycle.set_source_protection(
        tenant_id=seeded.tenant_id,
        category=item.category,
        source_type=item.source_type,
        source_id=item.source_id,
        pinned=True,
        legal_hold=True,
        admin_exempt=True,
        reason="retention test hold",
    )
    db_session.commit()
    assert (
        lifecycle._protection_reason(item=item, tenant_id=seeded.tenant_id, now=datetime.now(UTC))
        == "legal_hold"
    )

    first = lifecycle.claim_scan_run(tenant_id=seeded.tenant_id, lease_minutes=1)
    assert first is not None
    second = lifecycle.claim_scan_run(tenant_id=seeded.tenant_id, lease_minutes=1)
    assert second is None
    first.lease_until = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    recovered = lifecycle.claim_scan_run(tenant_id=seeded.tenant_id, lease_minutes=1)
    assert recovered is not None
    assert recovered.id == first.id


def test_deepspace_event_can_be_linked_to_its_agent_run(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "event-run-link-tenant", "event-run-link@example.com", "StrongPass!1234", ("user",)
    )
    conversation = DeepSpaceChatRepository(db_session).create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Event link test",
        kind="deepspace",
    )
    run = DeepSpaceAgentRun(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        status="completed",
    )
    db_session.add(run)
    db_session.flush()
    event = DeepSpaceRunEvent(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        run_id=run.id,
        client_request_id="event-run-link",
        sequence=1,
        frame="event: done\ndata: {}\n\n",
        event_name="done",
    )
    db_session.add(event)
    db_session.commit()
    assert event.run_id == run.id


def test_reservation_is_idempotent_and_tenant_object_prefix_is_strict(
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "reservation-tenant", "reservation@example.com", "StrongPass!1234", ("user",)
    )
    service = StorageQuotaService(db_session)
    first = service.reserve_capacity(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        reservation_key="test-reservation",
        reserved_bytes=1,
    )
    second = service.reserve_capacity(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        reservation_key="test-reservation",
        reserved_bytes=1,
    )
    assert first.id == second.id
    assert (
        service.release_capacity(
            tenant_id=seeded.tenant_id,
            reservation_key="test-reservation",
        )
        is True
    )
    db_session.commit()
    assert StorageService.is_tenant_object_key(
        tenant_id=seeded.tenant_id,
        object_key=f"{seeded.tenant_id}/file.txt",
    )
    assert not StorageService.is_tenant_object_key(
        tenant_id=seeded.tenant_id,
        object_key=f"{uuid.uuid4()}/file.txt",
    )
