"""End-to-end sealed-chat tests: enable, send, read, rotate, shred.

Exercises the authenticated API against the migrated schema with the test
chat keyring from ``tests/conftest.py``.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.documents.models.collection import CollectionChatEpoch, CollectionChatMessage
from app.documents.services.collection_chat_crypto import generate_device_keypair
from app.platform.database.session import get_session_factory
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


def _make_collection(client: TestClient, headers: dict[str, str]) -> str:
    created = client.post(
        "/api/v1/collections",
        headers=headers,
        json={"name": "Sealed chat", "description": "signal-pattern-v1"},
    )
    assert created.status_code == 201
    return str(created.json()["id"])


def _stored_row(collection_id: str) -> CollectionChatMessage:
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        return (
            session.query(CollectionChatMessage)
            .filter(CollectionChatMessage.collection_id == collection_id)
            .order_by(CollectionChatMessage.created_at.desc())
            .first()
        )
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


def _epoch_count(collection_id: str) -> int:
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        return (
            session.query(CollectionChatEpoch)
            .filter(CollectionChatEpoch.collection_id == collection_id)
            .count()
        )
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


def test_sealed_chat_end_to_end(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "sealed-chat-e2e",
        "sealed-chat@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)
    headers = _headers(seeded, token)
    collection_id = _make_collection(client, headers)

    # Plaintext by default.
    plain = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "before sealing", "client_message_id": "plain-1"},
    )
    assert plain.status_code == 200
    assert plain.json()["is_encrypted"] is False

    # Enable sealed chat.
    enabled = client.post(
        f"/api/v1/collections/{collection_id}/chat-encryption/enable",
        headers=headers,
    )
    assert enabled.status_code == 200
    assert enabled.json()["chat_encryption_enabled"] is True
    assert enabled.json()["crypto_epoch"] == 1
    assert enabled.json()["protocol"] == "signal-pattern-v1"

    # Sealed send: API returns plaintext, storage holds ciphertext only.
    sent = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "top secret plans", "client_message_id": "sealed-1"},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["message"] == "top secret plans"
    assert body["is_encrypted"] is True
    assert body["crypto_epoch"] == 1

    row = _stored_row(collection_id)
    assert row is not None and row.is_encrypted is True
    assert "top secret plans" not in row.message
    assert '"ct"' in row.message

    # History read unseals for the member.
    history = client.get(f"/api/v1/collections/{collection_id}/chats", headers=headers)
    assert history.status_code == 200
    texts = {item["message"] for item in history.json()}
    assert {"before sealing", "top secret plans"} <= texts

    # Idempotent replay returns the same sealed message.
    replay = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "top secret plans", "client_message_id": "sealed-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == body["id"]

    conflicting = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "different words", "client_message_id": "sealed-1"},
    )
    assert conflicting.status_code == 409

    # Rotation keeps old history readable and moves new sends forward.
    rotated = client.post(
        f"/api/v1/collections/{collection_id}/chat-encryption/rotate",
        headers=headers,
    )
    assert rotated.status_code == 200
    assert rotated.json()["crypto_epoch"] == 2
    assert _epoch_count(collection_id) == 2

    second = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "post rotation", "client_message_id": "sealed-2"},
    )
    assert second.status_code == 200
    assert second.json()["crypto_epoch"] == 2

    history_after = client.get(f"/api/v1/collections/{collection_id}/chats", headers=headers)
    assert history_after.status_code == 200
    texts_after = {item["message"] for item in history_after.json()}
    assert {"before sealing", "top secret plans", "post rotation"} <= texts_after

    # Clear deletes messages and crypto-shreds the epochs.
    cleared = client.post(f"/api/v1/collections/{collection_id}/chats/clear", headers=headers)
    assert cleared.status_code == 200
    assert _epoch_count(collection_id) == 0
    empty = client.get(f"/api/v1/collections/{collection_id}/chats", headers=headers)
    assert empty.status_code == 200
    assert empty.json() == []


def test_sealed_chat_handles_max_length_plaintext(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    """A 4096-char message seals to ~5.6k chars; the body column must hold it."""
    seeded = seed_user(
        "sealed-chat-maxlen",
        "sealed-maxlen@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)
    headers = _headers(seeded, token)
    collection_id = _make_collection(client, headers)
    assert (
        client.post(
            f"/api/v1/collections/{collection_id}/chat-encryption/enable",
            headers=headers,
        ).status_code
        == 200
    )

    big = "m" * 4096
    sent = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": big, "client_message_id": "maxlen-1"},
    )
    assert sent.status_code == 200
    assert sent.json()["message"] == big
    assert sent.json()["is_encrypted"] is True

    history = client.get(f"/api/v1/collections/{collection_id}/chats", headers=headers)
    assert history.status_code == 200
    assert history.json()[0]["message"] == big


def test_sealed_chat_tamper_fails_closed(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "sealed-chat-tamper",
        "sealed-tamper@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)
    headers = _headers(seeded, token)
    collection_id = _make_collection(client, headers)
    assert (
        client.post(
            f"/api/v1/collections/{collection_id}/chat-encryption/enable",
            headers=headers,
        ).status_code
        == 200
    )
    sent = client.post(
        f"/api/v1/collections/{collection_id}/chats",
        headers=headers,
        json={"message": "untampered", "client_message_id": "tamper-1"},
    )
    assert sent.status_code == 200

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        row = (
            session.query(CollectionChatMessage)
            .filter(CollectionChatMessage.collection_id == collection_id)
            .one()
        )
        row.message = row.message[:-6] + ("A" if not row.message.endswith("A") else "B")
        session.commit()
    finally:
        session.execute(text("RESET ROLE"))
        session.close()

    history = client.get(f"/api/v1/collections/{collection_id}/chats", headers=headers)
    assert history.status_code == 500
    assert history.json()["error"]["code"] == "CHAT_DECRYPTION_FAILED"


def test_sealed_chat_device_key_registration(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "sealed-chat-device",
        "sealed-device@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)
    headers = _headers(seeded, token)
    collection_id = _make_collection(client, headers)
    keypair = generate_device_keypair()

    registered = client.post(
        f"/api/v1/collections/{collection_id}/chat-encryption/device-key",
        headers=headers,
        json={"device_id": "browser-1", "public_key": keypair.public_key_b64},
    )
    assert registered.status_code == 200
    assert registered.json()["protocol"] == "signal-pattern-v1"

    rejected = client.post(
        f"/api/v1/collections/{collection_id}/chat-encryption/device-key",
        headers=headers,
        json={"device_id": "browser-1", "public_key": "not-a-key"},
    )
    assert rejected.status_code == 422


def test_rotate_requires_enabled_collection(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "sealed-chat-rotate-guard",
        "sealed-guard@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)
    headers = _headers(seeded, token)
    collection_id = _make_collection(client, headers)

    rotated = client.post(
        f"/api/v1/collections/{collection_id}/chat-encryption/rotate",
        headers=headers,
    )
    assert rotated.status_code == 409
