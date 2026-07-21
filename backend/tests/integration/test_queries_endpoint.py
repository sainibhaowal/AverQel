from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select, text

from app.db.session import get_session_factory, set_db_tenant_context
from app.query.models.query import Query
from app.query.services.query_service import QueryService
from app.system.services.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser


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

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)


def _upload_indexed_doc(
    client: TestClient, token: str, tenant_id: str, idem: str, content: bytes
) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": tenant_id,
            "Idempotency-Key": idem,
        },
        files={"file": (f"{idem}.txt", content, "text/plain")},
    )
    assert response.status_code == 200


def test_query_endpoint_happy_path_and_cache_hit(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)
    seeded = seed_user(
        "tenant-q1", "editor-q1@tenant.example", "StrongPass!1234", ("editor",)
    )
    token = _login(client, seeded)

    _upload_indexed_doc(
        client,
        token,
        str(seeded.tenant_id),
        "idem-w3-q1",
        b"SLA requires 99.9% API availability and 99.5% query success rate.",
    )

    payload = {
        "query": "What is the query success rate target?",
        "top_k": 5,
        "filters": {},
    }
    first = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json=payload,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["cached"] is False
    assert 0.0 <= float(first_body["confidence"]) <= 1.0
    assert first_body["citations"]

    second = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json=payload,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["cached"] is True
    assert second_body["answer"] == first_body["answer"]

    session = get_session_factory()()
    session.execute(text("SET ROLE aks_app"))
    try:
        set_db_tenant_context(session, seeded.tenant_id)
        rows = (
            session.execute(
                select(Query)
                .where(Query.tenant_id == seeded.tenant_id)
                .order_by(Query.created_at.asc())
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        assert rows[0].cache_hit is False
        assert rows[1].cache_hit is True
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


def test_query_top_k_out_of_bounds_rejected(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)
    seeded = seed_user(
        "tenant-q2", "editor-q2@tenant.example", "StrongPass!1234", ("editor",)
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"query": "hello", "top_k": 99, "filters": {}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TOP_K_OUT_OF_RANGE"


def test_query_stream_accepts_top_k_25(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    seeded = seed_user(
        "tenant-q-stream",
        "editor-q-stream@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)

    async def fake_stream_execute(
        self: QueryService, **_: object
    ) -> AsyncIterator[str]:
        yield 'event: replace\ndata: {"content":"ok"}\n\n'
        yield "event: done\ndata: {}\n\n"

    monkeypatch.setattr(QueryService, "stream_execute", fake_stream_execute)

    with client.stream(
        "POST",
        "/api/v1/queries/stream",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"query": "hello", "top_k": 25, "filters": {}},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: replace" in body
    assert '"content":"ok"' in body


def test_query_invalid_filter_field_rejected(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-q3", "editor-q3@tenant.example", "StrongPass!1234", ("editor",)
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"query": "hello", "top_k": 5, "filters": {"unknown_field": "x"}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER_FIELD"
