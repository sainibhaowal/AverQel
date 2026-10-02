import asyncio
from collections.abc import Callable

from fastapi.testclient import TestClient

from app.documents.api import collections as collections_api
from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _headers(seeded: SeededUser, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_chat_post_is_idempotent_and_rejects_foreign_media_reference(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "collection-chat-hardening",
        "chat-hardening@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)
    headers = _headers(seeded, token)

    created = client.post(
        "/api/v1/collections",
        headers=headers,
        json={"name": "Chat hardening", "description": "security"},
    )
    assert created.status_code == 201
    collection_id = created.json()["id"]

    first = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "encrypted", "client_message_id": "client-1"},
    )
    assert first.status_code == 200

    duplicate = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "encrypted", "client_message_id": "client-1"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]

    conflicting_retry = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "different payload", "client_message_id": "client-1"},
    )
    assert conflicting_retry.status_code == 409
    assert conflicting_retry.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    foreign_media = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={
            "message": "encrypted media",
            "is_media": True,
            "media_id": "00000000-0000-0000-0000-000000000001",
            "media_object_key": "00000000-0000-0000-0000-000000000002/"
            "00000000-0000-0000-0000-000000000001/file.bin",
        },
    )
    assert foreign_media.status_code == 403


def test_query_filter_contract_accepts_collection_scope() -> None:
    from app.query.schemas.queries import QueryRequest

    request = QueryRequest.model_validate(
        {
            "query": "summarize the shared documents",
            "top_k": 5,
            "filters": {"collection_id": "00000000-0000-0000-0000-000000000001"},
        }
    )

    assert str(request.filters.collection_id) == "00000000-0000-0000-0000-000000000001"


def test_device_revocation_and_self_block_are_tenant_scoped(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "collection-security-controls",
        "security-controls@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)
    headers = _headers(seeded, token)

    device = client.post(
        "/api/v1/collections/security/devices",
        headers=headers,
        json={"device_id": "browser-test-1", "label": "Test browser"},
    )
    assert device.status_code == 200
    assert device.json()["protocol_version"] == "legacy-shared-key"

    listed = client.get("/api/v1/collections/security/devices", headers=headers)
    assert listed.status_code == 200
    assert any(row["device_id"] == "browser-test-1" for row in listed.json())

    revoked = client.delete(
        "/api/v1/collections/security/devices/browser-test-1",
        headers=headers,
    )
    assert revoked.status_code == 204

    collection = client.post(
        "/api/v1/collections",
        headers=headers,
        json={"name": "Moderation", "description": "security"},
    ).json()["id"]
    blocked_self = client.post(
        f"/api/v1/collections/{collection}/security/blocks",
        headers=headers,
        json={"user_id": str(seeded.user_id)},
    )
    assert blocked_self.status_code == 422


def test_websocket_message_mutation_cannot_cross_collection(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "collection-ws-isolation",
        "ws-isolation@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)
    headers = _headers(seeded, token)

    async def no_subscriber(_collection_id: str) -> None:
        await asyncio.sleep(0)

    async def no_publish(_collection_id: str, _event_type: str, _data: dict) -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(collections_api.broadcast_manager, "_redis_subscribe_loop", no_subscriber)
    monkeypatch.setattr(collections_api.broadcast_manager, "publish_event", no_publish)

    collection_a = client.post(
        "/api/v1/collections",
        headers=headers,
        json={"name": "Collection A", "description": "A"},
    ).json()["id"]
    collection_b = client.post(
        "/api/v1/collections",
        headers=headers,
        json={"name": "Collection B", "description": "B"},
    ).json()["id"]
    message_b = client.post(
        f"/api/v1/collections/{collection_b}/chats",
        headers=headers,
        json={"message": "message in B"},
    )
    assert message_b.status_code == 200
    message_b_id = message_b.json()["id"]

    with client.websocket_connect(
        f"/api/v1/collections/{collection_a}/ws" f"?token={token}&tenant_id={seeded.tenant_id}"
    ) as websocket:
        websocket.send_json({"action": "react", "message_id": message_b_id, "reaction": "❤️"})

    messages_b = client.get(f"/api/v1/collections/{collection_b}/chats", headers=headers)
    assert messages_b.status_code == 200
    assert messages_b.json()[0]["reactions"] == "{}"
