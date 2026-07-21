from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select, text

from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.system.services.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser


def test_sample_corpus_indexes_end_to_end(
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
            etag="etag",
            size_bytes=len(payload),
            content_type=content_type,
        )

    def fake_get(self: StorageService, *, bucket: str, object_key: str) -> bytes:
        return in_memory_objects[(bucket, object_key)]

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)

    seeded = seed_user(
        "tenant-e2e", "editor-e2e@tenant.example", "StrongPass!1234", ("editor",)
    )

    login = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    corpus = [
        (
            "playbook.md",
            b"# Incident Playbook\n\nStep 1: Identify issue.\nStep 2: Mitigate quickly.",
        ),
        (
            "runbook.txt",
            b"Operational runbook entry with checks and escalation matrix.",
        ),
    ]

    for idx, (name, payload) in enumerate(corpus, start=1):
        response = client.post(
            "/api/v1/documents/upload",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": str(seeded.tenant_id),
                "Idempotency-Key": f"idem-e2e-{idx}",
            },
            files={
                "file": (
                    name,
                    payload,
                    "text/markdown" if name.endswith(".md") else "text/plain",
                )
            },
        )
        assert response.status_code == 200
        status = client.get(
            f"/api/v1/documents/{response.json()['document_id']}/status",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": str(seeded.tenant_id),
            },
        )
        assert status.status_code == 200
        assert status.json()["status"] == "indexed"

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)

        documents_count = session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == seeded.tenant_id)
        ).scalar_one()
        chunks_count = session.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.tenant_id == seeded.tenant_id)
        ).scalar_one()
        embeddings_count = session.execute(
            select(func.count())
            .select_from(ChunkEmbedding)
            .where(ChunkEmbedding.tenant_id == seeded.tenant_id)
        ).scalar_one()

        assert documents_count == len(corpus)
        assert chunks_count >= len(corpus)
        assert embeddings_count >= len(corpus)
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
