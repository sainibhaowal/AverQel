from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.models.user import User
from app.auth.security import hash_password
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.document import Document
from app.platform.database.session import get_session_factory, set_db_tenant_context
from tests.conftest import SeededUser, _generate_test_collection_code


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_collections_admin_management_routes_allow_add_list_and_remove(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-coll-admin",
        "admin-coll@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    token = _login(client, seeded)

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)

        extra_user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=seeded.tenant_id,
            email="viewer-coll@tenant.example",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        document = Document(
            id=generate_uuid7_with_fallback(),
            tenant_id=seeded.tenant_id,
            uploaded_by_user_id=seeded.user_id,
            filename="collection-doc.txt",
            content_type="text/plain",
            size_bytes=21,
            sha256_hash="a" * 64,
            storage_bucket="averqel",
            storage_object_key=f"{seeded.tenant_id}/collection-doc.txt",
            status="ready",
        )
        session.add(extra_user)
        session.add(document)
        session.commit()
        extra_user_id = extra_user.id
        extra_user_code = extra_user.collection_code
        document_id = document.id
    finally:
        session.execute(text("RESET ROLE"))
        session.close()

    create = client.post(
        "/api/v1/collections",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"name": "Research", "description": "Papers"},
    )
    assert create.status_code == 201
    collection_id = create.json()["id"]

    add_documents = client.post(
        f"/api/v1/collections/{collection_id}/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"document_ids": [str(document_id)]},
    )
    assert add_documents.status_code == 204

    list_documents = client.get(
        f"/api/v1/collections/{collection_id}/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert list_documents.status_code == 200
    assert len(list_documents.json()) == 1

    add_permissions = client.post(
        f"/api/v1/collections/{collection_id}/permissions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"connection_code": extra_user_code},
    )
    assert add_permissions.status_code == 204

    list_permissions = client.get(
        f"/api/v1/collections/{collection_id}/permissions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert list_permissions.status_code == 200
    permission_rows = list_permissions.json()
    permission_user_ids = {item["user_id"] for item in permission_rows}
    assert str(extra_user_id) in permission_user_ids
    assert str(seeded.user_id) in permission_user_ids
    assert {item["user_id"]: item["role"] for item in permission_rows}[
        str(extra_user_id)
    ] == "pending"

    remove_documents = client.request(
        "DELETE",
        f"/api/v1/collections/{collection_id}/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"document_ids": [str(document_id)]},
    )
    assert remove_documents.status_code == 204

    remove_permissions = client.request(
        "DELETE",
        f"/api/v1/collections/{collection_id}/permissions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"user_ids": [str(extra_user_id)]},
    )
    assert remove_permissions.status_code == 204

    list_documents_after = client.get(
        f"/api/v1/collections/{collection_id}/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert list_documents_after.status_code == 200
    assert list_documents_after.json() == []

    list_permissions_after = client.get(
        f"/api/v1/collections/{collection_id}/permissions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert list_permissions_after.status_code == 200
    permission_user_ids_after = {
        item["user_id"] for item in list_permissions_after.json()
    }
    assert str(extra_user_id) not in permission_user_ids_after
    assert str(seeded.user_id) in permission_user_ids_after

    delete_collection = client.request(
        "DELETE",
        f"/api/v1/collections/{collection_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert delete_collection.status_code == 204

    get_deleted_collection = client.get(
        f"/api/v1/collections/{collection_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert get_deleted_collection.status_code == 404


def test_shared_user_can_only_disconnect_self(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    owner = seed_user(
        "tenant-coll-shared",
        "owner-coll@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )
    shared_user = seed_user(
        "tenant-coll-shared",
        "shared-coll@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )
    owner_token = _login(client, owner)
    shared_token = _login(client, shared_user)

    create = client.post(
        "/api/v1/collections",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
        json={"name": "Shared Research", "description": "Shared docs"},
    )
    assert create.status_code == 201
    assert create.json()["requester_access_role"] == "member"
    collection_id = create.json()["id"]

    add_permissions = client.post(
        f"/api/v1/collections/{collection_id}/permissions",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
        json={"connection_code": shared_user.collection_code},
    )
    assert add_permissions.status_code == 204

    pending_list = client.get(
        "/api/v1/collections/invitations",
        headers={
            "Authorization": f"Bearer {shared_token}",
            "X-Tenant-Id": str(shared_user.tenant_id),
        },
    )
    assert pending_list.status_code == 200
    assert pending_list.json()[0]["requester_access_role"] == "pending"

    approve = client.post(
        f"/api/v1/collections/{collection_id}/invitations/respond",
        headers={
            "Authorization": f"Bearer {shared_token}",
            "X-Tenant-Id": str(shared_user.tenant_id),
        },
        json={"action": "approve"},
    )
    assert approve.status_code == 204

    permissions_after_owner_attempt = client.get(
        f"/api/v1/collections/{collection_id}/permissions",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert permissions_after_owner_attempt.status_code == 200
    assert {item["user_id"] for item in permissions_after_owner_attempt.json()} == {
        str(owner.user_id),
        str(shared_user.user_id),
    }

    shared_disconnect = client.request(
        "DELETE",
        f"/api/v1/collections/{collection_id}/permissions",
        headers={
            "Authorization": f"Bearer {shared_token}",
            "X-Tenant-Id": str(shared_user.tenant_id),
        },
        json={"user_ids": [str(shared_user.user_id)]},
    )
    assert shared_disconnect.status_code == 204

    shared_list_after = client.get(
        "/api/v1/collections",
        headers={
            "Authorization": f"Bearer {shared_token}",
            "X-Tenant-Id": str(shared_user.tenant_id),
        },
    )
    assert shared_list_after.status_code == 200
    assert shared_list_after.json() == []


def test_shared_user_in_different_tenant_can_see_shared_collection_documents(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    owner = seed_user(
        "tenant-coll-owner-x",
        "owner-cross@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )
    shared_user = seed_user(
        "tenant-coll-recipient-x",
        "shared-cross@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )
    owner_token = _login(client, owner)
    shared_token = _login(client, shared_user)

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, owner.tenant_id)
        document = Document(
            id=generate_uuid7_with_fallback(),
            tenant_id=owner.tenant_id,
            uploaded_by_user_id=owner.user_id,
            filename="shared-cross-doc.txt",
            content_type="text/plain",
            size_bytes=21,
            sha256_hash="b" * 64,
            storage_bucket="averqel",
            storage_object_key=f"{owner.tenant_id}/shared-cross-doc.txt",
            status="indexed",
        )
        session.add(document)
        session.commit()
        document_id = document.id
    finally:
        session.execute(text("RESET ROLE"))
        session.close()

    create = client.post(
        "/api/v1/collections",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
        json={"name": "Cross Tenant Share", "description": "Shared docs"},
    )
    assert create.status_code == 201
    collection_id = create.json()["id"]

    add_documents = client.post(
        f"/api/v1/collections/{collection_id}/documents",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
        json={"document_ids": [str(document_id)]},
    )
    assert add_documents.status_code == 204

    add_permissions = client.post(
        f"/api/v1/collections/{collection_id}/permissions",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
        json={"connection_code": shared_user.collection_code},
    )
    assert add_permissions.status_code == 204

    approve = client.post(
        f"/api/v1/collections/{collection_id}/invitations/respond",
        headers={
            "Authorization": f"Bearer {shared_token}",
            "X-Tenant-Id": str(shared_user.tenant_id),
        },
        json={"action": "approve"},
    )
    assert approve.status_code == 204

    shared_list = client.get(
        "/api/v1/collections",
        headers={
            "Authorization": f"Bearer {shared_token}",
            "X-Tenant-Id": str(shared_user.tenant_id),
        },
    )
    assert shared_list.status_code == 200
    assert len(shared_list.json()) == 1
    assert shared_list.json()[0]["requester_access_role"] == "member"

    shared_documents = client.get(
        f"/api/v1/collections/{collection_id}/documents",
        headers={
            "Authorization": f"Bearer {shared_token}",
            "X-Tenant-Id": str(shared_user.tenant_id),
        },
    )
    assert shared_documents.status_code == 200
    assert [item["filename"] for item in shared_documents.json()] == [
        "shared-cross-doc.txt"
    ]
