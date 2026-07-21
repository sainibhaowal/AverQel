from __future__ import annotations

from collections.abc import Callable

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.query.repositories.chat import ChatRepository
from app.deepspace.orchestration.deepspace_service import DeepSpaceService
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


def test_manual_compaction_persists_snapshot_and_updates_session_context(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "DeepSpace Compaction Tenant",
        "deepspace-compaction@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))
    repo = ChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Long Mission",
        kind="deepspace",
    )
    for index in range(7):
        repo.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            kind="deepspace",
            role="user",
            content=f"User request {index}: " + ("please keep this context " * 20),
        )
        repo.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            kind="deepspace",
            role="assistant",
            content=f"Assistant answer {index}: " + ("detailed working memory " * 24),
        )
    db_session.commit()

    compact_response = client.post(
        f"/api/v1/deepspace/chats/session/{conversation.id}/compact",
        headers=headers,
    )
    assert compact_response.status_code == 200
    compact_payload = compact_response.json()
    assert compact_payload["status"] == "compacted"
    compaction = compact_payload["compaction"]
    assert compaction["saved_tokens"] > 0
    assert compaction["summarized_count"] > 0

    context_response = client.get(
        f"/api/v1/deepspace/chats/session/{conversation.id}/context",
        headers=headers,
    )
    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["token_count"] == compaction["after_tokens"]
    assert context_payload["compaction"]["saved_tokens"] == compaction["saved_tokens"]

    refreshed_messages = list(
        repo.get_messages(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            user_id=seeded.user_id,
            kind="deepspace",
            limit=100,
        )
    )
    last_assistant = next(
        message
        for message in reversed(refreshed_messages)
        if message.role == "assistant"
    )
    assert last_assistant.metadata_json["conversation_compaction"]["saved_tokens"] > 0


def test_previous_messages_respect_compaction_snapshot(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "DeepSpace Snapshot Tenant",
        "deepspace-snapshot@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))
    repo = ChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Snapshot Mission",
        kind="deepspace",
    )
    for index in range(6):
        repo.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            kind="deepspace",
            role="user",
            content=f"Question {index}: " + ("background detail " * 18),
        )
        repo.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            kind="deepspace",
            role="assistant",
            content=f"Answer {index}: " + ("analysis and summary " * 20),
        )
    db_session.commit()

    compact_response = client.post(
        f"/api/v1/deepspace/chats/session/{conversation.id}/compact",
        headers=headers,
    )
    assert compact_response.status_code == 200

    service = DeepSpaceService(db=db_session, settings=get_settings())
    previous = service._build_previous_messages(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation.id,
    )

    assert previous
    assert any(
        message["role"] == "system"
        and "Compacted conversation history" in message["content"]
        for message in previous
    )
