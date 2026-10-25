from __future__ import annotations

from unittest.mock import Mock

from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.deepspace.api import chats as chats_api
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.platform.database.session import set_db_tenant_context
from tests.conftest import SeededUser


def _auth_headers(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"editor"},
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def _seed_turns(db_session, seeded: SeededUser, prompts: list[str]):
    set_db_tenant_context(db_session, seeded.tenant_id)
    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Prompt edit test",
        kind="deepspace",
    )
    pairs = []
    for prompt in prompts:
        user_message = repo.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            user_id=seeded.user_id,
            kind="deepspace",
            role="user",
            content=prompt,
        )
        assistant_message = repo.add_message(
            tenant_id=seeded.tenant_id,
            conversation_id=conversation.id,
            user_id=seeded.user_id,
            kind="deepspace",
            role="assistant",
            content=f"Answer to: {prompt}",
        )
        pairs.append((user_message, assistant_message))
    db_session.commit()
    return conversation, pairs


def _install_stream_stub(monkeypatch):
    stream_requests: list[dict[str, object]] = []

    async def stream_stub(*, raw_payload, **_kwargs):
        stream_requests.append(raw_payload)

        async def frames():
            yield 'event: done\ndata: {"status":"completed"}\n\n'

        return StreamingResponse(frames(), media_type="text/event-stream")

    dispatch = Mock()
    monkeypatch.setattr(chats_api, "_stream_deepspace_chat_payload", stream_stub)
    monkeypatch.setattr(chats_api, "_dispatch_deepspace_queue", dispatch)
    monkeypatch.setattr(
        chats_api.RateLimitService,
        "enforce_deepspace_user_limit",
        lambda *_args, **_kwargs: None,
    )
    return stream_requests, dispatch


def test_edit_and_regenerate_queues_repeated_edits_idempotently(
    client: TestClient, db_session, seed_user, monkeypatch
) -> None:
    seeded = seed_user("Prompt Edit", "prompt-edit@example.com", "password123", ("editor",))
    conversation, [(user_message, assistant_message)] = _seed_turns(
        db_session, seeded, ["Original prompt"]
    )
    stream_requests, dispatch = _install_stream_stub(monkeypatch)
    endpoint = (
        f"/api/v1/deepspace/chats/{conversation.id}/messages/{user_message.id}"
        "/edit-and-regenerate/stream"
    )
    headers = _auth_headers(seeded)

    first_payload = {
        "client_request_id": "edit-attempt-1",
        "content": "First revision",
        "thinking_enabled": False,
    }
    first_response = client.post(endpoint, headers=headers, json=first_payload)
    assert first_response.status_code == 200
    assert "event: done" in first_response.text

    replay_response = client.post(endpoint, headers=headers, json=first_payload)
    assert replay_response.status_code == 200

    conflicting_replay = client.post(
        endpoint,
        headers=headers,
        json={
            **first_payload,
            "content": "Different text under the same request id",
        },
    )
    assert conflicting_replay.status_code == 409

    db_session.expire_all()
    repo = DeepSpaceChatRepository(db_session)
    edited_user = repo.get_message_by_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        message_id=user_message.id,
        kind="deepspace",
    )
    queued = db_session.execute(
        select(DeepSpaceQueuedTurn).where(
            DeepSpaceQueuedTurn.conversation_id == conversation.id,
            DeepSpaceQueuedTurn.client_request_id == "edit-attempt-1",
        )
    ).scalar_one()
    assert edited_user is not None
    assert edited_user.content == "First revision"
    assert len(edited_user.versions) == 2
    assert queued.prompt == "First revision"
    assert queued.regenerate_message_id == assistant_message.id
    assert [item["client_request_id"] for item in stream_requests] == [
        "edit-attempt-1",
        "edit-attempt-1",
    ]
    assert all(item["reconnect"] is True for item in stream_requests)
    assert dispatch.call_count == 2

    overlapping_edit = client.post(
        endpoint,
        headers=headers,
        json={
            "client_request_id": "edit-attempt-2",
            "content": "Second revision",
            "thinking_enabled": False,
        },
    )
    assert overlapping_edit.status_code == 409

    db_session.execute(
        update(DeepSpaceQueuedTurn)
        .where(DeepSpaceQueuedTurn.id == queued.id)
        .values(status="completed")
    )
    db_session.commit()

    second_response = client.post(
        endpoint,
        headers=headers,
        json={
            "client_request_id": "edit-attempt-2",
            "content": "Second revision",
            "thinking_enabled": False,
        },
    )
    assert second_response.status_code == 200

    db_session.expire_all()
    edited_user = repo.get_message_by_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        message_id=user_message.id,
        kind="deepspace",
    )
    edited_assistant = repo.get_message_by_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        kind="deepspace",
    )
    second_queued = db_session.execute(
        select(DeepSpaceQueuedTurn).where(
            DeepSpaceQueuedTurn.conversation_id == conversation.id,
            DeepSpaceQueuedTurn.client_request_id == "edit-attempt-2",
        )
    ).scalar_one()
    assert edited_user is not None
    assert edited_user.content == "Second revision"
    assert len(edited_user.versions) == 3
    assert edited_assistant is not None
    assert len(edited_assistant.versions) == 1
    assert second_queued.prompt == "Second revision"
    assert second_queued.regenerate_message_id == assistant_message.id


def test_edit_and_regenerate_rejects_older_prompt_without_mutating_it(
    client: TestClient, db_session, seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "Older Prompt Edit", "older-prompt-edit@example.com", "password123", ("editor",)
    )
    conversation, [(older_user, _), _latest_pair] = _seed_turns(
        db_session, seeded, ["Older prompt", "Latest prompt"]
    )
    stream_requests, _ = _install_stream_stub(monkeypatch)
    endpoint = (
        f"/api/v1/deepspace/chats/{conversation.id}/messages/{older_user.id}"
        "/edit-and-regenerate/stream"
    )

    response = client.post(
        endpoint,
        headers=_auth_headers(seeded),
        json={"client_request_id": "stale-edit", "content": "Should not be saved"},
    )

    assert response.status_code == 409
    assert stream_requests == []
    db_session.expire_all()
    edited_user = DeepSpaceChatRepository(db_session).get_message_by_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        message_id=older_user.id,
        kind="deepspace",
    )
    assert edited_user is not None
    assert edited_user.content == "Older prompt"
    assert len(edited_user.versions) == 1
