from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from tests.conftest import SeededUser


def _auth_headers(seeded: SeededUser, *, roles: set[str] | None = None) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=roles or {"user"},
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_voice_token_is_bound_to_the_authenticated_user_and_requested_room(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user("voice-token", "voice-token@example.test", "StrongPass!1234", ("user",))
    room = "deepspace-room-isolated-test"
    identity = f"user-{seeded.user_id}"

    response = client.get(
        "/api/v1/voice/token",
        params={"room": room, "identity": identity},
        headers=_auth_headers(seeded),
    )

    assert response.status_code == 200
    token = response.json()["token"]
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["sub"] == identity
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["room"] == room


def test_voice_token_rejects_missing_permission_and_identity_mismatch(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "voice-token-denied", "voice-denied@example.test", "StrongPass!1234", ("user",)
    )
    own_identity = f"user-{seeded.user_id}"

    unauthenticated = client.get(
        "/api/v1/voice/token",
        params={"room": "isolated-room", "identity": own_identity},
    )
    assert unauthenticated.status_code == 401

    without_query_permission = client.get(
        "/api/v1/voice/token",
        params={"room": "isolated-room", "identity": own_identity},
        headers=_auth_headers(seeded, roles={"support_manager"}),
    )
    assert without_query_permission.status_code == 403

    identity_mismatch = client.get(
        "/api/v1/voice/token",
        params={"room": "isolated-room", "identity": "user-someone-else"},
        headers=_auth_headers(seeded),
    )
    assert identity_mismatch.status_code == 403
    assert identity_mismatch.json()["error"]["code"] == "FORBIDDEN"
