from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.auth.roles import canonicalize_role_name
from app.auth.security import hash_password
from app.db.session import get_session_factory, set_db_tenant_context
from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from tests.conftest import SeededUser, _generate_test_collection_code


def _auth_headers(
    client: TestClient,
    seeded: SeededUser,
    *,
    roles: tuple[str, ...] | None = None,
) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles or ("admin",)),
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def _add_user_to_existing_tenant(
    *, tenant_id, email: str, password: str, role_name: str
) -> SeededUser:
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, tenant_id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            email=email,
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password(password),
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
        return SeededUser(
            tenant_id=tenant_id,
            user_id=user.id,
            collection_code=user.collection_code,
            email=email,
            password=password,
        )
    finally:
        session.rollback()
        session.close()


def test_provider_config_crud_masks_secrets(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-api",
        "admin-providers@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    create_response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "openai",
            "display_name": "Primary OpenAI",
            "api_base_url": "https://api.openai.com/v1",
            "auth_mode": "api_key",
            "enabled": True,
            "is_local": False,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": False,
            "default_chat_model": "gpt-4.1-mini",
            "default_embedding_model": "text-embedding-3-small",
            "timeout_seconds": 30,
            "priority": 10,
            "metadata_json": {"source": "test"},
            "api_key": "sk-test-secret-1234",
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    provider_id = payload["id"]
    assert payload["secrets"][0]["secret_type"] == "api_key"
    assert payload["secrets"][0]["masked_value"].startswith("sk-")
    assert "secret-1234" not in payload["secrets"][0]["masked_value"]

    get_response = client.get(f"/api/v1/providers/{provider_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["display_name"] == "Primary OpenAI"

    list_response = client.get("/api/v1/providers", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == provider_id for item in list_response.json()["items"])

    update_response = client.patch(
        f"/api/v1/providers/{provider_id}",
        headers=headers,
        json={"display_name": "Renamed OpenAI"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Renamed OpenAI"

    delete_response = client.delete(f"/api/v1/providers/{provider_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"


def test_delete_provider_clears_assignments_and_removes_provider(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-delete-active",
        "admin-provider-delete@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    create_response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "lmstudio",
            "display_name": "LM Studio",
            "api_base_url": "http://localhost:1234/v1",
            "auth_mode": "local_no_key",
            "enabled": True,
            "is_local": True,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": False,
            "default_chat_model": "local-chat",
            "default_embedding_model": "local-embed",
            "timeout_seconds": 30,
            "priority": 10,
            "metadata_json": {"source": "test"},
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]

    assignment_response = client.post(
        "/api/v1/providers/assignments",
        headers=headers,
        json={
            "feature_scope": "chat",
            "provider_config_id": provider_id,
            "model_name": "local-chat",
            "enabled": True,
            "priority": 100,
        },
    )
    assert assignment_response.status_code == 200

    delete_response = client.delete(f"/api/v1/providers/{provider_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"

    providers_response = client.get("/api/v1/providers", headers=headers)
    assert providers_response.status_code == 200
    assert not any(
        item["id"] == provider_id for item in providers_response.json()["items"]
    )

    assignments_response = client.get("/api/v1/providers/assignments", headers=headers)
    assert assignments_response.status_code == 200
    assert all(
        item["provider_config_id"] != provider_id
        for item in assignments_response.json()["items"]
    )


def test_provider_supported_types_catalog_is_exposed(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-catalog",
        "admin-catalog@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    response = client.get("/api/v1/providers/catalog/supported-types", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["provider_type"] == "openai" for item in items)
    assert any(item["provider_type"] == "ollama" for item in items)


def test_user_role_can_manage_provider_configs(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-user-access",
        "user-providers@tenant.example",
        "StrongPass!1234",
        ("user",),
    )
    headers = _auth_headers(client, seeded)

    create_response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "lmstudio",
            "display_name": "User LM Studio",
            "api_base_url": "http://localhost:1234/v1",
            "auth_mode": "local_no_key",
            "enabled": True,
            "is_local": True,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": False,
            "default_chat_model": "local-chat",
            "default_embedding_model": "local-embed",
            "timeout_seconds": 30,
            "priority": 10,
            "metadata_json": {"source": "user-test"},
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]

    list_response = client.get("/api/v1/providers", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == provider_id for item in list_response.json()["items"])

    update_response = client.patch(
        f"/api/v1/providers/{provider_id}",
        headers=headers,
        json={"display_name": "User LM Studio Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "User LM Studio Updated"

    delete_response = client.delete(f"/api/v1/providers/{provider_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"


def test_provider_configs_are_private_between_users_in_same_tenant(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    owner = seed_user(
        "tenant-provider-user-privacy",
        "owner-provider@tenant.example",
        "StrongPass!1234",
        ("user",),
    )
    other = _add_user_to_existing_tenant(
        tenant_id=owner.tenant_id,
        email="other-provider@tenant.example",
        password="StrongPass!1234",
        role_name="editor",
    )
    owner_headers = _auth_headers(client, owner, roles=("user",))
    other_headers = _auth_headers(client, other, roles=("editor",))

    create_response = client.post(
        "/api/v1/providers",
        headers=owner_headers,
        json={
            "provider_type": "lmstudio",
            "display_name": "Private LM Studio",
            "api_base_url": "http://localhost:1234/v1",
            "auth_mode": "local_no_key",
            "enabled": True,
            "is_local": True,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": False,
            "default_chat_model": "local-chat",
            "default_embedding_model": "local-embed",
            "timeout_seconds": 30,
            "priority": 10,
            "metadata_json": {},
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]
    assert create_response.json()["owner_user_id"] == str(owner.user_id)
    assert create_response.json()["visibility_scope"] == "user"

    other_list = client.get("/api/v1/providers", headers=other_headers)
    assert other_list.status_code == 200
    assert all(item["id"] != provider_id for item in other_list.json()["items"])

    other_get = client.get(f"/api/v1/providers/{provider_id}", headers=other_headers)
    assert other_get.status_code == 404

    other_update = client.patch(
        f"/api/v1/providers/{provider_id}",
        headers=other_headers,
        json={"display_name": "stolen"},
    )
    assert other_update.status_code == 404

    other_models = client.get(
        f"/api/v1/providers/{provider_id}/models", headers=other_headers
    )
    assert other_models.status_code == 404
