from __future__ import annotations

from collections.abc import Callable

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


def test_voice_settings_require_authentication_and_query_permission(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    unauthenticated = client.get("/api/v1/deepspace/voice/settings")
    assert unauthenticated.status_code == 401

    seeded = seed_user(
        "voice-settings-denied",
        "voice-settings-denied@example.test",
        "StrongPass!1234",
        ("support_manager",),
    )
    denied = client.get(
        "/api/v1/deepspace/voice/settings",
        headers=_auth_headers(seeded, roles={"support_manager"}),
    )
    assert denied.status_code == 403


def test_voice_settings_are_persisted_per_authenticated_user_and_tenant(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "voice-settings",
        "voice-settings@example.test",
        "StrongPass!1234",
        ("user",),
    )
    headers = _auth_headers(seeded)

    initial = client.get("/api/v1/deepspace/voice/settings", headers=headers)
    assert initial.status_code == 200
    assert initial.json() == {
        "voice": "alba",
        "speed": 1.0,
        "pitch": 1.0,
        "volume": 1.0,
        "clonedVoiceId": None,
        "clonedVoiceName": None,
    }

    updated = client.put(
        "/api/v1/deepspace/voice/settings",
        headers=headers,
        json={"voice": "cosette", "speed": 1.4, "pitch": 1.0, "volume": 0.75},
    )
    assert updated.status_code == 200
    assert updated.json()["voice"] == "cosette"
    assert updated.json()["speed"] == 1.4

    persisted = client.get("/api/v1/deepspace/voice/settings", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json() == updated.json()


def test_voice_settings_reject_invalid_voice_and_out_of_range_speed(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "voice-settings-validation",
        "voice-settings-validation@example.test",
        "StrongPass!1234",
        ("user",),
    )

    invalid_voice = client.put(
        "/api/v1/deepspace/voice/settings",
        headers=_auth_headers(seeded),
        json={"voice": "../../other-tenant/voice", "speed": 1.0},
    )
    assert invalid_voice.status_code == 422

    invalid_speed = client.put(
        "/api/v1/deepspace/voice/settings",
        headers=_auth_headers(seeded),
        json={"voice": "alba", "speed": 3.0},
    )
    assert invalid_speed.status_code == 422
