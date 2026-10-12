from __future__ import annotations

import asyncio
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from app.deepspace.models.agent_runtime import DeepSpaceAgentRun
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.queue_control import DeepSpaceQueueControl
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.deepspace.schemas.chats import QueueTurnRequest, RegenerateRequest
from app.deepspace.services import turn_queue as turn_queue_module
from app.deepspace.services.turn_queue import (
    DeepSpaceTurnQueueStore,
    QueueTurnEditConflictError,
    QueueTurnNotEditableError,
)
from app.system.services.storage_quota import StorageQuotaService


def test_regenerate_api_queues_saved_turn_for_durable_replay(
    db_session, seed_user, monkeypatch
) -> None:
    from app.deepspace.api import chats as chat_api

    _silence_queue_side_effects(monkeypatch)
    monkeypatch.setattr(chat_api, "_dispatch_deepspace_queue", lambda **_kwargs: None)
    seeded = seed_user(
        "RegenerateApiTenant",
        "regenerate-api@example.com",
        "StrongPass!1234",
        ("user",),
    )
    conversation_id = _conversation(db_session, seeded)
    attachment_id = uuid.uuid4()
    repo = DeepSpaceChatRepository(db_session)
    source_user = repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation_id,
        role="user",
        content="Saved prompt from the original turn",
        metadata_json={"attachments": [{"id": str(attachment_id), "name": "source.pdf"}]},
    )
    assistant = repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation_id,
        role="assistant",
        content="Previous answer",
        metadata_json={"status": "ready"},
    )
    db_session.commit()

    @contextmanager
    def session_scope():
        yield db_session

    monkeypatch.setattr(chat_api, "managed_db_session", session_scope)
    monkeypatch.setattr(chat_api, "set_db_tenant_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        chat_api.RateLimitService, "enforce_deepspace_user_limit", lambda *_args, **_kwargs: None
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/api/v1/deepspace/chats/{conversation_id}/messages/{assistant.id}/regenerate/stream",
            "headers": [],
            "query_string": b"",
        },
        receive=lambda: None,
    )
    auth = SimpleNamespace(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        roles=frozenset({"user"}),
        permissions=frozenset({"queries:run"}),
    )
    settings = SimpleNamespace()

    response = asyncio.run(
        chat_api.regenerate_message_stream(
            conversation_id=conversation_id,
            message_id=assistant.id,
            payload=RegenerateRequest(client_request_id="regen-api-request"),
            request=request,
            auth=auth,
            settings=settings,
        )
    )
    queued_response = chat_api.enqueue_deepspace_turn(
        conversation_id=conversation_id,
        payload=QueueTurnRequest(
            message="",
            client_request_id="regen-queued-api-request",
            regenerate_message_id=assistant.id,
        ),
        request=request,
        auth=auth,
        db=db_session,
        settings=settings,
    )
    queued = DeepSpaceTurnQueueStore(db_session).list_open(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )

    assert response.media_type == "text/event-stream"
    assert queued_response.regenerate_message_id == assistant.id
    assert len(queued) == 2
    assert {turn.client_request_id for turn in queued} == {
        "regen-api-request",
        "regen-queued-api-request",
    }
    for turn in queued:
        assert turn.regenerate_message_id == assistant.id
        assert turn.prompt == source_user.content
        assert turn.attachment_file_ids_json == [str(attachment_id)]
    assert assistant.content == "Previous answer"
    assert assistant.metadata_json["status"] == "ready"


def _conversation(db_session, seeded, *, title: str = "Queue recovery") -> uuid.UUID:
    conversation = DeepSpaceChatRepository(db_session).create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title=title,
        kind="deepspace",
    )
    return conversation.id


def _turn(
    db_session,
    seeded,
    conversation_id: uuid.UUID,
    *,
    request_id: str,
    prompt: str,
    sequence: int,
    status: str,
    priority: int = 0,
    resume_from_request_id: str | None = None,
    regenerate_message_id: uuid.UUID | None = None,
    attachment_file_ids: list[str] | None = None,
) -> DeepSpaceQueuedTurn:
    turn = DeepSpaceQueuedTurn(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        client_request_id=request_id,
        regenerate_message_id=regenerate_message_id,
        resume_from_request_id=resume_from_request_id,
        prompt=prompt,
        sequence=sequence,
        priority=priority,
        thinking_enabled=False,
        roles_json=["user"],
        permissions_json=["queries:run"],
        attachment_file_ids_json=list(attachment_file_ids or []),
        status=status,
    )
    db_session.add(turn)
    db_session.commit()
    db_session.refresh(turn)
    return turn


def _silence_queue_side_effects(monkeypatch) -> None:
    monkeypatch.setattr(DeepSpaceTurnQueueStore, "_publish_queue_event", lambda *a, **k: None)
    monkeypatch.setattr(DeepSpaceTurnQueueStore, "_record_activity", lambda *a, **k: None)
    monkeypatch.setattr(StorageQuotaService, "ensure_capacity", lambda *a, **k: None)


def test_failed_turn_does_not_pause_queue_and_next_priority_turn_runs(
    db_session, seed_user, monkeypatch
) -> None:
    _silence_queue_side_effects(monkeypatch)
    seeded = seed_user(
        "QueueAdvanceTenant", "queue-advance@example.com", "StrongPass!1234", ("user",)
    )
    conversation_id = _conversation(db_session, seeded)
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="failed-first",
        prompt="Initial prompt",
        sequence=1,
        status="running",
    )
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="queued-normal",
        prompt="Normal follow-up",
        sequence=2,
        status="queued",
    )
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="queued-steered",
        prompt="Steered follow-up",
        sequence=3,
        status="queued",
        priority=1,
    )
    queue = DeepSpaceTurnQueueStore(db_session)

    assert queue.finish(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        client_request_id="failed-first",
        status="failed",
        error="provider temporarily unavailable",
    )
    assert not queue.state(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    ).paused

    visible = queue.list_open(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )
    assert [turn.client_request_id for turn in visible] == [
        "queued-steered",
        "queued-normal",
        "failed-first",
    ]

    first = queue.claim_next(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )
    assert first is not None and first.client_request_id == "queued-steered"
    queue.finish(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        client_request_id="queued-steered",
        status="completed",
    )
    second = queue.claim_next(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )
    assert second is not None and second.client_request_id == "queued-normal"


def test_legacy_failure_pause_recovers_but_manual_pause_remains(db_session, seed_user, monkeypatch):
    _silence_queue_side_effects(monkeypatch)
    seeded = seed_user("QueuePauseTenant", "queue-pause@example.com", "StrongPass!1234", ("user",))
    conversation_id = _conversation(db_session, seeded)
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="legacy-pending",
        prompt="Pending prompt",
        sequence=1,
        status="queued",
    )
    db_session.add(
        DeepSpaceQueueControl(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation_id,
            paused=True,
            reason="Legacy failed-turn pause",
            failed_request_id="expired-failure",
        )
    )
    db_session.commit()
    queue = DeepSpaceTurnQueueStore(db_session)

    assert queue.resume_after_failure(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )
    claimed = queue.claim_next(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )
    assert claimed is not None and claimed.client_request_id == "legacy-pending"

    other_conversation_id = _conversation(db_session, seeded, title="Manual pause")
    _turn(
        db_session,
        seeded,
        other_conversation_id,
        request_id="manual-pending",
        prompt="Must remain paused",
        sequence=1,
        status="queued",
    )
    queue.pause(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=other_conversation_id,
    )
    assert not queue.resume_after_failure(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=other_conversation_id,
    )
    assert (
        queue.claim_next(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=other_conversation_id,
        )
        is None
    )


def test_resume_after_failure_does_not_lock_conversation_without_legacy_pause(
    db_session, seed_user, monkeypatch
):
    seeded = seed_user("QueueReadTenant", "queue-read@example.com", "StrongPass!1234", ("user",))
    conversation_id = _conversation(db_session, seeded)
    queue = DeepSpaceTurnQueueStore(db_session)

    def unexpected_conversation_lock(**_kwargs):
        raise AssertionError("ordinary queue reads must not lock the conversation")

    monkeypatch.setattr(queue, "_conversation_for_update", unexpected_conversation_lock)

    assert not queue.resume_after_failure(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )


def test_queue_reads_do_not_wait_on_active_conversation_lock(client, db_session, seed_user):
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings

    seeded = seed_user("QueueLockTenant", "queue-lock@example.com", "StrongPass!1234", ("user",))
    conversation_id = _conversation(db_session, seeded)
    db_session.commit()
    db_session.execute(
        select(Conversation).where(Conversation.id == conversation_id).with_for_update()
    ).scalar_one()

    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }

    queue_response = client.get(f"/api/v1/deepspace/chats/{conversation_id}/queue", headers=headers)
    state_response = client.get(
        f"/api/v1/deepspace/chats/{conversation_id}/queue/state", headers=headers
    )

    assert queue_response.status_code == 200
    assert state_response.status_code == 200
    db_session.rollback()


@pytest.mark.parametrize("queue_path", ["queue", "queue/state"])
def test_queue_read_returns_retryable_response_for_transient_lock_timeout(
    queue_path, client, db_session, seed_user, monkeypatch
):
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings

    seeded = seed_user("QueueBusyTenant", "queue-busy@example.com", "StrongPass!1234", ("user",))
    conversation_id = _conversation(db_session, seeded)
    db_session.commit()

    class PostgresLockTimeoutError(Exception):
        sqlstate = "55P03"

    def raise_lock_timeout(self, **_kwargs):
        raise OperationalError(
            "SELECT ... FOR UPDATE", {}, PostgresLockTimeoutError("lock timeout")
        )

    monkeypatch.setattr(DeepSpaceTurnQueueStore, "resume_after_failure", raise_lock_timeout)
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }

    response = client.get(
        f"/api/v1/deepspace/chats/{conversation_id}/{queue_path}", headers=headers
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["error"]["code"] == "SERVICE_OVERLOAD"


def test_retry_is_idempotent_and_a_failed_attempt_can_be_retried_again(
    db_session, seed_user, monkeypatch
) -> None:
    _silence_queue_side_effects(monkeypatch)
    seeded = seed_user("QueueRetryTenant", "queue-retry@example.com", "StrongPass!1234", ("user",))
    conversation_id = _conversation(db_session, seeded)
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="failed-original",
        prompt="Retry this prompt",
        sequence=1,
        status="failed",
        attachment_file_ids=["library-file-a", "library-file-b"],
    )
    queue = DeepSpaceTurnQueueStore(db_session)
    common = {
        "tenant_id": seeded.tenant_id,
        "user_id": seeded.user_id,
        "conversation_id": conversation_id,
        "failed_request_id": "failed-original",
    }

    first = queue.retry_failed(**common, client_request_id="retry-one")
    same_request = queue.retry_failed(**common, client_request_id="retry-one")
    another_click = queue.retry_failed(**common, client_request_id="retry-click-two")
    assert first.id == same_request.id == another_click.id
    assert another_click.client_request_id == "retry-one"
    assert first.prompt == "Retry this prompt"
    assert first.attachment_file_ids_json == ["library-file-a", "library-file-b"]
    assert first.resume_from_request_id == "failed-original"

    queue.finish(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        client_request_id="retry-one",
        status="failed",
        error="The retry also failed",
    )
    second = queue.retry_failed(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        failed_request_id="retry-one",
        client_request_id="retry-two",
    )
    assert second.client_request_id == "retry-two"
    assert second.resume_from_request_id == "retry-one"
    assert [
        turn.client_request_id
        for turn in queue.list_open(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation_id,
        )
    ] == ["retry-two"]


def test_queued_regeneration_keeps_its_target_through_claim_and_retry(
    db_session, seed_user, monkeypatch
) -> None:
    _silence_queue_side_effects(monkeypatch)
    seeded = seed_user(
        "QueueRegenerateTenant",
        "queue-regenerate@example.com",
        "StrongPass!1234",
        ("user",),
    )
    conversation_id = _conversation(db_session, seeded)
    repo = DeepSpaceChatRepository(db_session)
    repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation_id,
        role="user",
        content="Saved prompt",
    )
    assistant = repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation_id,
        role="assistant",
        content="Saved answer",
    )
    db_session.commit()

    queue = DeepSpaceTurnQueueStore(db_session)
    turn = queue.enqueue(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        client_request_id="regenerate-first",
        regenerate_message_id=assistant.id,
        prompt="Saved prompt",
        thinking_enabled=False,
        roles=["user"],
        permissions=["queries:run"],
    )
    claimed = queue.claim_next(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )

    assert claimed is not None
    assert claimed.client_request_id == turn.client_request_id
    assert claimed.regenerate_message_id == assistant.id
    queue.finish(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        client_request_id=turn.client_request_id,
        status="failed",
        error="worker stopped",
    )
    retry = queue.retry_failed(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        failed_request_id=turn.client_request_id,
        client_request_id="regenerate-retry",
    )

    assert retry.regenerate_message_id == assistant.id
    assert retry.resume_from_request_id == turn.client_request_id


def test_expired_worker_closes_the_saved_stream_and_marks_message_recoverable(
    db_session, seed_user, monkeypatch
) -> None:
    _silence_queue_side_effects(monkeypatch)
    seeded = seed_user(
        "QueueExpiredRunTenant",
        "queue-expired-run@example.com",
        "StrongPass!1234",
        ("user",),
    )
    conversation_id = _conversation(db_session, seeded)
    repo = DeepSpaceChatRepository(db_session)
    repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation_id,
        role="user",
        content="Recover this prompt",
    )
    assistant = repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation_id,
        role="assistant",
        content="Partial output",
        metadata_json={"status": "streaming", "client_request_id": "expired-run"},
    )
    db_session.commit()
    turn = _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="expired-run",
        prompt="Recover this prompt",
        sequence=1,
        status="running",
    )
    turn.started_at = datetime.now(UTC) - timedelta(hours=1)
    run = DeepSpaceAgentRun(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        assistant_message_id=assistant.id,
        status="failed",
        checkpoint={},
        last_error="worker_lease_expired",
        heartbeat_at=None,
    )
    db_session.add(run)
    db_session.commit()
    appended_frames: list[str] = []

    def capture_event(_db, *, frame, **_kwargs):
        appended_frames.append(frame)

    monkeypatch.setattr(turn_queue_module, "append_event", capture_event)
    recovered = DeepSpaceTurnQueueStore(db_session).recover_stale_claims(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
    )
    db_session.refresh(turn)
    db_session.refresh(assistant)

    assert recovered == 1
    assert turn.status == "failed"
    assert assistant.metadata_json["status"] == "error"
    assert assistant.metadata_json["error_code"] == "DEEPSPACE_WORKER_LEASE_EXPIRED"
    assert "available to retry" in assistant.metadata_json["error_message"]
    assert len(appended_frames) == 1
    assert appended_frames[0].startswith("event: error\n")
    assert "DEEPSPACE_WORKER_LEASE_EXPIRED" in appended_frames[0]


def test_retry_lookup_finds_the_saved_prompt_through_assistant_retry_id(
    db_session, seed_user
) -> None:
    seeded = seed_user(
        "QueuePromptLookupTenant",
        "queue-prompt-lookup@example.com",
        "StrongPass!1234",
        ("user",),
    )
    conversation_id = _conversation(db_session, seeded)
    repo = DeepSpaceChatRepository(db_session)
    original_user = repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation_id,
        role="user",
        content="The original saved prompt",
        metadata_json={"client_request_id": "original-request"},
    )
    retried_assistant = repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation_id,
        role="assistant",
        content="",
        metadata_json={"client_request_id": "retry-request"},
    )
    db_session.commit()

    found = repo.find_turn_by_request_id(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        request_id="retry-request",
    )

    assert found is not None
    assert found[0].id == original_user.id
    assert found[1].id == retried_assistant.id


def test_queue_state_repairs_legacy_failure_pause_and_returns_next_request(
    client, db_session, seed_user, monkeypatch
) -> None:
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings
    from app.deepspace.api import chats as chat_api

    seeded = seed_user("QueueStateTenant", "queue-state@example.com", "StrongPass!1234", ("user",))
    conversation_id = _conversation(db_session, seeded)
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="old-failed-turn",
        prompt="Failed prompt",
        sequence=1,
        status="failed",
    )
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="next-prompt",
        prompt="Next prompt",
        sequence=2,
        status="queued",
    )
    db_session.add(
        DeepSpaceQueueControl(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation_id,
            paused=True,
            reason="Legacy automatic failure pause",
            failed_request_id="old-failed-turn",
        )
    )
    db_session.commit()
    dispatches: list[dict[str, object]] = []
    monkeypatch.setattr(
        chat_api, "_dispatch_deepspace_queue", lambda **kwargs: dispatches.append(kwargs)
    )
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }

    response = client.get(f"/api/v1/deepspace/chats/{conversation_id}/queue/state", headers=headers)

    assert response.status_code == 200
    assert response.json()["paused"] is False
    assert response.json()["failed_request_id"] is None
    assert response.json()["active_request_id"] == "next-prompt"
    assert dispatches == [
        {
            "tenant_id": seeded.tenant_id,
            "user_id": seeded.user_id,
            "conversation_id": conversation_id,
        }
    ]


def test_edit_updates_only_the_pending_prompt_and_preserves_fifo_metadata(
    db_session, seed_user, monkeypatch
) -> None:
    _silence_queue_side_effects(monkeypatch)
    seeded = seed_user("QueueEditTenant", "queue-edit@example.com", "StrongPass!1234", ("user",))
    conversation_id = _conversation(db_session, seeded)
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="before-edit",
        prompt="First queued prompt",
        sequence=1,
        status="queued",
    )
    middle = _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="edit-me",
        prompt="Original middle prompt",
        sequence=2,
        status="queued",
        priority=1,
    )
    middle.thinking_enabled = True
    middle.reasoning_effort = "high"
    middle.roles_json = ["editor", "user"]
    middle.permissions_json = ["queries:run", "documents:read"]
    attachment_id = str(uuid.uuid4())
    middle.attachment_file_ids_json = [attachment_id]
    db_session.commit()
    db_session.refresh(middle)
    _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="after-edit",
        prompt="Last queued prompt",
        sequence=3,
        status="queued",
    )
    quota_checks = []

    def capture_quota_check(_service, **kwargs) -> None:
        # Capacity accounting must see the old persisted row and replace its
        # old logical size with the revised size exactly once.
        assert middle.prompt == "Original middle prompt"
        quota_checks.append(kwargs)

    monkeypatch.setattr(StorageQuotaService, "ensure_capacity", capture_quota_check)

    queue = DeepSpaceTurnQueueStore(db_session)
    edited = queue.update_queued_prompt(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation_id,
        client_request_id="edit-me",
        expected_prompt="Original middle prompt",
        prompt="Revised middle prompt",
    )

    assert edited is not None
    assert edited.id == middle.id
    assert edited.client_request_id == "edit-me"
    assert edited.prompt == "Revised middle prompt"
    assert edited.priority == 1
    assert edited.sequence == 2
    assert edited.status == "queued"
    assert edited.thinking_enabled is True
    assert edited.reasoning_effort == "high"
    assert edited.roles_json == ["editor", "user"]
    assert edited.permissions_json == ["queries:run", "documents:read"]
    assert edited.attachment_file_ids_json == [attachment_id]
    assert quota_checks == [
        {
            "tenant_id": seeded.tenant_id,
            "user_id": seeded.user_id,
            "additional_bytes": StorageQuotaService.estimate_bytes(
                "Revised middle prompt",
                edited.roles_json,
                edited.permissions_json,
                edited.attachment_file_ids_json,
            ),
            "replacing_bytes": StorageQuotaService.estimate_bytes(
                "Original middle prompt",
                edited.roles_json,
                edited.permissions_json,
                edited.attachment_file_ids_json,
            ),
        }
    ]
    assert [
        turn.client_request_id
        for turn in queue.list_open(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation_id,
        )
    ] == ["edit-me", "before-edit", "after-edit"]

    with pytest.raises(QueueTurnEditConflictError):
        queue.update_queued_prompt(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation_id,
            client_request_id="edit-me",
            expected_prompt="Original middle prompt",
            prompt="Stale overwrite",
        )
    assert middle.prompt == "Revised middle prompt"

    middle.status = "running"
    db_session.commit()
    with pytest.raises(QueueTurnNotEditableError):
        queue.update_queued_prompt(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation_id,
            client_request_id="edit-me",
            expected_prompt="Revised middle prompt",
            prompt="Too late to edit",
        )


def test_queue_edit_api_updates_a_pending_turn_in_place_and_rejects_stale_edit(
    client, db_session, seed_user, monkeypatch
) -> None:
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings
    from app.system.services.rate_limit_service import RateLimitService

    monkeypatch.setattr(RateLimitService, "enforce_deepspace_user_limit", lambda *a, **k: None)
    seeded = seed_user(
        "QueueEditApiTenant", "queue-edit-api@example.com", "StrongPass!1234", ("user",)
    )
    conversation_id = _conversation(db_session, seeded)
    turn = _turn(
        db_session,
        seeded,
        conversation_id,
        request_id="api-edit-me",
        prompt="The original API prompt",
        sequence=1,
        status="queued",
    )
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }
    path = f"/api/v1/deepspace/chats/{conversation_id}/queue/api-edit-me"
    other_user = seed_user(
        "QueueEditOtherTenant",
        "queue-edit-other@example.com",
        "StrongPass!1234",
        ("user",),
    )
    other_token = create_access_token(
        user_id=other_user.user_id,
        tenant_id=other_user.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    cross_tenant = client.patch(
        path,
        headers={
            "Authorization": f"Bearer {other_token}",
            "X-Tenant-Id": str(other_user.tenant_id),
        },
        json={"message": "Cross-tenant overwrite", "expected_prompt": turn.prompt},
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    response = client.patch(
        path,
        headers=headers,
        json={"message": "Updated through the API", "expected_prompt": turn.prompt},
    )

    assert response.status_code == 200
    assert response.json()["client_request_id"] == "api-edit-me"
    assert response.json()["prompt"] == "Updated through the API"
    assert response.json()["sequence"] == 1

    stale = client.patch(
        path,
        headers=headers,
        json={"message": "Stale update", "expected_prompt": "The original API prompt"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "QUEUE_TURN_EDIT_CONFLICT"

    turn.status = "running"
    db_session.commit()
    no_longer_pending = client.patch(
        path,
        headers=headers,
        json={"message": "Late update", "expected_prompt": "Updated through the API"},
    )
    assert no_longer_pending.status_code == 409
    assert no_longer_pending.json()["error"]["code"] == "QUEUE_TURN_NOT_EDITABLE"
