from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.query.repositories.chat import ChatRepository


def _headers(seeded, *, roles: tuple[str, ...]) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles),
        settings=get_settings(),
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}


def test_query_history_pages_are_chronological_and_cursor_scoped(
    client: TestClient, db_session, seed_user
) -> None:
    seeded = seed_user(
        "Query History Page", "query-history-page@example.com", "password123", ("user",)
    )
    repository = ChatRepository(db_session)
    conversation = repository.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Paged Query",
    )
    created = [
        repository.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            role="user" if index % 2 == 0 else "assistant",
            content=f"Message {index}",
        )
        for index in range(5)
    ]
    db_session.commit()

    headers = _headers(seeded, roles=("user",))
    first = client.get(
        f"/api/v1/chats/{conversation.id}/messages?limit=2",
        headers=headers,
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert [item["id"] for item in first_payload["messages"]] == [
        str(created[3].id),
        str(created[4].id),
    ]
    assert first_payload["has_more"] is True

    older = client.get(
        f"/api/v1/chats/{conversation.id}/messages?limit=2&before_message_id={created[3].id}",
        headers=headers,
    )
    assert older.status_code == 200
    assert [item["id"] for item in older.json()["messages"]] == [
        str(created[1].id),
        str(created[2].id),
    ]
    assert older.json()["has_more"] is True

    invalid_cursor = client.get(
        f"/api/v1/chats/{conversation.id}/messages?before_message_id={seeded.user_id}",
        headers=headers,
    )
    assert invalid_cursor.status_code == 404


def test_query_proxy_history_returns_the_latest_page(
    client: TestClient, db_session, seed_user, monkeypatch
) -> None:
    from app.deepspace.integrations import client_proxy
    from app.query.api.chats import _serialize_message

    seeded = seed_user(
        "Query Proxy History Page",
        "query-proxy-history-page@example.com",
        "password123",
        ("user",),
    )
    repository = ChatRepository(db_session)
    conversation = repository.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Paged Query Proxy",
    )
    created = [
        repository.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            role="user" if index % 2 == 0 else "assistant",
            content=f"Message {index}",
        )
        for index in range(3)
    ]
    db_session.commit()

    async def storage_call(*_args, **_kwargs):
        return [_serialize_message(message).model_dump(mode="json") for message in created]

    monkeypatch.setattr(client_proxy.client_proxy_registry, "is_storage_connected", lambda *_: True)
    monkeypatch.setattr(client_proxy.client_proxy_registry, "db_proxy_call", storage_call)

    response = client.get(
        f"/api/v1/chats/{conversation.id}/messages?limit=2",
        headers=_headers(seeded, roles=("user",)),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["messages"]] == [
        str(created[1].id),
        str(created[2].id),
    ]
    assert response.json()["has_more"] is True


def test_deepspace_history_pages_keep_older_messages_reachable(
    client: TestClient, db_session, seed_user
) -> None:
    seeded = seed_user(
        "DeepSpace History Page",
        "deepspace-history-page@example.com",
        "password123",
        ("user",),
    )
    repository = DeepSpaceChatRepository(db_session)
    conversation = repository.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Paged DeepSpace",
    )
    created = [
        repository.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            role="user" if index % 2 == 0 else "assistant",
            content=f"Message {index}",
        )
        for index in range(5)
    ]
    db_session.commit()

    headers = _headers(seeded, roles=("user",))
    first = client.get(
        f"/api/v1/deepspace/chats/{conversation.id}/messages?limit=2",
        headers=headers,
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert [item["id"] for item in first_payload["messages"]] == [
        str(created[3].id),
        str(created[4].id),
    ]
    assert first_payload["has_more"] is True

    older = client.get(
        f"/api/v1/deepspace/chats/{conversation.id}/messages?limit=2&before_message_id={created[3].id}",
        headers=headers,
    )
    assert older.status_code == 200
    assert [item["id"] for item in older.json()["messages"]] == [
        str(created[1].id),
        str(created[2].id),
    ]
    assert older.json()["has_more"] is True

    other_headers = _headers(seeded, roles=("user",))
    invalid_cursor = client.get(
        f"/api/v1/deepspace/chats/{conversation.id}/messages?before_message_id={seeded.user_id}",
        headers=other_headers,
    )
    assert invalid_cursor.status_code == 404
