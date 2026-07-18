from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core.config import Settings
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


def test_unsupported_extension_path(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-fail-ext", "user-ext@example.com", "Password!123", ("editor",)
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-fail-ext",
        },
        files={
            "file": ("bad_file.bin", b"some binary data", "application/octet-stream")
        },
    )
    # The API might allow basic upload for `.bin` if not strictly checked at API edge,
    # but the settings.upload_allowed_extensions guards it.
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD_TYPE"


def test_oversize_file_path(
    client: TestClient,
    settings: Settings,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    settings.upload_max_bytes = 100  # Artificially low limit for testing
    seeded = seed_user(
        "tenant-fail-size", "user-size@example.com", "Password!123", ("editor",)
    )
    token = _login(client, seeded)

    large_payload = b"x" * 200

    response = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-fail-size",
        },
        files={"file": ("large.txt", large_payload, "text/plain")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "DOC_TOO_LARGE"


def test_corrupted_file_path(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)
    seeded = seed_user(
        "tenant-fail-corrupted", "user-corr@example.com", "Password!123", ("editor",)
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-fail-corr",
        },
        files={
            "file": ("corrupted.pdf", b"this is not a valid pdf", "application/pdf")
        },
    )
    assert response.status_code == 200
    doc_id = response.json()["document_id"]

    import time

    start = time.time()
    while time.time() - start < 10:
        res = client.get(
            f"/api/v1/documents/{doc_id}/status",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": str(seeded.tenant_id),
            },
        )
        assert res.status_code == 200
        data = res.json()
        if data["status"] in ("failed", "dead_lettered"):
            # A completely invalid PDF with no fallbacks available (if ocr fails on non-image/pdf)
            # or yielding 0 text leads to DOCUMENT_EMPTY_AFTER_PARSE
            assert data["last_error_code"] in [
                "DOCUMENT_EMPTY_AFTER_PARSE",
                "IMAGE_PARSE_FAILED",
                "PDF_PARSE_FAILED",
            ]
            return
        time.sleep(0.5)
    raise TimeoutError("Document did not fail as expected")
