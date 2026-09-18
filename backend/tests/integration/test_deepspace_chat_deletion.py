from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.core.ids import generate_uuid7_with_fallback
from app.deepspace.memory.memory_service import MemoryService
from app.deepspace.models.agent_memory import AgentMemory
from app.deepspace.models.agent_runtime import (
    DeepSpaceAgentRun,
    DeepSpaceAgentStep,
    DeepSpaceRunEvent,
)
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.message import Message
from app.deepspace.models.mission_snapshot import DeepSpaceMissionSnapshot
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.deepspace.services.turn_queue import DeepSpaceTurnQueueStore
from app.system.models.storage_cleanup import StorageCleanupJob


def _seed_deepspace_conversation_with_runtime(
    session: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> uuid.UUID:
    """Create a fully-populated DeepSpace conversation with messages, runs, steps, events, memories, and queued turns."""
    repo = DeepSpaceChatRepository(session)
    conversation = repo.create_conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        title="Test Conversation for Deletion",
        kind="deepspace",
    )
    conv_id = conversation.id

    # 1. Message (repo.add_message creates initial MessageVersion automatically)
    repo.add_message(
        tenant_id=tenant_id,
        conversation_id=conv_id,
        role="assistant",
        content="Assistant response to be deleted",
    )

    # 2. Agent Run
    run = DeepSpaceAgentRun(
        id=generate_uuid7_with_fallback(),
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
        status="running",
    )
    session.add(run)
    session.flush()

    # 3. Agent Step
    step = DeepSpaceAgentStep(
        id=generate_uuid7_with_fallback(),
        run_id=run.id,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
        sequence=1,
        step_type="tool_call",
        tool_name="web_search",
        status="completed",
    )
    session.add(step)

    # 4. Run Event
    event = DeepSpaceRunEvent(
        id=generate_uuid7_with_fallback(),
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
        client_request_id=f"req_{conv_id}",
        sequence=1,
        frame="data: test\n\n",
        event_name="message",
    )
    session.add(event)

    # 5. Mission Snapshot
    snapshot = DeepSpaceMissionSnapshot(
        mission_id=generate_uuid7_with_fallback(),
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
        status="completed",
        payload={"mission": "test"},
    )
    session.add(snapshot)

    # 6. Queued Turn
    turn = DeepSpaceQueuedTurn(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
        client_request_id=f"queue_{conv_id}",
        prompt="Queued prompt",
        sequence=1,
        status="queued",
    )
    session.add(turn)

    # 7. AgentMemory tied to this conversation
    memory = AgentMemory(
        id=str(generate_uuid7_with_fallback()),
        tenant_id=str(tenant_id),
        user_id=str(user_id),
        key="fact_test_preference",
        value="User prefers dark theme",
        conversation_id=str(conv_id),
    )
    session.add(memory)

    session.commit()
    return conv_id


def test_single_conversation_delete_purges_all_runtime_artifacts_and_cache(db_session, seed_user):
    seeded = seed_user("DeletionTenant1", "delete_user1@test.com", "SecurePassword123!", ("user",))
    tenant_id = seeded.tenant_id
    user_id = seeded.user_id

    conv_id = _seed_deepspace_conversation_with_runtime(db_session, tenant_id, user_id)

    # Populate the Redis key space used by the repository's invalidation path.
    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = [
        f"deepspace:history:history-v1:{tenant_id}:{user_id}:{conv_id}:digest1"
    ]

    with patch("app.deepspace.services.context_cache.get_redis_client", return_value=mock_redis):
        repo = DeepSpaceChatRepository(db_session)
        deleted = repo.delete_conversation(
            tenant_id=tenant_id,
            conversation_id=conv_id,
            user_id=user_id,
        )
        db_session.commit()

        assert deleted is True

        # Verify Redis invalidation was executed
        mock_redis.delete.assert_called_once()

    # Verify Conversation deleted
    assert (
        db_session.execute(
            select(Conversation).where(Conversation.id == conv_id)
        ).scalar_one_or_none()
        is None
    )
    # Verify Messages and Versions deleted
    assert (
        db_session.execute(select(Message).where(Message.conversation_id == conv_id))
        .scalars()
        .all()
        == []
    )
    # Verify Agent Runs, Steps, Events deleted
    assert (
        db_session.execute(
            select(DeepSpaceAgentRun).where(DeepSpaceAgentRun.conversation_id == conv_id)
        )
        .scalars()
        .all()
        == []
    )
    assert (
        db_session.execute(
            select(DeepSpaceAgentStep).where(DeepSpaceAgentStep.conversation_id == conv_id)
        )
        .scalars()
        .all()
        == []
    )
    assert (
        db_session.execute(
            select(DeepSpaceRunEvent).where(DeepSpaceRunEvent.conversation_id == conv_id)
        )
        .scalars()
        .all()
        == []
    )
    # Verify Mission Snapshot deleted
    assert (
        db_session.execute(
            select(DeepSpaceMissionSnapshot).where(
                DeepSpaceMissionSnapshot.conversation_id == conv_id
            )
        )
        .scalars()
        .all()
        == []
    )
    # Verify Queued Turns deleted
    assert (
        db_session.execute(
            select(DeepSpaceQueuedTurn).where(DeepSpaceQueuedTurn.conversation_id == conv_id)
        )
        .scalars()
        .all()
        == []
    )
    # Verify AgentMemory linked to conversation deleted
    assert (
        db_session.execute(select(AgentMemory).where(AgentMemory.conversation_id == str(conv_id)))
        .scalars()
        .all()
        == []
    )


def test_bulk_conversation_delete_purges_all_conversations(db_session, seed_user):
    seeded = seed_user("DeletionTenant2", "delete_user2@test.com", "SecurePassword123!", ("user",))
    tenant_id = seeded.tenant_id
    user_id = seeded.user_id

    conv_id1 = _seed_deepspace_conversation_with_runtime(db_session, tenant_id, user_id)
    conv_id2 = _seed_deepspace_conversation_with_runtime(db_session, tenant_id, user_id)

    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = []

    with patch("app.deepspace.services.context_cache.get_redis_client", return_value=mock_redis):
        repo = DeepSpaceChatRepository(db_session)
        deleted_count = repo.bulk_delete_conversations(
            tenant_id=tenant_id,
            conversation_ids=[conv_id1, conv_id2],
            user_id=user_id,
        )
        db_session.commit()

        assert deleted_count == 2

    for cid in (conv_id1, conv_id2):
        assert (
            db_session.execute(
                select(Conversation).where(Conversation.id == cid)
            ).scalar_one_or_none()
            is None
        )
        assert (
            db_session.execute(
                select(DeepSpaceAgentRun).where(DeepSpaceAgentRun.conversation_id == cid)
            )
            .scalars()
            .all()
            == []
        )
        assert (
            db_session.execute(
                select(DeepSpaceAgentStep).where(DeepSpaceAgentStep.conversation_id == cid)
            )
            .scalars()
            .all()
            == []
        )
        assert (
            db_session.execute(
                select(DeepSpaceRunEvent).where(DeepSpaceRunEvent.conversation_id == cid)
            )
            .scalars()
            .all()
            == []
        )
        assert (
            db_session.execute(select(AgentMemory).where(AgentMemory.conversation_id == str(cid)))
            .scalars()
            .all()
            == []
        )


def test_turn_queue_cancel_all_for_conversation(db_session, seed_user):
    seeded = seed_user("DeletionTenant3", "delete_user3@test.com", "SecurePassword123!", ("user",))
    tenant_id = seeded.tenant_id
    user_id = seeded.user_id

    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=tenant_id, user_id=user_id, title="Queue Test"
    )
    conv_id = conversation.id

    turn1 = DeepSpaceQueuedTurn(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
        client_request_id="q1",
        prompt="p1",
        sequence=1,
        status="queued",
    )
    turn2 = DeepSpaceQueuedTurn(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
        client_request_id="q2",
        prompt="p2",
        sequence=2,
        status="running",
    )
    db_session.add_all([turn1, turn2])
    db_session.commit()

    queue_store = DeepSpaceTurnQueueStore(db_session)
    cancelled_count = queue_store.cancel_all_for_conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
    )

    assert cancelled_count == 2
    db_session.refresh(turn1)
    db_session.refresh(turn2)
    assert turn1.status == "cancelled"
    assert turn2.status == "cancelling"


@pytest.mark.asyncio
async def test_memory_consolidation_is_opt_in(db_session, seed_user):
    """Ensure that ordinary turns do not auto-save memories unless automatic_capture_enabled is True or user explicitly requests."""
    seeded = seed_user("DeletionTenant4", "delete_user4@test.com", "SecurePassword123!", ("user",))
    tenant_id = str(seeded.tenant_id)
    user_id = str(seeded.user_id)

    from app.core.config import get_settings

    mem_svc = MemoryService(db_session, get_settings())

    # User preferences default to automatic_capture_enabled = False
    prefs = await mem_svc.get_preferences(tenant_id=tenant_id, user_id=user_id)
    assert prefs["automatic_capture_enabled"] is False

    # Inferred turn without explicit "remember"
    result = await mem_svc.consolidate_turn(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=str(generate_uuid7_with_fallback()),
        prompt="I always use postgresql for my database",
    )
    # Because automatic_capture_enabled is False and prompt is not an explicit "remember" command,
    # consolidate_turn should return None and not persist anything!
    assert result is None


def test_api_delete_conversation_endpoint(client, db_session, seed_user):
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings

    seeded = seed_user("DeletionTenantAPI", "delete_api@test.com", "SecurePassword123!", ("user",))
    conv_id = _seed_deepspace_conversation_with_runtime(
        db_session, seeded.tenant_id, seeded.user_id
    )

    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}

    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = []
    with patch("app.deepspace.services.context_cache.get_redis_client", return_value=mock_redis):
        resp = client.delete(f"/api/v1/deepspace/chats/{conv_id}", headers=headers)
        assert resp.status_code == 204

    # Verify conversation deleted in DB
    assert (
        db_session.execute(
            select(Conversation).where(Conversation.id == conv_id)
        ).scalar_one_or_none()
        is None
    )
    # Verify runtime rows deleted
    assert (
        db_session.execute(
            select(DeepSpaceAgentRun).where(DeepSpaceAgentRun.conversation_id == conv_id)
        )
        .scalars()
        .all()
        == []
    )


def test_api_bulk_delete_conversations_endpoint(client, db_session, seed_user):
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings

    seeded = seed_user(
        "DeletionTenantBulkAPI", "delete_bulk_api@test.com", "SecurePassword123!", ("user",)
    )
    conv_id1 = _seed_deepspace_conversation_with_runtime(
        db_session, seeded.tenant_id, seeded.user_id
    )
    conv_id2 = _seed_deepspace_conversation_with_runtime(
        db_session, seeded.tenant_id, seeded.user_id
    )

    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}

    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = []
    with patch("app.deepspace.services.context_cache.get_redis_client", return_value=mock_redis):
        resp = client.post(
            "/api/v1/deepspace/chats/bulk-delete",
            json={"conversation_ids": [str(conv_id1), str(conv_id2)]},
            headers=headers,
        )
        assert resp.status_code == 204
        assert resp.headers.get("X-Deleted-Count") == "2"

    for cid in (conv_id1, conv_id2):
        assert (
            db_session.execute(
                select(Conversation).where(Conversation.id == cid)
            ).scalar_one_or_none()
            is None
        )
        assert (
            db_session.execute(
                select(DeepSpaceAgentRun).where(DeepSpaceAgentRun.conversation_id == cid)
            )
            .scalars()
            .all()
            == []
        )


def test_delete_message_invalidates_context_cache(client, db_session, seed_user):
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings

    seeded = seed_user("DelMsgTenant", "del_msg@test.com", "SecurePassword123!", ("user",))
    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=seeded.tenant_id, user_id=seeded.user_id, title="Msg Delete Cache Test"
    )
    repo.add_message(
        tenant_id=seeded.tenant_id, conversation_id=conversation.id, role="user", content="Hello"
    )
    assistant_msg = repo.add_message(
        tenant_id=seeded.tenant_id,
        conversation_id=conversation.id,
        role="assistant",
        content="Hi there!",
    )
    db_session.commit()

    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}

    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = [
        f"deepspace:history:history-v1:{seeded.tenant_id}:{seeded.user_id}:{conversation.id}:digest"
    ]

    with patch("app.deepspace.services.context_cache.get_redis_client", return_value=mock_redis):
        resp = client.delete(
            f"/api/v1/deepspace/chats/{conversation.id}/messages/{assistant_msg.id}",
            headers=headers,
        )
        assert resp.status_code == 204
        mock_redis.delete.assert_called_once()

    msg_in_db = repo.get_message_by_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
    )
    assert msg_in_db is None


def test_delete_conversation_atomic_nonexistent_returns_404(client, db_session, seed_user):
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings

    seeded = seed_user("DelNonexistentTenant", "del_none@test.com", "SecurePassword123!", ("user",))
    non_existent_id = generate_uuid7_with_fallback()

    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}

    with patch(
        "app.deepspace.services.runtime_store.DeepSpaceRuntimeStore.request_cancel"
    ) as mock_cancel:
        resp = client.delete(f"/api/v1/deepspace/chats/{non_existent_id}", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
        mock_cancel.assert_not_called()


def test_storage_cleanup_job_created_on_storage_failure(db_session, seed_user):
    from app.system.services.storage_service import StorageService

    seeded = seed_user(
        "DelStorageRetryTenant", "del_storage@test.com", "SecurePassword123!", ("user",)
    )
    tenant_id = seeded.tenant_id
    user_id = seeded.user_id

    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=tenant_id, user_id=user_id, title="Storage Retry Test"
    )
    conv_id = conversation.id

    ws_file = DeepSpaceWorkspaceFile(
        id=generate_uuid7_with_fallback(),
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv_id,
        name="test_report.pdf",
        storage_bucket="averqel-library",
        storage_key=f"library/{tenant_id}/{conv_id}/test_report.pdf",
    )
    db_session.add(ws_file)
    db_session.commit()

    with patch.object(
        StorageService, "delete_object", side_effect=RuntimeError("MinIO connection timed out")
    ):
        deleted = repo.delete_conversation(
            tenant_id=tenant_id, conversation_id=conv_id, user_id=user_id
        )
        db_session.commit()
        assert deleted is True

    job = db_session.execute(
        select(StorageCleanupJob).where(
            StorageCleanupJob.tenant_id == tenant_id,
            StorageCleanupJob.bucket == "averqel-library",
            StorageCleanupJob.object_key == f"library/{tenant_id}/{conv_id}/test_report.pdf",
        )
    ).scalar_one_or_none()

    assert job is not None
    assert job.status == "pending"
    assert "MinIO connection timed out" in (job.last_error or "")


@pytest.mark.asyncio
async def test_memory_intent_guard_in_new_chats(db_session, seed_user):
    from app.auth.dependencies import AuthContext
    from app.core.config import get_settings
    from app.deepspace.services.chat_service import DeepSpaceChatService

    seeded = seed_user("MemGuardTenant", "mem_guard@test.com", "SecurePassword123!", ("user",))
    tenant_id = seeded.tenant_id
    user_id = seeded.user_id

    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=tenant_id, user_id=user_id, title="Memory Guard Test"
    )
    conv_id = conversation.id

    svc = DeepSpaceChatService(db=db_session, settings=get_settings())
    auth = AuthContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=frozenset(["user"]),
        token_id=str(generate_uuid7_with_fallback()),
        permissions=frozenset(["queries:run"]),
    )

    # 1. Without memory intent (user prompt does not ask to remember/recall)
    result_without_intent = await svc._execute_productivity_tool(
        tool_name="find",
        arguments={"target": "memory", "query": "database preference"},
        auth=auth,
        conversation_id=conv_id,
        web_provider=None,
        web_candidate=None,
        request=None,
        user_prompt="Help me write a Python script for CSV parsing",
    )
    assert result_without_intent.get("retrieval_disabled") is True
    assert "Memory access is only enabled upon explicit user request" in result_without_intent.get(
        "message", ""
    )

    read_without_intent = await svc._execute_productivity_tool(
        tool_name="read",
        arguments={"target": "memory", "memory_key": "favorite_database"},
        auth=auth,
        conversation_id=conv_id,
        web_provider=None,
        web_candidate=None,
        request=None,
        user_prompt="Help me write a Python script for CSV parsing",
    )
    assert read_without_intent.get("retrieval_disabled") is True
    assert "Memory access is only enabled upon explicit user request" in read_without_intent.get(
        "message", ""
    )

    # 2. With explicit memory intent in user prompt
    result_with_intent = await svc._execute_productivity_tool(
        tool_name="find",
        arguments={"target": "memory", "query": "database preference"},
        auth=auth,
        conversation_id=conv_id,
        web_provider=None,
        web_candidate=None,
        request=None,
        user_prompt="Do you remember what database preference I have saved?",
    )
    assert (
        result_with_intent.get("retrieval_disabled") is not True or "memories" in result_with_intent
    )


@pytest.mark.asyncio
async def test_library_search_stops_on_empty_with_guidance(db_session, seed_user):
    from app.auth.dependencies import AuthContext
    from app.core.config import get_settings
    from app.deepspace.services.chat_service import DeepSpaceChatService

    seeded = seed_user("LibStopTenant", "lib_stop@test.com", "SecurePassword123!", ("user",))
    tenant_id = seeded.tenant_id
    user_id = seeded.user_id

    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=tenant_id, user_id=user_id, title="Lib Stop Test"
    )
    conv_id = conversation.id

    svc = DeepSpaceChatService(db=db_session, settings=get_settings())
    auth = AuthContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=frozenset(["user"]),
        token_id=str(generate_uuid7_with_fallback()),
        permissions=frozenset(["queries:run"]),
    )

    result = await svc._execute_productivity_tool(
        tool_name="find",
        arguments={"target": "library", "query": "non_existent_document.pdf"},
        auth=auth,
        conversation_id=conv_id,
        web_provider=None,
        web_candidate=None,
        request=None,
        user_prompt="Find my non existent document in the library",
    )

    assert result["files"] == []
    assert result["status"] == "not_found"
    assert (
        "Stop and inform the user that the file was not found. Do not invent or guess filenames."
        in result["message"]
    )


def test_delete_conversation_is_fully_atomic_and_rolls_back_on_error(client, db_session, seed_user):
    from app.auth.dependencies import create_access_token
    from app.core.config import get_settings

    seeded = seed_user("DelAtomicTenant", "del_atomic@test.com", "SecurePassword123!", ("user",))
    conv_id = _seed_deepspace_conversation_with_runtime(
        db_session, seeded.tenant_id, seeded.user_id
    )

    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"user"},
        settings=get_settings(),
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}

    with patch(
        "app.deepspace.repositories.chat.DeepSpaceChatRepository.delete_conversation",
        side_effect=RuntimeError("Simulated DB lock error"),
    ):
        with pytest.raises(RuntimeError, match="Simulated DB lock error"):
            client.delete(f"/api/v1/deepspace/chats/{conv_id}", headers=headers)

    # Because commit=False was passed to cancel routines, the transaction was rolled back.
    # The conversation and runtime data must still exist intact in the DB!
    conv = db_session.execute(
        select(Conversation).where(Conversation.id == conv_id)
    ).scalar_one_or_none()
    assert conv is not None

    # The active run was NOT permanently committed as 'cancelling' without the chat being deleted
    run = db_session.execute(
        select(DeepSpaceAgentRun).where(DeepSpaceAgentRun.conversation_id == conv_id)
    ).scalar_one_or_none()
    assert run is not None
    assert run.status == "running"


@pytest.mark.asyncio
async def test_active_worker_aborts_turn_persistence_if_conversation_deleted(db_session, seed_user):
    from app.auth.dependencies import AuthContext
    from app.core.config import get_settings
    from app.deepspace.services.chat_service import DeepSpaceChatService

    seeded = seed_user("WorkerRaceTenant", "worker_race@test.com", "SecurePassword123!", ("user",))
    tenant_id = seeded.tenant_id
    user_id = seeded.user_id

    repo = DeepSpaceChatRepository(db_session)
    conversation = repo.create_conversation(
        tenant_id=tenant_id, user_id=user_id, title="Worker Race Test"
    )
    conv_id = conversation.id

    svc = DeepSpaceChatService(db=db_session, settings=get_settings())
    auth = AuthContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=frozenset(["user"]),
        token_id=str(generate_uuid7_with_fallback()),
        permissions=frozenset(["queries:run"]),
    )

    # Concurrently delete conversation before turn persistence finishes
    repo.delete_conversation(tenant_id=tenant_id, conversation_id=conv_id, user_id=user_id)
    db_session.commit()

    # Pre-commit check confirms the conversation was deleted and aborts
    active_conv = svc.chat.get_conversation(tenant_id=auth.tenant_id, conversation_id=conv_id)
    assert active_conv is None

    # Confirm no messages exist or were created for this deleted conversation
    messages = (
        db_session.execute(select(Message).where(Message.conversation_id == conv_id))
        .scalars()
        .all()
    )
    assert messages == []


@pytest.mark.asyncio
async def test_library_search_empty_forces_immediate_stop_in_turn_loop(monkeypatch):
    """Verify that when find(target='library') returns not_found, the agent loop stops immediately via forced_answer without continuing to guess."""
    from types import SimpleNamespace
    from uuid import uuid4

    from app.auth.dependencies import AuthContext
    from app.deepspace.services import chat_service as chat_service_module
    from app.deepspace.services.chat_service import DeepSpaceChatService

    call_count = 0

    class _ToolRegistryWithLibraryCall:
        def __init__(self, *args, **kwargs):
            pass

        def get_chat_provider_from_selection(self, candidate):
            provider = MagicMock()

            async def _fake_stream(*a, **kw):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    yield {
                        "type": "tool_calls_delta",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_find_1",
                                "function": {
                                    "name": "find",
                                    "arguments": '{"target":"library","query":"report.pdf"}',
                                },
                            }
                        ],
                    }
                else:
                    yield {"type": "delta", "text": "I am guessing another filename."}

            provider.stream_generate_events = _fake_stream
            return provider

    class _MockSelectionService:
        def __init__(self, *args, **kwargs):
            pass

        def resolve_chat(self, **kwargs):
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        model_name="mock-model",
                        provider_type="mock",
                        base_url="https://mock.ai",
                        api_key="test-key",
                        context_window=131072,
                        context_window_source="live_model",
                    )
                ]
            )

    class _MockTaskStore:
        def __init__(self, *args, **kwargs):
            pass

        def find_workspace_files(self, *args, **kwargs):
            return []

        def check_tasks(self, *args, **kwargs):
            return {"task_count": 0, "complete": True, "tasks": []}

        def read_note(self, *args, **kwargs):
            return None

        def list_workspace_entries(self, *args, **kwargs):
            return []

    monkeypatch.setattr(chat_service_module, "ProviderRegistry", _ToolRegistryWithLibraryCall)
    monkeypatch.setattr(chat_service_module, "ProviderSelectionService", _MockSelectionService)
    monkeypatch.setattr(chat_service_module, "DeepSpaceTaskLoopStore", _MockTaskStore)

    mock_db = MagicMock()
    mock_chat_repo = MagicMock()
    mock_msg = MagicMock(id=uuid4())
    mock_chat_repo.add_message.return_value = mock_msg
    mock_chat_repo.get_conversation.return_value = MagicMock()

    service = DeepSpaceChatService(
        db=mock_db,
        settings=SimpleNamespace(
            llm_temperature=0.2,
            llm_max_tokens_per_request=128,
            deepspace_sandbox_timeout_seconds=30,
            deepspace_max_concurrent_tools=4,
        ),
    )
    service.chat = mock_chat_repo

    auth = AuthContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        roles=frozenset(["user"]),
        token_id=str(uuid4()),
        permissions=frozenset(["queries:run"]),
    )

    frames = [
        frame
        async for frame in service.stream_turn(
            auth=auth,
            conversation_id=uuid4(),
            prompt="Find report.pdf in library",
            thinking_enabled=False,
        )
    ]

    assert call_count == 1
    result_frames = [f for f in frames if f.startswith("event: tool_result")]
    assert len(result_frames) == 1
    result_data = json.loads(result_frames[0].split("data: ", 1)[1].strip())
    assert result_data["tool_name"] == "find"
    output_obj = json.loads(result_data["output"])
    assert output_obj["status"] == "not_found"

    delta_frames = [f for f in frames if f.startswith("event: delta")]
    assert len(delta_frames) >= 1
    delta_text = "".join(json.loads(f.split("data: ", 1)[1].strip())["text"] for f in delta_frames)
    assert "No file found matching query in the Library" in delta_text
