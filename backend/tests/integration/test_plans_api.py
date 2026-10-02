from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models.user import User
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.system.models.tenant_storage_allocation import TenantStorageAllocation
from app.system.services.storage_quota import StorageQuotaExceededError
from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_plan_endpoint_exposes_free_and_editor_without_admin_card(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user("plan-user-tenant", "plan-user@example.com", "StrongPass!1234", ("user",))
    token = _login(client, seeded)

    response = client.get(
        "/api/v1/plans/current",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_plan"]["id"] == "free"
    assert body["current_plan"]["storage_limit_bytes"] == 500 * 1024 * 1024
    assert {plan["id"] for plan in body["plans"]} == {"free", "editor"}
    assert body["usage"]["total_bytes"] == 0


def test_plan_endpoint_exposes_admin_card_only_to_admin(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user("plan-admin-tenant", "plan-admin@example.com", "StrongPass!1234", ("admin",))
    token = _login(client, seeded)

    response = client.get(
        "/api/v1/plans/current",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_plan"]["id"] == "admin"
    assert body["current_plan"]["admin_account"] is True
    assert {plan["id"] for plan in body["plans"]} == {"free", "editor", "admin"}


def test_storage_endpoint_returns_tenant_scoped_inventory(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user("storage-tenant", "storage@example.com", "StrongPass!1234", ("user",))
    token = _login(client, seeded)

    response = client.get(
        "/api/v1/storage/current",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_plan"]["id"] == "free"
    assert body["usage"]["total_bytes"] == 0
    assert {metric["key"] for metric in body["metrics"]} >= {
        "documents",
        "library",
        "chat_history",
        "memory",
        "activity_and_runs",
    }
    assert all("content" not in metric for metric in body["metrics"])


def test_storage_retention_policy_is_tenant_scoped_and_safe_by_default(
    client: TestClient,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "retention-policy-tenant", "retention-policy@example.com", "StrongPass!1234", ("user",)
    )
    token = _login(client, seeded)
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}

    default_response = client.get("/api/v1/storage/retention", headers=headers)
    assert default_response.status_code == 200
    assert default_response.json() == {
        "mode": "off",
        "days": 0,
        "policy_version": 1,
        "automatic_purge_enabled": False,
    }

    update_response = client.put(
        "/api/v1/storage/retention",
        headers=headers,
        json={"mode": "30"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["mode"] == "30"
    assert update_response.json()["days"] == 30
    assert update_response.json()["automatic_purge_enabled"] is False

    allocation = db_session.execute(
        select(TenantStorageAllocation).where(TenantStorageAllocation.tenant_id == seeded.tenant_id)
    ).scalar_one()
    assert allocation.retention_mode == "30"
    assert allocation.retention_days == 30

    preview_response = client.get("/api/v1/storage/retention/preview", headers=headers)
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["policy"]["mode"] == "30"
    assert preview["legacy_data_preserved"] is True
    assert preview["candidate_count"] == 0


def test_new_registration_receives_real_free_storage_allocation(
    client: TestClient,
    db_session,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "allocated@example.com", "password": "StrongPass!1234"},
    )

    assert response.status_code == 200
    assert response.json()["user_id"]
    user_id = response.json()["user_id"]
    tenant_id = db_session.execute(select(User.tenant_id).where(User.id == user_id)).scalar_one()
    allocation = db_session.execute(
        select(TenantStorageAllocation).where(TenantStorageAllocation.tenant_id == tenant_id)
    ).scalar_one()
    assert user_id
    assert allocation.plan_id == "free"
    assert allocation.allocated_bytes == 500 * 1024 * 1024


def test_chat_history_is_metered_and_rejected_at_the_tenant_limit(
    client: TestClient,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user("chat-meter-tenant", "chat-meter@example.com", "StrongPass!1234", ("user",))
    token = _login(client, seeded)
    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Metered conversation",
    )
    db_session.commit()

    storage_response = client.get(
        "/api/v1/storage/current",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert storage_response.status_code == 200
    chat_metric = next(
        metric for metric in storage_response.json()["metrics"] if metric["key"] == "chat_history"
    )
    assert chat_metric["included_in_quota"] is True
    assert chat_metric["bytes"] > 0

    allocation = db_session.execute(
        select(TenantStorageAllocation).where(TenantStorageAllocation.tenant_id == seeded.tenant_id)
    ).scalar_one()
    allocation.allocated_bytes = 1
    db_session.commit()

    with pytest.raises(StorageQuotaExceededError):
        repo.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            role="user",
            content="This message must be rejected before it is persisted.",
            user_id=seeded.user_id,
        )
