from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select, text

from app.db.session import get_session_factory, set_db_tenant_context
from app.models.query.query import Query
from app.models.query.query_citation import QueryCitation
from app.system.services.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser


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

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_upload_index_query_citations_e2e(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)
    seeded = seed_user(
        "tenant-e2e-w3", "editor-e2e-w3@tenant.example", "StrongPass!1234", ("editor",)
    )
    token = _login(client, seeded)

    for idx, text_payload in enumerate(
        [
            b"SLA target is 99.5 percent query success rate.",
            b"P95 latency targets are defined for cached and uncached paths.",
        ],
        start=1,
    ):
        upload = client.post(
            "/api/v1/documents/upload",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": str(seeded.tenant_id),
                "Idempotency-Key": f"idem-w3-e2e-{idx}",
            },
            files={"file": (f"doc-{idx}.txt", text_payload, "text/plain")},
        )
        assert upload.status_code == 200

    query = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={
            "query": "what is the query success rate target",
            "top_k": 5,
            "filters": {},
        },
    )
    assert query.status_code == 200
    payload = query.json()
    assert payload["citations"]
    assert payload["cached"] is False

    session = get_session_factory()()
    session.execute(text("SET ROLE aks_app"))
    try:
        set_db_tenant_context(session, seeded.tenant_id)
        query_count = session.execute(
            select(func.count())
            .select_from(Query)
            .where(Query.tenant_id == seeded.tenant_id)
        ).scalar_one()
        citation_count = session.execute(
            select(func.count())
            .select_from(QueryCitation)
            .where(QueryCitation.tenant_id == seeded.tenant_id)
        ).scalar_one()
        assert query_count == 1
        assert citation_count >= 1
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
