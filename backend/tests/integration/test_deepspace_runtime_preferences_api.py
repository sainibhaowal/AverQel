from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from tests.conftest import SeededUser


def _auth_headers(seeded: SeededUser, *, roles: tuple[str, ...]) -> dict[str, str]:
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


def test_runtime_preferences_api_round_trips_conversation_scope(
    client,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "DeepSpace Runtime Tenant",
        "runtime@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))
    conversation_id = str(uuid4())

    get_response = client.get(
        f"/api/v1/deepspace/chats/runtime-preferences?conversation_id={conversation_id}",
        headers=headers,
    )

    assert get_response.status_code == 200
    assert get_response.json() == {
        "conversation_id": conversation_id,
        "execution_mode": "auto_review",
        "planner_mode": "default",
        "subagent_profile": "default",
        "runtime_hooks_enabled": True,
        "workspace_mode_enabled": True,
    }

    patch_response = client.patch(
        "/api/v1/deepspace/chats/runtime-preferences",
        headers=headers,
        json={
            "conversation_id": conversation_id,
            "execution_mode": "full_access",
            "planner_mode": "structured",
            "subagent_profile": "analysis",
            "runtime_hooks_enabled": False,
            "workspace_mode_enabled": False,
        },
    )

    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "conversation_id": conversation_id,
        "execution_mode": "full_access",
        "planner_mode": "structured",
        "subagent_profile": "analysis",
        "runtime_hooks_enabled": False,
        "workspace_mode_enabled": False,
    }

    confirm_response = client.get(
        f"/api/v1/deepspace/chats/runtime-preferences?conversation_id={conversation_id}",
        headers=headers,
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["planner_mode"] == "structured"
    assert confirm_response.json()["subagent_profile"] == "analysis"


def test_runtime_preferences_api_is_isolated_per_user(
    client,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded_a = seed_user(
        "DeepSpace Runtime Tenant A",
        "runtime-a@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    seeded_b = seed_user(
        "DeepSpace Runtime Tenant B",
        "runtime-b@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers_a = _auth_headers(seeded_a, roles=("admin",))
    headers_b = _auth_headers(seeded_b, roles=("admin",))

    patch_response = client.patch(
        "/api/v1/deepspace/chats/runtime-preferences",
        headers=headers_a,
        json={
            "planner_mode": "structured",
            "subagent_profile": "research",
            "runtime_hooks_enabled": False,
        },
    )
    assert patch_response.status_code == 200

    response_a = client.get(
        "/api/v1/deepspace/chats/runtime-preferences",
        headers=headers_a,
    )
    response_b = client.get(
        "/api/v1/deepspace/chats/runtime-preferences",
        headers=headers_b,
    )

    assert response_a.status_code == 200
    assert response_a.json()["planner_mode"] == "structured"
    assert response_a.json()["subagent_profile"] == "research"
    assert response_a.json()["runtime_hooks_enabled"] is False

    assert response_b.status_code == 200
    assert response_b.json()["planner_mode"] == "default"
    assert response_b.json()["subagent_profile"] == "default"
    assert response_b.json()["runtime_hooks_enabled"] is True
