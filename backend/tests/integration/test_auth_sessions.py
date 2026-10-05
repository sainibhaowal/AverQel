from __future__ import annotations

import importlib.util
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.models.auth_session import AuthSession
from app.auth.models.refresh_token import RefreshToken
from app.auth.models.user import User
from app.core.config import get_settings
from app.platform.database.session import set_db_tenant_context
from app.system.workers.tasks_maintenance import retention_cleanup
from tests.conftest import SeededUser


def _login(client: TestClient, user: SeededUser, device_id: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(user.tenant_id)},
        json={
            "email": user.email,
            "password": user.password,
            "device_id": device_id,
            "device_label": "Chrome on Linux",
        },
    )
    assert response.status_code == 200
    refresh_cookie = SimpleCookie()
    refresh_cookie.load(response.headers["set-cookie"])
    return response.json()["access_token"], refresh_cookie[get_settings().refresh_cookie_name].value


def test_user_can_revoke_another_session_but_not_the_current_one(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-sessions",
        "sessions@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    first_token, first_refresh = _login(client, seeded, "browser-session-one")
    first_headers = {
        "X-Tenant-Id": str(seeded.tenant_id),
        "Authorization": f"Bearer {first_token}",
    }

    first_list = client.get("/api/v1/auth/sessions", headers=first_headers)
    assert first_list.status_code == 200
    first_session = first_list.json()[0]
    assert first_session["device_id"] == "browser-session-one"
    assert first_session["label"] == "Chrome on Linux"
    assert first_session["current"] is True

    current_revoke = client.delete(
        f"/api/v1/auth/sessions/{first_session['id']}", headers=first_headers
    )
    assert current_revoke.status_code == 409
    assert current_revoke.json()["error"]["code"] == "CURRENT_SESSION_CANNOT_BE_REVOKED"

    second_token, _second_refresh = _login(client, seeded, "browser-session-two")
    second_headers = {
        "X-Tenant-Id": str(seeded.tenant_id),
        "Authorization": f"Bearer {second_token}",
    }
    second_list = client.get("/api/v1/auth/sessions", headers=second_headers)
    assert second_list.status_code == 200
    assert len(second_list.json()) == 2
    assert sum(row["current"] for row in second_list.json()) == 1

    page_one = client.get("/api/v1/auth/sessions?limit=1&offset=0", headers=second_headers)
    page_two = client.get("/api/v1/auth/sessions?limit=1&offset=1", headers=second_headers)
    assert page_one.status_code == page_two.status_code == 200
    assert len(page_one.json()) == len(page_two.json()) == 1
    assert page_one.json()[0]["id"] != page_two.json()[0]["id"]

    revoked = client.delete(f"/api/v1/auth/sessions/{first_session['id']}", headers=second_headers)
    assert revoked.status_code == 200
    assert revoked.json() == {"success": True}

    old_access = client.get("/api/v1/auth/profile", headers=first_headers)
    assert old_access.status_code == 401
    assert old_access.json()["error"]["code"] == "SESSION_REVOKED"

    old_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{get_settings().refresh_cookie_name}={first_refresh}"},
    )
    assert old_refresh.status_code == 401
    assert old_refresh.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"


def test_session_list_and_revoke_are_scoped_to_tenant_and_owner(
    client: TestClient,
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    first = seed_user(
        "tenant-auth-owner-one", "owner-one@example.test", "StrongPass!1234", ("admin",)
    )
    second = seed_user(
        "tenant-auth-owner-two", "owner-two@example.test", "StrongPass!1234", ("admin",)
    )
    first_token, _ = _login(client, first, "browser-owner-one")
    second_token, _ = _login(client, second, "browser-owner-two")
    first_headers = {
        "X-Tenant-Id": str(first.tenant_id),
        "Authorization": f"Bearer {first_token}",
    }
    second_headers = {
        "X-Tenant-Id": str(second.tenant_id),
        "Authorization": f"Bearer {second_token}",
    }
    first_session = client.get("/api/v1/auth/sessions", headers=first_headers).json()[0]
    second_session = client.get("/api/v1/auth/sessions", headers=second_headers).json()[0]

    assert first_session["device_id"] == "browser-owner-one"
    assert client.get("/api/v1/auth/sessions", headers=first_headers).json() == [first_session]
    foreign_revoke = client.delete(
        f"/api/v1/auth/sessions/{second_session['id']}", headers=first_headers
    )
    assert foreign_revoke.status_code == 404
    assert client.get("/api/v1/auth/profile", headers=second_headers).status_code == 200

    db_session.execute(text("SET LOCAL ROLE aks_app"))
    db_session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(first.tenant_id)},
    )
    visible_tenants = set(db_session.execute(text("SELECT tenant_id FROM auth_sessions")).scalars())
    assert visible_tenants == {first.tenant_id}
    db_session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    assert db_session.execute(text("SELECT id FROM auth_sessions")).all() == []


def test_refresh_token_reuse_revokes_the_session_and_rotated_token(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-session-reuse",
        "refresh-reuse@example.test",
        "StrongPass!1234",
        ("admin",),
    )
    _access_token, original_refresh = _login(client, seeded, "browser-refresh-reuse")
    rotated = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{get_settings().refresh_cookie_name}={original_refresh}"},
    )
    assert rotated.status_code == 200
    rotated_cookie = SimpleCookie()
    rotated_cookie.load(rotated.headers["set-cookie"])
    rotated_refresh = rotated_cookie[get_settings().refresh_cookie_name].value
    rotated_headers = {
        "X-Tenant-Id": str(seeded.tenant_id),
        "Authorization": f"Bearer {rotated.json()['access_token']}",
    }

    replay = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{get_settings().refresh_cookie_name}={original_refresh}"},
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"
    rejected_access = client.get("/api/v1/auth/profile", headers=rotated_headers)
    assert rejected_access.status_code == 401
    assert rejected_access.json()["error"]["code"] == "SESSION_REVOKED"
    rejected_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{get_settings().refresh_cookie_name}={rotated_refresh}"},
    )
    assert rejected_refresh.status_code == 401
    assert rejected_refresh.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"


def test_logout_ends_the_current_session_even_without_a_refresh_cookie(
    client: TestClient,
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-session-logout",
        "logout-session@example.test",
        "StrongPass!1234",
        ("admin",),
    )
    access_token, refresh_token = _login(client, seeded, "browser-logout-session")
    headers = {
        "X-Tenant-Id": str(seeded.tenant_id),
        "Authorization": f"Bearer {access_token}",
    }
    session_id = client.get("/api/v1/auth/sessions", headers=headers).json()[0]["id"]
    client.cookies.clear()
    logged_out = client.post("/api/v1/auth/logout", headers=headers)
    assert logged_out.status_code == 200
    assert logged_out.json() == {"success": True}

    rejected_access = client.get("/api/v1/auth/profile", headers=headers)
    assert rejected_access.status_code == 401
    assert rejected_access.json()["error"]["code"] == "TOKEN_REVOKED"
    set_db_tenant_context(db_session, seeded.tenant_id)
    session = db_session.get(AuthSession, session_id)
    assert session is not None
    assert session.revoked_at is not None
    assert session.revocation_reason == "logout"
    rejected_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{get_settings().refresh_cookie_name}={refresh_token}"},
    )
    assert rejected_refresh.status_code == 401
    assert rejected_refresh.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"


def test_logout_all_revokes_every_linked_session(
    client: TestClient,
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-session-logout-all",
        "logout-all@example.test",
        "StrongPass!1234",
        ("admin",),
    )
    first_token, _ = _login(client, seeded, "browser-logout-all-one")
    second_token, _ = _login(client, seeded, "browser-logout-all-two")
    headers = {
        "X-Tenant-Id": str(seeded.tenant_id),
        "Authorization": f"Bearer {second_token}",
    }
    session_ids = {row["id"] for row in client.get("/api/v1/auth/sessions", headers=headers).json()}
    result = client.post("/api/v1/auth/logout-all", headers=headers)
    assert result.status_code == 200
    assert result.json() == {"success": True}

    for token in (first_token, second_token):
        rejected = client.get(
            "/api/v1/auth/profile",
            headers={
                "X-Tenant-Id": str(seeded.tenant_id),
                "Authorization": f"Bearer {token}",
            },
        )
        assert rejected.status_code == 401
        assert rejected.json()["error"]["code"] == "TOKEN_REVOKED"

    set_db_tenant_context(db_session, seeded.tenant_id)
    rows = db_session.query(AuthSession).filter(AuthSession.id.in_(session_ids)).all()
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows)
    assert all(row.revocation_reason == "logout_all" for row in rows)


def test_retention_expires_dead_sessions_and_prunes_old_revoked_history(
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-session-retention",
        "session-retention@example.test",
        "StrongPass!1234",
        ("admin",),
    )
    now = datetime.now(UTC)
    old_time = now - timedelta(days=get_settings().auth_session_retention_days + 10)
    old_family = uuid4()
    old_session_id = uuid4()
    expired_family = uuid4()
    expired_session_id = uuid4()
    set_db_tenant_context(db_session, seeded.tenant_id)
    db_session.add_all(
        [
            AuthSession(
                id=old_session_id,
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                token_family_id=old_family,
                device_id="browser-old-session",
                label="Old browser",
                created_at=old_time,
                last_seen_at=old_time,
                revoked_at=old_time,
                revocation_reason="revoked_by_user",
            ),
            AuthSession(
                id=expired_session_id,
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                token_family_id=expired_family,
                device_id="browser-expired-session",
                label="Expired browser",
                created_at=now,
                last_seen_at=now,
            ),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            RefreshToken(
                id=uuid4(),
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                session_id=old_session_id,
                token_hash=f"old-session-token-{uuid4().hex}",
                token_family_id=old_family,
                expires_at=old_time,
                revoked_at=old_time,
                revocation_reason="revoked_by_user",
                created_at=old_time,
            ),
            RefreshToken(
                id=uuid4(),
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                session_id=expired_session_id,
                token_hash=f"expired-session-token-{uuid4().hex}",
                token_family_id=expired_family,
                expires_at=now - timedelta(days=1),
                created_at=now - timedelta(days=8),
            ),
        ]
    )
    db_session.commit()

    result = retention_cleanup()

    set_db_tenant_context(db_session, seeded.tenant_id)
    assert db_session.get(AuthSession, old_session_id) is None
    expired = db_session.get(AuthSession, expired_session_id)
    assert expired is not None
    assert expired.revoked_at is not None
    assert expired.revocation_reason == "expired"
    assert result["auth_sessions_deleted"] == 1
    assert result["auth_refresh_tokens_deleted"] == 1


def test_auth_sessions_have_forced_tenant_rls(db_session: Session) -> None:
    flags = db_session.execute(text("""
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE oid = 'auth_sessions'::regclass
            """)).one()
    policy_exists = db_session.execute(text("""
            SELECT 1 FROM pg_policies
            WHERE tablename = 'auth_sessions'
              AND policyname = 'tenant_isolation_auth_sessions'
            """)).first()
    assert flags == (True, True)
    assert policy_exists is not None


def test_migration_backfills_only_live_legacy_refresh_families(
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-session-backfill",
        "legacy-session@example.test",
        "StrongPass!1234",
        ("admin",),
    )
    family_id = uuid4()
    now = datetime.now(UTC)
    db_session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(seeded.tenant_id)},
    )
    db_session.add_all(
        [
            RefreshToken(
                id=uuid4(),
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                token_hash=f"legacy-active-{uuid4().hex}",
                token_family_id=family_id,
                expires_at=now + timedelta(days=1),
                session_id=None,
            ),
            RefreshToken(
                id=uuid4(),
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                token_hash=f"legacy-revoked-{uuid4().hex}",
                token_family_id=family_id,
                expires_at=now + timedelta(days=1),
                revoked_at=now,
                revocation_reason="rotated",
                session_id=None,
            ),
        ]
    )
    ambiguous_family_id = uuid4()
    second_user_id = uuid4()
    second_user = User(
        id=second_user_id,
        tenant_id=seeded.tenant_id,
        email="legacy-second-owner@example.test",
        collection_code=uuid4().hex[:8].upper(),
        password_hash="unused-test-hash",
        is_active=True,
    )
    db_session.add(second_user)
    db_session.flush()
    db_session.add_all(
        [
            RefreshToken(
                id=uuid4(),
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                token_hash=f"ambiguous-owner-one-{uuid4().hex}",
                token_family_id=ambiguous_family_id,
                expires_at=now + timedelta(days=1),
                session_id=None,
            ),
            RefreshToken(
                id=uuid4(),
                tenant_id=seeded.tenant_id,
                user_id=second_user_id,
                token_hash=f"ambiguous-owner-two-{uuid4().hex}",
                token_family_id=ambiguous_family_id,
                expires_at=now + timedelta(days=1),
                session_id=None,
            ),
        ]
    )
    db_session.flush()
    before_version = db_session.execute(
        select(User.access_token_version).where(
            User.tenant_id == seeded.tenant_id,
            User.id == seeded.user_id,
        )
    ).scalar_one()

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20261012_0013_linked_session_hardening.py"
    )
    spec = importlib.util.spec_from_file_location("linked_session_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    db_session.execute(text("SELECT set_config('app.tenant_id', 'bypass', true)"))
    db_session.execute(text(migration.BACKFILL_SQL))
    db_session.execute(text(migration.UNLINKED_REFRESH_REVOKE_SQL))

    linked = (
        db_session.query(RefreshToken)
        .filter_by(
            tenant_id=seeded.tenant_id,
            token_family_id=family_id,
            revocation_reason=None,
        )
        .one()
    )
    revoked = (
        db_session.query(RefreshToken)
        .filter(
            RefreshToken.tenant_id == seeded.tenant_id,
            RefreshToken.token_family_id == family_id,
            RefreshToken.revoked_at.is_not(None),
        )
        .one()
    )
    session = (
        db_session.query(AuthSession)
        .filter_by(
            tenant_id=seeded.tenant_id,
            token_family_id=family_id,
        )
        .one()
    )
    after_version = db_session.execute(
        select(User.access_token_version).where(
            User.tenant_id == seeded.tenant_id,
            User.id == seeded.user_id,
        )
    ).scalar_one()
    second_user_version = db_session.execute(
        select(User.access_token_version).where(
            User.tenant_id == seeded.tenant_id,
            User.id == second_user_id,
        )
    ).scalar_one()
    ambiguous_tokens = (
        db_session.query(RefreshToken)
        .filter_by(tenant_id=seeded.tenant_id, token_family_id=ambiguous_family_id)
        .all()
    )
    ambiguous_sessions = (
        db_session.query(AuthSession)
        .filter_by(tenant_id=seeded.tenant_id, token_family_id=ambiguous_family_id)
        .all()
    )
    assert linked.session_id == session.id
    assert revoked.session_id is None
    assert session.label == "Previously signed-in device"
    assert session.device_id.startswith("legacy-")
    assert after_version == before_version + 1
    assert second_user_version == 1
    assert len(ambiguous_tokens) == 2
    assert all(row.revocation_reason == "legacy_session_unlinked" for row in ambiguous_tokens)
    assert all(row.session_id is None for row in ambiguous_tokens)
    assert ambiguous_sessions == []
