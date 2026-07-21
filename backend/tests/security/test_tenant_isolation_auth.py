from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.auth.models.user import User
from app.core.config import Settings, get_settings
from app.platform.database.session import get_session_factory, set_db_tenant_context
from tests.conftest import SeededUser

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def test_cross_tenant_request_is_rejected_by_app_scope(
    client: TestClient,
    settings: Settings,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    tenant_a = seed_user(
        "tenant-scope-a",
        "admin-a@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    tenant_b = seed_user(
        "tenant-scope-b",
        "admin-b@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [tenant_a.email]

    login_response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(tenant_a.tenant_id)},
        json={"email": tenant_a.email, "password": tenant_a.password},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    cross_tenant_response = client.get(
        "/api/v1/admin/audit-logs",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(tenant_b.tenant_id),
        },
    )
    assert cross_tenant_response.status_code == 403
    assert cross_tenant_response.json()["error"]["code"] == "TENANT_SCOPE_MISMATCH"


def test_rls_blocks_cross_tenant_read_without_tenant_filter(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    tenant_a = seed_user(
        "tenant-rls-a",
        "reader-a@example.com",
        "StrongPass!1234",
        ("reader",),
    )
    tenant_b = seed_user(
        "tenant-rls-b",
        "reader-b@example.com",
        "StrongPass!1234",
        ("reader",),
    )

    session = get_session_factory()()
    session.execute(text("SET ROLE aks_app"))
    try:
        set_db_tenant_context(session, tenant_a.tenant_id)
        leaked_user = session.execute(
            select(User).where(User.id == tenant_b.user_id)
        ).scalar_one_or_none()
        assert leaked_user is None
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


def test_invalid_jwt_signature_is_rejected(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    settings: Settings,
) -> None:
    seeded = seed_user(
        "tenant-signature-check",
        "reader-signature@example.com",
        "StrongPass!1234",
        ("reader",),
    )
    now = datetime.now(tz=UTC)
    claims = {
        "sub": str(seeded.user_id),
        "tenant_id": str(seeded.tenant_id),
        "roles": ["reader"],
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(
        claims,
        "wrong-signing-secret-with-minimum-32-chars-123456",
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(
        "/api/v1/admin/audit-logs",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_ACCESS_TOKEN"


def test_expired_jwt_is_rejected(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    settings: Settings,
) -> None:
    seeded = seed_user(
        "tenant-expiry-check",
        "reader-expired@example.com",
        "StrongPass!1234",
        ("reader",),
    )
    now = datetime.now(tz=UTC)
    claims = {
        "sub": str(seeded.user_id),
        "tenant_id": str(seeded.tenant_id),
        "roles": ["reader"],
        "jti": str(uuid4()),
        "iat": int((now - timedelta(minutes=30)).timestamp()),
        "exp": int((now - timedelta(minutes=1)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = client.get(
        "/api/v1/admin/audit-logs",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ACCESS_TOKEN_EXPIRED"
