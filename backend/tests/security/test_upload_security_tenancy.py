from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select, text

from app.db.session import get_session_factory, set_db_tenant_context
from app.models.documents.document import Document
from app.services.system.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_cross_tenant_document_read_denied(
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

    tenant_a = seed_user(
        "tenant-sec-a", "editor-a@tenant.example", "StrongPass!1234", ("editor",)
    )
    tenant_b = seed_user(
        "tenant-sec-b", "reader-b@tenant.example", "StrongPass!1234", ("reader",)
    )

    token_a = _login(client, tenant_a)
    token_b = _login(client, tenant_b)

    upload = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Tenant-Id": str(tenant_a.tenant_id),
            "Idempotency-Key": "idem-security-tenant",
        },
        files={"file": ("tenant-a.txt", b"tenant-a-content", "text/plain")},
    )
    assert upload.status_code == 200
    document_id = upload.json()["document_id"]

    cross_read = client.get(
        f"/api/v1/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Tenant-Id": str(tenant_b.tenant_id),
        },
    )
    assert cross_read.status_code == 404
    assert cross_read.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_upload_validation_blocks_invalid_mime(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_put(
        self: StorageService,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> StoredObject:
        del self, tenant_id, document_id, filename, payload
        return StoredObject(
            bucket="aks-documents",
            object_key="ignored",
            etag="ignored",
            size_bytes=0,
            content_type=content_type,
        )

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)

    seeded = seed_user(
        "tenant-sec-c", "editor-c@tenant.example", "StrongPass!1234", ("editor",)
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-security-invalid-mime",
        },
        files={"file": ("payload.exe", b"MZ", "application/x-msdownload")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD_TYPE"


def test_malware_scan_blocked_path(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-sec-d", "editor-d@tenant.example", "StrongPass!1234", ("editor",)
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-security-malware",
        },
        files={
            "file": (
                "eicar.txt",
                b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*",
                "text/plain",
            )
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MALWARE_SCAN_FAILED"

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        doc_count = session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == seeded.tenant_id)
        ).scalar_one()
        assert doc_count == 0
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
