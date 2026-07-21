from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.system.services.rate_limit_service import RateLimitService
from tests.conftest import SeededUser


def test_auth_login_rate_limit_exceeded_returns_429(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    seeded = seed_user(
        "tenant-auth-rate-limit",
        "reader-auth-rate-limit@tenant.example",
        "StrongPass!1234",
        ("reader",),
    )

    def fake_increment(
        self: RateLimitService, *, key: str, window_seconds: int
    ) -> tuple[int, int]:
        del self, window_seconds
        if "auth_login" in key:
            return 999, 300
        return 1, 300

    monkeypatch.setattr(RateLimitService, "_increment_counter", fake_increment)

    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_public_auth_routes_allow_missing_tenant_id_without_crashing(
    client: TestClient,
    monkeypatch: MonkeyPatch,
) -> None:
    seen_keys: list[str] = []

    def fake_increment(
        self: RateLimitService, *, key: str, window_seconds: int
    ) -> tuple[int, int]:
        del self, window_seconds
        seen_keys.append(key)
        return 1, 300

    monkeypatch.setattr(RateLimitService, "_increment_counter", fake_increment)

    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "public-auth@example.com", "password": "StrongPass!1234"},
    )
    assert register_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "public-auth@example.com", "password": "StrongPass!1234"},
    )
    assert login_response.status_code == 200

    assert any(
        "rate_limit:auth_login:unknown:public-auth@example.com" == key
        for key in seen_keys
    )
