from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core.config import get_settings
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

    def fake_delete(self: StorageService, *, bucket: str, object_key: str) -> None:
        in_memory_objects.pop((bucket, object_key), None)

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)
    monkeypatch.setattr(StorageService, "delete_object", fake_delete)


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_week4_e2e_security_reliability_flow(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)
    seeded = seed_user(
        "tenant-week4-e2e",
        "admin-week4-e2e@tenant.example",
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
            "Idempotency-Key": "idem-week4-e2e-1",
        },
        files={
            "file": (
                "week4-e2e.txt",
                b"SLA content for week 4 end-to-end flow",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 200

    query = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"query": "what SLA content exists?", "top_k": 5, "filters": {}},
    )
    assert query.status_code == 200

    delete_create = client.post(
        "/api/v1/admin/data-deletions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"reason": "week4 e2e cleanup"},
    )
    assert delete_create.status_code == 200
    deletion_id = delete_create.json()["deletion_id"]

    delete_status = client.get(
        f"/api/v1/admin/data-deletions/{deletion_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert delete_status.status_code == 200

    audit = client.get(
        "/api/v1/admin/audit-logs?limit=50",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert audit.status_code == 200
    assert "items" in audit.json()
