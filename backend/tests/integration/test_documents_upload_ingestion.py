from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select, text

from app.core.config import Settings
from app.db.session import get_session_factory, set_db_tenant_context
from app.models.documents.chunk_embedding import ChunkEmbedding
from app.models.documents.document import Document
from app.models.documents.document_chunk import DocumentChunk
from app.services.system.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser


def _login(
    *,
    client: TestClient,
    tenant_id: str,
    email: str,
    password: str,
) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": tenant_id},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_upload_ingestion_happy_path_and_idempotent_replay(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
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
            etag="fake-etag",
            size_bytes=len(payload),
            content_type=content_type,
        )

    def fake_get(self: StorageService, *, bucket: str, object_key: str) -> bytes:
        return in_memory_objects[(bucket, object_key)]

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)

    seeded = seed_user(
        "tenant-week2-a", "editor@tenant-a.example", "StrongPass!1234", ("editor",)
    )
    token = _login(
        client=client,
        tenant_id=str(seeded.tenant_id),
        email=seeded.email,
        password=seeded.password,
    )

    file_payload = b"Week 2 ingestion happy path content for indexing.\n" * 15
    upload_headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
        "Idempotency-Key": "idem-week2-upload-1",
    }

    upload_response = client.post(
        "/api/v1/documents/upload",
        headers=upload_headers,
        files={"file": ("knowledge.txt", file_payload, "text/plain")},
    )
    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    assert upload_payload["status"] == "queued"

    replay_response = client.post(
        "/api/v1/documents/upload",
        headers=upload_headers,
        files={"file": ("knowledge.txt", file_payload, "text/plain")},
    )
    assert replay_response.status_code == 200
    replay_payload = replay_response.json()
    assert replay_payload["document_id"] == upload_payload["document_id"]
    assert replay_payload["ingestion_job_id"] == upload_payload["ingestion_job_id"]

    status_response = client.get(
        f"/api/v1/documents/{upload_payload['document_id']}/status",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "indexed"
    assert status_payload["ingestion_status"] == "indexed"

    metadata_response = client.get(
        f"/api/v1/documents/{upload_payload['document_id']}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert metadata_response.status_code == 200
    metadata_payload = metadata_response.json()
    assert metadata_payload["filename"] == "knowledge.txt"
    assert metadata_payload["size_bytes"] == len(file_payload)

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)

        doc_count = session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == seeded.tenant_id)
        ).scalar_one()
        chunk_count = session.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.tenant_id == seeded.tenant_id)
        ).scalar_one()
        embedding_count = session.execute(
            select(func.count())
            .select_from(ChunkEmbedding)
            .where(ChunkEmbedding.tenant_id == seeded.tenant_id)
        ).scalar_one()
        assert doc_count == 1
        assert chunk_count >= 1
        assert embedding_count >= 1
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


def test_idempotency_conflict_when_payload_changes(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
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
            etag="fake-etag",
            size_bytes=len(payload),
            content_type=content_type,
        )

    def fake_get(self: StorageService, *, bucket: str, object_key: str) -> bytes:
        return in_memory_objects[(bucket, object_key)]

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)

    seeded = seed_user(
        "tenant-week2-b", "editor@tenant-b.example", "StrongPass!1234", ("editor",)
    )
    token = _login(
        client=client,
        tenant_id=str(seeded.tenant_id),
        email=seeded.email,
        password=seeded.password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
        "Idempotency-Key": "idem-week2-conflict-1",
    }

    first = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("doc.txt", b"first-payload", "text/plain")},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("doc.txt", b"second-payload", "text/plain")},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_upload_ingestion_sanitizes_null_bytes_in_text_payload(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
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
            etag="fake-etag",
            size_bytes=len(payload),
            content_type=content_type,
        )

    def fake_get(self: StorageService, *, bucket: str, object_key: str) -> bytes:
        return in_memory_objects[(bucket, object_key)]

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)

    # Bypass MIME signature validation; null bytes make magic sniff as octet-stream
    from app.services.ingestion.ingestion_service import IngestionService

    monkeypatch.setattr(
        IngestionService, "_validate_upload", lambda self, **kwargs: None
    )

    seeded = seed_user(
        "tenant-week2-c", "editor@tenant-c.example", "StrongPass!1234", ("editor",)
    )
    token = _login(
        client=client,
        tenant_id=str(seeded.tenant_id),
        email=seeded.email,
        password=seeded.password,
    )

    upload = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-week2-null-byte-1",
        },
        files={"file": ("nulls.txt", b"line1\x00line2\x00line3", "text/plain")},
    )
    assert upload.status_code == 200
    document_id = upload.json()["document_id"]

    status = client.get(
        f"/api/v1/documents/{document_id}/status",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "indexed"
    assert payload["ingestion_status"] == "indexed"

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        first_chunk = session.execute(
            select(DocumentChunk.content)
            .where(DocumentChunk.tenant_id == seeded.tenant_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(1)
        ).scalar_one()
        assert "\x00" not in first_chunk
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
