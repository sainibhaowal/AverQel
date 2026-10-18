from __future__ import annotations

from datetime import UTC, datetime

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
from app.ingestion.models.ingestion_job import IngestionJob
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.system.models.audit_log import AuditLog
from app.system.models.break_glass_grant import BreakGlassGrant
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.services.storage_service import StorageService
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
    account = next(item for item in payload["items"] if item["user_id"] == target_user_id)
    assert set(account) == {
        "user_id",
        "tenant_id",
        "tenant_name",
        "email",
        "is_active",
        "totp_enabled",
        "roles",
    }
    assert account["email"] == "member@example.org"
    assert account["is_active"] is True
    assert account["totp_enabled"] is False
    assert account["roles"] == ["editor"]

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
    assert set(detail_response.json()) == {"user"}
    assert "stats" not in detail_response.text
    assert "recent_activity" not in detail_response.text

    audit_response = client.get(
        "/api/v1/admin/audit-logs?limit=100",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert audit_response.status_code == 200
    audit_items = audit_response.json()["items"]
    actions = {item["action"] for item in audit_items}
    assert "admin.users.list.read" in actions
    assert "admin.user.read" in actions
    assert "admin.user.disabled" in actions
    assert all("ip_address" not in item and "details" not in item for item in audit_items)


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
    assert set(delete_response.json()) == {"success", "deleted_user_id"}

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


def test_admin_user_deletion_queues_failed_document_object_cleanup(
    client: TestClient,
    seed_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = seed_user(
        "tenant-admin-delete-cleanup",
        "owner-delete-cleanup@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    target_user_id = _add_user_to_tenant(
        tenant_id=owner.tenant_id,
        email="member-delete-cleanup@example.org",
        role_name="editor",
    )
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, owner.tenant_id)
        session.add(
            Document(
                id=generate_uuid7_with_fallback(),
                tenant_id=owner.tenant_id,
                uploaded_by_user_id=target_user_id,
                filename="private-admin-delete.txt",
                content_type="text/plain",
                size_bytes=12,
                sha256_hash="d" * 64,
                storage_bucket="private-admin-delete-bucket",
                storage_object_key="private-admin-delete/path.txt",
                status="ready",
            )
        )
        session.commit()
    finally:
        session.rollback()
        session.close()

    def fail_delete(
        self: StorageService,
        *,
        bucket: str,
        object_key: str,
        raise_on_error: bool = False,
    ) -> None:
        raise RuntimeError("private provider error")

    monkeypatch.setattr(StorageService, "delete_object", fail_delete)
    response = client.delete(
        f"/api/v1/admin/users/{target_user_id}",
        headers={
            "Authorization": f"Bearer {_login(client, owner)}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )
    assert response.status_code == 200

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, owner.tenant_id)
        job = session.execute(
            select(StorageCleanupJob).where(
                StorageCleanupJob.tenant_id == owner.tenant_id,
                StorageCleanupJob.owner_user_id == target_user_id,
            )
        ).scalar_one()
        assert job.status == "pending"
        assert job.last_error == "storage_delete_failed"
    finally:
        session.rollback()
        session.close()


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


def test_admin_workspace_list_exposes_seat_and_status_metadata_only(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "tenant-admin-workspaces",
        "owner-workspaces@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    access_token = _login(client, owner)

    response = client.get(
        "/api/v1/admin/tenants",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(owner.tenant_id),
        },
    )

    assert response.status_code == 200
    workspace = next(
        item for item in response.json()["items"] if item["tenant_id"] == str(owner.tenant_id)
    )
    assert workspace["seats_used"] == 1
    assert workspace["status"] == "active"
    assert "stats" not in workspace
    assert "last_activity_at" not in workspace
    assert "documents_count" not in workspace
    assert "queries_count" not in workspace


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
    assert item["quarantined_count"] == 1
    assert item["error_count"] == 1
    assert set(item) == {"tenant_id", "quarantined_count", "error_count"}
    assert "documents_count" not in body_text
    assert "storage_bytes" not in body_text


def test_admin_processing_and_cleanup_diagnostics_omit_content_identifiers_and_errors(
    client: TestClient,
    seed_user,
) -> None:
    owner = seed_user(
        "tenant-admin-processing-diagnostics",
        "owner-processing-diagnostics@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    document_id = generate_uuid7_with_fallback()
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, owner.tenant_id)
        session.add(
            Document(
                id=document_id,
                tenant_id=owner.tenant_id,
                uploaded_by_user_id=owner.user_id,
                filename="private-processing-document.pdf",
                content_type="application/pdf",
                size_bytes=4096,
                sha256_hash="c" * 64,
                storage_bucket="private-diagnostics-bucket",
                storage_object_key="private-diagnostics/path.pdf",
                status="failed",
            )
        )
        session.flush()
        session.add(
            IngestionJob(
                id=generate_uuid7_with_fallback(),
                tenant_id=owner.tenant_id,
                document_id=document_id,
                status="failed",
                max_attempts=3,
                checkpoint_stage="embedding",
                checkpoint_cursor=77,
                checkpoint_updated_at=datetime.now(UTC),
                resume_count=2,
                last_error_code="PROVIDER_TIMEOUT",
                last_error_message="PRIVATE-ERROR-CONTENT must not be returned",
            )
        )
        session.add(
            StorageCleanupJob(
                tenant_id=owner.tenant_id,
                owner_user_id=owner.user_id,
                bucket="private-cleanup-bucket",
                object_key="private-cleanup/private-file.pdf",
                last_error="PRIVATE-CLEANUP-ERROR must not be returned",
            )
        )
        session.commit()
    finally:
        session.rollback()
        session.close()

    headers = {
        "Authorization": f"Bearer {_login(client, owner)}",
        "X-Tenant-Id": str(owner.tenant_id),
    }
    recovery = client.get("/api/v1/admin/documents/recovery-history", headers=headers)
    assert recovery.status_code == 200
    recovery_payload = recovery.json()["items"][0]
    assert set(recovery_payload) == {
        "job_id",
        "status",
        "checkpoint_stage",
        "checkpoint_updated_at",
        "resume_count",
        "last_error_code",
        "updated_at",
    }
    assert recovery_payload["last_error_code"] == "PROVIDER_TIMEOUT"

    cleanup = client.get("/api/v1/admin/storage-cleanup", headers=headers)
    assert cleanup.status_code == 200
    cleanup_payload = cleanup.json()["items"][0]
    assert set(cleanup_payload) == {
        "id",
        "tenant_id",
        "status",
        "attempts",
        "next_attempt_at",
        "created_at",
    }
    for private_value in (
        "private-processing-document.pdf",
        "private-diagnostics-bucket",
        "private-diagnostics/path.pdf",
        "PRIVATE-ERROR-CONTENT",
        "private-cleanup-bucket",
        "private-cleanup/private-file.pdf",
        "PRIVATE-CLEANUP-ERROR",
    ):
        assert private_value not in recovery.text + cleanup.text


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
