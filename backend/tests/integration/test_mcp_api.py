from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.core.auth import create_access_token
from app.core.config import get_settings
from tests.conftest import SeededUser


def _auth_headers(seeded: SeededUser, *, roles: tuple[str, ...] = ("admin",)) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles),
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_marketplace_rejects_blank_verified_filter(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-mcp-marketplace",
        "mcp-marketplace@example.com",
        "StrongPass!1234",
        ("admin",),
    )

    response = client.get(
        "/api/v1/mcp/marketplace?verified=&page=1",
        headers=_auth_headers(seeded),
    )

    assert response.status_code == 422


def test_marketplace_accepts_omitted_verified_filter(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-mcp-marketplace-omitted",
        "mcp-marketplace-omitted@example.com",
        "StrongPass!1234",
        ("admin",),
    )

    response = client.get(
        "/api/v1/mcp/marketplace?page=1",
        headers=_auth_headers(seeded),
    )

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload


def test_legacy_catalog_import_route_is_removed(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-mcp-marketplace-user",
        "mcp-marketplace-user@example.com",
        "StrongPass!1234",
        ("user",),
    )

    response = client.post(
        "/api/v1/mcp/catalog/import",
        json={"manifest_url": "https://vendor.example.com/mcp.json"},
        headers=_auth_headers(seeded, roles=("user",)),
    )

    assert response.status_code == 404
