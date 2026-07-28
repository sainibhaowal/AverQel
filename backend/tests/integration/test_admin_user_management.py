from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.auth.roles import canonicalize_role_name
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.document import Document
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.system.models.audit_log import AuditLog
from app.system.models.break_glass_grant import BreakGlassGrant
from tests.conftest import SeededUser, _generate_test_collection_code

pytestmark = pytest.mark.db_commit


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _add_user_to_tenant(*, tenant_id, email: str, role_name: str) -> str:
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, tenant_id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            email=email,
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
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
        return str(user.id)
    finally:
        session.rollback()
        session.close()


def test_admin_can_list_and_disable_users(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "tenant-admin-users",
        "owner@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    target_user_id = _add_user_to_tenant(
        tenant_id=owner.tenant_id,
        email="member@example.org",
        role_name="editor",
    )
    access_token = _login(client, owner)

    list_response = client.get(
        "/api/v1/admin/users",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload["items"]) == 2

    disable_response = client.post(
        f"/api/v1/admin/users/{target_user_id}/disable",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert disable_response.status_code == 200

    detail_response = client.get(
        f"/api/v1/admin/users/{target_user_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["user"]["is_active"] is False


def test_admin_can_delete_non_protected_user(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "tenant-admin-users-delete",
        "owner-delete@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    target_user_id = _add_user_to_tenant(
        tenant_id=owner.tenant_id,
        email="delete-me@example.org",
        role_name="editor",
    )
    access_token = _login(client, owner)

    delete_response = client.delete(
        f"/api/v1/admin/users/{target_user_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_user_id"] == target_user_id

    list_response = client.get(
        "/api/v1/admin/users",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert list_response.status_code == 200
    emails = [item["email"] for item in list_response.json()["items"]]
    assert "delete-me@example.org" not in emails


def test_admin_can_list_users_across_workspaces(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "platform-owner-tenant",
        "owner-platform@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    other = seed_user(
        "other-tenant",
        "other-tenant-user@example.org",
        "StrongPass!1234",
        ("editor",),
    )
    access_token = _login(client, owner)

    response = client.get(
        "/api/v1/admin/users",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert response.status_code == 200
    emails = {item["email"] for item in response.json()["items"]}
    assert owner.email in emails
    assert other.email in emails


def test_non_allowlisted_admin_role_cannot_access_admin_routes(
    client: TestClient,
    seed_user,
) -> None:
    seeded = seed_user(
        "tenant-admin-allowlist",
        "stale-admin@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = ["owner-only@example.org"]
    access_token = _login(client, seeded)

    response = client.get(
        "/api/v1/admin/users",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_document_summary_is_metadata_only(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "tenant-admin-doc-summary",
        "owner-doc-summary@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, owner.tenant_id)
        session.add(
            Document(
                id=generate_uuid7_with_fallback(),
                tenant_id=owner.tenant_id,
                uploaded_by_user_id=owner.user_id,
                filename="private-contract.pdf",
                content_type="application/pdf",
                size_bytes=4096,
                sha256_hash="b" * 64,
                storage_bucket="private-bucket",
                storage_object_key="raw/private/path.pdf",
                status="failed",
                quarantined=True,
            )
        )
        session.commit()
    finally:
        session.rollback()
        session.close()
    access_token = _login(client, owner)

    response = client.get(
        "/api/v1/admin/documents/summary",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )

    assert response.status_code == 200
    body_text = response.text
    assert "private-contract.pdf" not in body_text
    assert "private-bucket" not in body_text
    assert "raw/private/path.pdf" not in body_text
    item = response.json()["items"][0]
    assert item["documents_count"] == 1
    assert item["storage_bytes"] == 4096
    assert item["quarantined_count"] == 1
    assert item["error_count"] == 1


def test_break_glass_requires_reason_creates_limited_grant_and_audit(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "tenant-break-glass",
        "owner-break-glass@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    previous_break_glass_enabled = get_settings().admin_break_glass_enabled
    get_settings().admin_break_glass_enabled = True
    target_user_id = _add_user_to_tenant(
        tenant_id=owner.tenant_id,
        email="break-glass-target@example.org",
        role_name="editor",
    )
    try:
        access_token = _login(client, owner)

        invalid = client.post(
            "/api/v1/admin/break-glass",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Tenant-Id": str(owner.tenant_id),
            },
            json={
                "target_user_id": target_user_id,
                "target_tenant_id": str(owner.tenant_id),
                "resource_type": "document",
                "reason": "too short",
                "duration_minutes": 30,
            },
        )
        assert invalid.status_code == 422

        response = client.post(
            "/api/v1/admin/break-glass",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Tenant-Id": str(owner.tenant_id),
            },
            json={
                "target_user_id": target_user_id,
                "target_tenant_id": str(owner.tenant_id),
                "resource_type": "document",
                "resource_id": "doc-123",
                "reason": "Support ticket 123 requires document access investigation.",
                "duration_minutes": 15,
            },
        )
        assert response.status_code == 200
        grant_id = response.json()["grant_id"]

        session = get_session_factory()()
        try:
            set_db_tenant_context(session, owner.tenant_id)
            grant = session.get(BreakGlassGrant, grant_id)
            assert grant is not None
            assert grant.status == "active"
            assert grant.reason.startswith("Support ticket")
            audit = session.execute(
                select(AuditLog).where(AuditLog.action == "admin.break_glass.grant")
            ).scalar_one()
            assert audit.details["reason"].startswith("Support ticket")
        finally:
            session.rollback()
            session.close()

        revoke = client.post(
            f"/api/v1/admin/break-glass/{grant_id}/revoke",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Tenant-Id": str(owner.tenant_id),
            },
        )
        assert revoke.status_code == 200
    finally:
        get_settings().admin_break_glass_enabled = previous_break_glass_enabled


def test_break_glass_is_disabled_by_default(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "tenant-break-glass-disabled",
        "owner-break-glass-disabled@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    settings = get_settings()
    settings.bootstrap_super_admin_emails = [owner.email]
    settings.admin_break_glass_enabled = False
    target_user_id = _add_user_to_tenant(
        tenant_id=owner.tenant_id,
        email="break-glass-disabled-target@example.org",
        role_name="editor",
    )
    access_token = _login(client, owner)

    response = client.post(
        "/api/v1/admin/break-glass",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
        json={
            "target_user_id": target_user_id,
            "target_tenant_id": str(owner.tenant_id),
            "resource_type": "document",
            "resource_id": "doc-123",
            "reason": "Support ticket 456 requires document access investigation.",
            "duration_minutes": 15,
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Break-glass access is disabled for this deployment."
    )
