from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select

from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.auth.roles import canonicalize_role_name
from app.auth.security import hash_password
from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.system.services.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser, _generate_test_collection_code


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


def _add_user_to_existing_tenant(
    *, tenant_id, email: str, password: str, role_name: str = "reader"
) -> SeededUser:
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, tenant_id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            email=email,
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(user)
        session.flush()
        role = session.execute(
            select(Role).where(Role.name == canonicalize_role_name(role_name))
        ).scalar_one()
        session.add(
            UserRole(
                id=generate_uuid7_with_fallback(),
                tenant_id=tenant_id,
                user_id=user.id,
                role_id=role.id,
            )
        )
        session.commit()
        return SeededUser(
            tenant_id=tenant_id,
            user_id=user.id,
            collection_code=user.collection_code,
            email=email,
            password=password,
        )
    finally:
        session.rollback()
        session.close()


def test_cross_tenant_retrieval_has_no_leakage(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)

    tenant_a = seed_user("tenant-r-a", "editor-a@tenant.example", "StrongPass!1234", ("editor",))
    tenant_b = seed_user("tenant-r-b", "reader-b@tenant.example", "StrongPass!1234", ("reader",))

    token_a = _login(client, tenant_a)
    token_b = _login(client, tenant_b)

    upload = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Tenant-Id": str(tenant_a.tenant_id),
            "Idempotency-Key": "idem-isolation-a",
        },
        files={"file": ("tenant-a.txt", b"Tenant A private policy content", "text/plain")},
    )
    assert upload.status_code == 200

    query_b = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Tenant-Id": str(tenant_b.tenant_id),
        },
        json={"query": "private policy", "top_k": 5, "filters": {}},
    )
    assert query_b.status_code == 200
    payload = query_b.json()
    assert payload["citations"] == []
    assert payload["confidence"] == 0.0
    assert payload["answer"] == "No relevant information found for the requested query."


def test_same_tenant_query_cache_does_not_cross_user_access_scope(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    """A cached answer for one tenant member must not reach another member."""
    _patch_storage(monkeypatch)

    owner = seed_user(
        "tenant-r-same-tenant",
        "owner@same-tenant.example",
        "StrongPass!1234",
        ("editor",),
    )
    viewer = _add_user_to_existing_tenant(
        tenant_id=owner.tenant_id,
        email="viewer@same-tenant.example",
        password="StrongPass!1234",
    )
    owner_token = _login(client, owner)
    viewer_token = _login(client, viewer)

    upload = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-Id": str(owner.tenant_id),
            "Idempotency-Key": "idem-same-tenant-cache-owner",
        },
        files={"file": ("owner-private.txt", b"Owner private policy content", "text/plain")},
    )
    assert upload.status_code == 200

    owner_query = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
        json={"query": "private policy", "top_k": 5, "filters": {}},
    )
    assert owner_query.status_code == 200
    assert owner_query.json()["citations"]

    viewer_query = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {viewer_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
        json={"query": "private policy", "top_k": 5, "filters": {}},
    )
    assert viewer_query.status_code == 200
    viewer_payload = viewer_query.json()
    assert viewer_payload["cached"] is False
    assert viewer_payload["citations"] == []
    assert viewer_payload["confidence"] == 0.0


def test_query_tenant_scope_mismatch_rejected(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    tenant_a = seed_user("tenant-r-c", "reader-c@tenant.example", "StrongPass!1234", ("reader",))
    tenant_b = seed_user("tenant-r-d", "reader-d@tenant.example", "StrongPass!1234", ("reader",))

    token_a = _login(client, tenant_a)
    response = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Tenant-Id": str(tenant_b.tenant_id),
        },
        json={"query": "test", "top_k": 5, "filters": {}},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_SCOPE_MISMATCH"
