"""DeepSpace productivity chat, note, history, and memory endpoints."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    API_KEY_PREFIX,
    AuthContext,
    build_auth_context_from_api_key,
    build_auth_context_from_jwt,
    decode_access_token,
    get_auth_context,
)
from app.auth.rbac import require_permissions, resolve_permissions
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.deepspace.schemas.chats import (
    ApprovalDecisionRequest,
    BulkDeleteRequest,
    ChatHistoryResponse,
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationSchema,
    ConversationUpdate,
    MemoryFactSchema,
    MemoryPreferencesSchema,
    MemoryPreferencesUpdateRequest,
    MemoryRetentionReportSchema,
    MemoryUpdateRequest,
    MemoryWriteRequest,
    MessageEditRequest,
    MessageSchema,
    MessageVersionSchema,
    RegenerateRequest,
)
from app.deepspace.services.chat_service import DeepSpaceChatService, sse
from app.deepspace.services.run_events import (
    cancellation_key,
    channel_name,
    decode_live_event,
    event_name_from_frame,
    frames_after,
    is_terminal_event,
    load_events,
)
from app.deepspace.services.runtime_store import DeepSpaceRuntimeStore
from app.deepspace.workers.tasks import run_deepspace_task
from app.platform.database.session import get_db
from app.system.services.rate_limit_service import RateLimitService

router = APIRouter(prefix="/deepspace/chats", tags=["deepspace-chats"])
logger = logging.getLogger(__name__)
CONVERSATION_KIND = "deepspace"
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _serialize_message(message: Any) -> MessageSchema:
    versions = [MessageVersionSchema.model_validate(item) for item in message.versions]
    active_version = message.active_version
    return MessageSchema(
        id=message.id,
        role=message.role,
        content=active_version.content if active_version is not None else message.content,
        metadata_json=(
            dict(active_version.metadata_json)
            if active_version is not None
            else dict(message.metadata_json or {})
        ),
        created_at=message.created_at,
        active_version_id=message.active_version_id,
        active_version_index=(active_version.version_index if active_version is not None else 1),
        version_count=max(len(versions), 1),
        versions=versions,
    )


async def _authenticate_websocket_auth_context(
    websocket: Any,
    *,
    db: Session,
    settings: Settings,
) -> AuthContext:
    """Shared authentication helper for client storage and collection sockets."""
    token = str(websocket.query_params.get("token") or "").strip()
    tenant_id = str(websocket.query_params.get("tenant_id") or "").strip() or None
    if not token:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="Bearer access token or API key is required.",
            status_code=401,
        )

    if token.startswith(API_KEY_PREFIX):
        from app.auth.repositories.api_keys import ApiKeysRepository

        repo = ApiKeysRepository(db)
        api_key = repo.get_by_hash(key_hash=repo.hash_key(token))
        if api_key is None:
            raise ApiError(
                code="INVALID_API_KEY",
                message="API key is invalid or revoked.",
                status_code=401,
            )
        requested_tenant_id = None
        if tenant_id:
            try:
                requested_tenant_id = uuid.UUID(tenant_id)
            except ValueError as exc:
                raise ApiError(
                    code="INVALID_TENANT_ID",
                    message="tenant_id must be a valid UUID.",
                    status_code=400,
                ) from exc
        return build_auth_context_from_api_key(
            api_key=api_key,
            requested_tenant_id=requested_tenant_id,
            db=db,
        )

    return build_auth_context_from_jwt(
        claims=decode_access_token(token, settings),
        x_tenant_id=tenant_id,
        db=db,
    )


def _require_websocket_permissions(auth: AuthContext) -> None:
    granted = resolve_permissions(
        roles=frozenset(auth.roles),
        direct_permissions=getattr(auth, "permissions", frozenset()),
    )
    if "queries:run" not in granted:
        raise ApiError(
            code="FORBIDDEN",
            message="Insufficient permissions for requested operation.",
            status_code=403,
            details={"missing_permissions": ["queries:run"]},
        )


@router.get(
    "",
    response_model=ConversationListResponse,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def list_conversations(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationListResponse:
    from app.deepspace.integrations.client_proxy import client_proxy_registry

    if client_proxy_registry.is_storage_connected(str(auth.tenant_id), str(auth.user_id)):
        data = await client_proxy_registry.db_proxy_call(
            str(auth.tenant_id),
            str(auth.user_id),
            "db.chats.list_conversations",
            {
                "limit": limit,
                "offset": offset,
                "user_id": str(auth.user_id),
                "kind": CONVERSATION_KIND,
            },
            channel="storage",
        )
        return ConversationListResponse(
            items=[ConversationSchema.model_validate(item) for item in data],
            total=len(data),
        )

    repo = DeepSpaceChatRepository(db)
    items = repo.list_conversations(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        items=[ConversationSchema.model_validate(item) for item in items],
        total=len(items),
    )


@router.post(
    "",
    response_model=ConversationSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def create_conversation(
    payload: ConversationCreateRequest | None = None,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ConversationSchema:
    from app.deepspace.integrations.client_proxy import client_proxy_registry

    data = payload or ConversationCreateRequest()
    if client_proxy_registry.is_storage_connected(str(auth.tenant_id), str(auth.user_id)):
        conversation = await client_proxy_registry.db_proxy_call(
            str(auth.tenant_id),
            str(auth.user_id),
            "db.chats.create_conversation",
            {
                "user_id": str(auth.user_id),
                "title": data.title,
                "content_html": data.content_html,
                "kind": CONVERSATION_KIND,
            },
            channel="storage",
        )
        repo = DeepSpaceChatRepository(db)
        conversation_id = uuid.UUID(str(conversation["id"]))
        if (
            repo.get_conversation(
                tenant_id=auth.tenant_id,
                conversation_id=conversation_id,
                user_id=auth.user_id,
                kind=CONVERSATION_KIND,
            )
            is None
        ):
            repo.create_conversation(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                kind=CONVERSATION_KIND,
                title=str(conversation.get("title") or data.title),
            )
            db.commit()
        return ConversationSchema.model_validate(conversation)

    repo = DeepSpaceChatRepository(db)
    conversation = repo.create_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
        title=data.title,
        content_html=data.content_html,
    )
    db.commit()
    return ConversationSchema.model_validate(conversation)


@router.get(
    "/{conversation_id}/messages",
    response_model=ChatHistoryResponse,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_chat_history(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ChatHistoryResponse:
    from app.deepspace.integrations.client_proxy import client_proxy_registry

    if client_proxy_registry.is_storage_connected(str(auth.tenant_id), str(auth.user_id)):
        data = await client_proxy_registry.db_proxy_call(
            str(auth.tenant_id),
            str(auth.user_id),
            "db.chats.get_chat_history",
            {"conversation_id": str(conversation_id), "user_id": str(auth.user_id)},
            channel="storage",
        )
        return ChatHistoryResponse(messages=[MessageSchema.model_validate(item) for item in data])

    repo = DeepSpaceChatRepository(db)
    conversation = repo.get_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    if conversation is None:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404
        )
    messages = repo.get_messages(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    runtime = DeepSpaceRuntimeStore(db)
    serialized_messages: list[MessageSchema] = []
    for item in messages:
        serialized = _serialize_message(item)
        if item.role == "assistant":
            durable_steps = runtime.history_steps_for_message(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                assistant_message_id=item.id,
            )
            if durable_steps:
                serialized.metadata_json = {
                    **serialized.metadata_json,
                    "agent_steps": durable_steps,
                }
        serialized_messages.append(serialized)
    return ChatHistoryResponse(messages=serialized_messages)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ConversationSchema:
    repo = DeepSpaceChatRepository(db)
    if payload.title is None and payload.content_html is None:
        raise ApiError(
            code="INVALID_REQUEST", message="A title or note body is required.", status_code=400
        )
    updated = repo.update_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        title=payload.title,
        content_html=payload.content_html,
        kind=CONVERSATION_KIND,
    )
    if not updated:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404
        )
    db.commit()
    conversation = repo.get_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    if conversation is None:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found after update",
            status_code=404,
        )
    return ConversationSchema.model_validate(conversation)


@router.delete(
    "/{conversation_id}",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = DeepSpaceChatRepository(db)
    if not repo.delete_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    ):
        raise ApiError(
            code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404
        )
    db.commit()
    return Response(status_code=204)


@router.post(
    "/{conversation_id}/cancel",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def cancel_deepspace_chat(
    conversation_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    request_id = ""
    try:
        payload = await request.json()
        request_id = str(payload.get("client_request_id") or "").strip()
    except Exception:  # noqa: BLE001, B110 - malformed optional JSON is treated as no request id
        request_id = ""
    if request_id:
        cancel_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await cancel_client.set(
                cancellation_key(auth.tenant_id, auth.user_id, request_id),
                "1",
                ex=60 * 60 * 24,
            )
        finally:
            await cancel_client.close()
    cancelled = DeepSpaceRuntimeStore(db).request_cancel(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    return Response(
        status_code=204, headers={"X-DeepSpace-Cancel-Requested": "1" if cancelled else "0"}
    )


@router.post(
    "/queued/{client_request_id}/cancel",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def cancel_queued_deepspace_run(
    client_request_id: str,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Cancel a queued run before its worker has created a conversation run row."""
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.set(
            cancellation_key(auth.tenant_id, auth.user_id, client_request_id),
            "1",
            ex=60 * 60 * 24,
        )
    finally:
        await client.close()
    return Response(status_code=204, headers={"X-DeepSpace-Cancel-Requested": "1"})


@router.post(
    "/{conversation_id}/approvals/{approval_id}",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def resolve_deepspace_approval(
    conversation_id: uuid.UUID,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    resolved = DeepSpaceRuntimeStore(db).resolve_approval(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        approval_id=approval_id,
        decision=payload.decision,
    )
    if resolved is None:
        raise ApiError(
            code="APPROVAL_NOT_FOUND", message="Approval request not found.", status_code=404
        )
    if resolved.get("status") == "already_resolved":
        raise ApiError(
            code="APPROVAL_ALREADY_RESOLVED",
            message="Approval request was already resolved.",
            status_code=409,
        )
    return {
        "approval_id": approval_id,
        "decision": payload.decision,
        "tool_name": resolved.get("tool_name"),
        "status": "resolved",
    }


@router.post(
    "/bulk-delete",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def bulk_delete_conversations(
    payload: BulkDeleteRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = DeepSpaceChatRepository(db)
    count = repo.bulk_delete_conversations(
        tenant_id=auth.tenant_id,
        conversation_ids=payload.conversation_ids,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    db.commit()
    return Response(status_code=204, headers={"X-Deleted-Count": str(count)})


@router.delete(
    "/{conversation_id}/messages/{message_id}",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def delete_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = DeepSpaceChatRepository(db)
    message = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        kind=CONVERSATION_KIND,
    )
    if message is None:
        raise ApiError(code="MESSAGE_NOT_FOUND", message="Message not found.", status_code=404)
    if message.role != "assistant":
        raise ApiError(
            code="INVALID_MESSAGE_ROLE",
            message="Only assistant messages can be deleted.",
            status_code=400,
        )
    repo.delete_message(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        kind=CONVERSATION_KIND,
    )
    db.commit()
    return Response(status_code=204)


@router.patch(
    "/{conversation_id}/messages/{message_id}",
    response_model=MessageSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def edit_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: MessageEditRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> MessageSchema:
    repo = DeepSpaceChatRepository(db)
    user_message, assistant_message = repo.get_latest_turn_pair(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    if user_message is None or assistant_message is None or user_message.id != message_id:
        raise ApiError(
            code="MESSAGE_EDIT_NOT_ALLOWED",
            message="Only the latest user message can be edited.",
            status_code=409,
        )
    repo.create_message_version(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        message_id=message_id,
        content=payload.content,
        metadata_json=user_message.metadata_json,
        source_type="user_edit",
        activate=True,
    )
    db.commit()
    message = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        kind=CONVERSATION_KIND,
    )
    if message is None:
        raise ApiError(code="MESSAGE_NOT_FOUND", message="Message not found.", status_code=404)
    return _serialize_message(message)


@router.patch(
    "/{conversation_id}/messages/{message_id}/versions/{version_id}/activate",
    response_model=MessageSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def activate_message_version(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> MessageSchema:
    repo = DeepSpaceChatRepository(db)
    message = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        kind=CONVERSATION_KIND,
    )
    if message is None:
        raise ApiError(code="MESSAGE_NOT_FOUND", message="Message not found.", status_code=404)
    repo.activate_message_version(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        message_id=message_id,
        version_id=version_id,
        user_id=auth.user_id,
    )
    db.commit()
    refreshed = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        kind=CONVERSATION_KIND,
    )
    if refreshed is None:
        raise ApiError(code="MESSAGE_NOT_FOUND", message="Message not found.", status_code=404)
    return _serialize_message(refreshed)


@router.post(
    "/stream",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def stream_deepspace_chat(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    raw_payload = await request.json()
    prompt = str(raw_payload.get("message", ""))
    conversation_id_raw = raw_payload.get("conversation_id")
    conversation_id = uuid.UUID(str(conversation_id_raw)) if conversation_id_raw else None
    resume_approval_id = str(raw_payload.get("resume_approval_id") or "").strip() or None
    resume_user_question_id = (
        str(raw_payload.get("resume_user_question_id") or "").strip() or None
    )
    if not prompt.strip() and not resume_approval_id and not resume_user_question_id:

        async def empty_stream() -> AsyncIterator[str]:
            yield sse("error", {"code": "EMPTY_MESSAGE", "message": "Message cannot be empty."})

        return StreamingResponse(
            empty_stream(), media_type="text/event-stream", headers=SSE_HEADERS
        )
    client_request_id = str(raw_payload.get("client_request_id") or "").strip() or str(uuid.uuid4())
    reconnect = bool(raw_payload.get("reconnect", False))
    try:
        after_sequence = max(0, int(raw_payload.get("after_sequence") or 0))
    except (TypeError, ValueError):
        after_sequence = 0
    thinking_enabled = bool(raw_payload.get("thinking_enabled", False))
    if not reconnect and not resume_approval_id and not resume_user_question_id:
        RateLimitService(settings).enforce_deepspace_user_limit(
            request=request,
            user_id=str(auth.user_id),
        )

    async def iterator() -> AsyncIterator[str]:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        last_sequence = after_sequence
        try:
            await pubsub.subscribe(channel_name(client_request_id))
            if not reconnect:
                try:
                    run_deepspace_task.apply_async(
                        kwargs={
                            "tenant_id": str(auth.tenant_id),
                            "user_id": str(auth.user_id),
                            "roles": sorted(auth.roles),
                            "permissions": sorted(auth.permissions),
                            "conversation_id": str(conversation_id) if conversation_id else None,
                            "prompt": prompt,
                            "client_request_id": client_request_id,
                            "thinking_enabled": thinking_enabled,
                            "resume_approval_id": resume_approval_id,
                            "resume_user_question_id": resume_user_question_id,
                        }
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to enqueue detached DeepSpace run")
                    yield sse(
                        "error",
                        {
                            "code": "DEEPSPACE_QUEUE_UNAVAILABLE",
                            "message": "DeepSpace could not start this response. Please retry.",
                        },
                    )
                    return

            terminal = False
            while not terminal:
                # PostgreSQL is the replay source of truth. This also closes
                # the small race between queue submission and Redis subscribe.
                if conversation_id is not None:
                    db.rollback()
                    stored = load_events(
                        db,
                        tenant_id=auth.tenant_id,
                        user_id=auth.user_id,
                        conversation_id=conversation_id,
                        client_request_id=client_request_id,
                        after_sequence=last_sequence,
                    )
                    for sequence, frame in frames_after(stored, after_sequence=last_sequence):
                        last_sequence = sequence
                        yield frame
                        terminal = is_terminal_event(event_name_from_frame(frame))
                        if terminal:
                            break
                    if terminal:
                        return

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    yield ": keep-alive\n\n"
                    await asyncio.sleep(0)
                    continue
                decoded = decode_live_event(str(message.get("data") or ""))
                if decoded is None:
                    continue
                sequence, frame = decoded
                if sequence <= last_sequence:
                    continue
                last_sequence = sequence
                yield frame
                terminal = is_terminal_event(event_name_from_frame(frame))
        finally:
            try:
                await pubsub.unsubscribe(channel_name(client_request_id))
                await pubsub.close()
                await redis_client.close()
            except Exception:  # noqa: BLE001
                logger.debug("DeepSpace detached stream cleanup failed", exc_info=True)

    return StreamingResponse(iterator(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post(
    "/{conversation_id}/messages/{message_id}/regenerate/stream",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def regenerate_message_stream(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: RegenerateRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    repo = DeepSpaceChatRepository(db)
    source_message = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=auth.user_id,
    )
    if source_message is None or source_message.role != "assistant":
        raise ApiError(
            code="MESSAGE_NOT_FOUND", message="DeepSpace turn not found.", status_code=404
        )
    messages = list(
        repo.get_messages(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
        )
    )
    source_index = next((index for index, item in enumerate(messages) if item.id == message_id), -1)
    if source_index < 0:
        raise ApiError(
            code="MESSAGE_NOT_FOUND", message="DeepSpace turn not found.", status_code=404
        )
    user_message = next(
        (item for item in reversed(messages[:source_index]) if item.role == "user"), None
    )
    if user_message is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND", message="DeepSpace source prompt not found.", status_code=404
        )
    source_prompt = (
        user_message.active_version.content
        if user_message.active_version is not None
        else user_message.content
    )
    service = DeepSpaceChatService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        async for chunk in service.stream_turn(
            auth=auth,
            conversation_id=conversation_id,
            prompt=source_prompt,
            thinking_enabled=payload.thinking_enabled,
            request=request,
        ):
            yield chunk

    return StreamingResponse(iterator(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post(
    "/{conversation_id}/messages/{message_id}/edit-and-regenerate/stream",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def edit_and_regenerate_stream(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    raw_payload = await request.json()
    content = str(raw_payload.get("content", ""))
    repo = DeepSpaceChatRepository(db)
    edited = repo.create_message_version(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=auth.user_id,
        content=content,
    )
    if edited is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND", message="DeepSpace message not found.", status_code=404
        )
    db.commit()
    service = DeepSpaceChatService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        async for chunk in service.stream_turn(
            auth=auth,
            conversation_id=conversation_id,
            prompt=content,
            thinking_enabled=bool(raw_payload.get("thinking_enabled", True)),
            request=request,
        ):
            yield chunk

    return StreamingResponse(iterator(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/memory/search", response_model=dict[str, Any])
async def search_memories(
    query: str = Query(..., min_length=1),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.deepspace.memory.memory_service import MemoryService

    results = await MemoryService(db).search_memories(
        tenant_id=auth.tenant_id, user_id=auth.user_id, query=query
    )
    return {"results": results}


@router.get("/memory", response_model=list[MemoryFactSchema])
async def list_memories(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    from app.deepspace.memory.memory_service import MemoryService

    return await MemoryService(db).list_all_memories(tenant_id=auth.tenant_id, user_id=auth.user_id)


@router.post("/memory", response_model=MemoryFactSchema, status_code=201)
async def write_memory(
    payload: MemoryWriteRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.deepspace.memory.memory_service import MemoryService

    memory_id = await MemoryService(db).store_fact(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        key=payload.key,
        value=payload.value,
        scope=payload.scope,
        tags=payload.tags,
        importance_score=payload.importance_score,
        confidence_score=payload.confidence_score,
        source="manual_memory",
        metadata_json=payload.metadata,
    )
    memory = await MemoryService(db).get_memory(
        tenant_id=auth.tenant_id, user_id=auth.user_id, memory_id=memory_id
    )
    if memory is None:
        raise ApiError(
            code="MEMORY_NOT_FOUND",
            message="Memory was not available after saving.",
            status_code=500,
        )
    return memory


@router.get("/memory/preferences", response_model=MemoryPreferencesSchema)
async def get_memory_preferences(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    from app.deepspace.memory.memory_service import MemoryService

    return await MemoryService(db).get_preferences(tenant_id=auth.tenant_id, user_id=auth.user_id)


@router.patch("/memory/preferences", response_model=MemoryPreferencesSchema)
async def update_memory_preferences(
    payload: MemoryPreferencesUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    from app.deepspace.memory.memory_service import MemoryService

    return await MemoryService(db).update_preferences(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        automatic_capture_enabled=payload.automatic_capture_enabled,
        review_inferred_memories=payload.review_inferred_memories,
        memory_retrieval_enabled=payload.memory_retrieval_enabled,
    )


@router.patch("/memory/{memory_id}", response_model=MemoryFactSchema)
async def update_memory(
    memory_id: str,
    payload: MemoryUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.deepspace.memory.memory_service import MemoryService

    memory = await MemoryService(db).update_memory(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        memory_id=memory_id,
        value=payload.value,
        scope=payload.scope,
        tags=payload.tags,
        importance_score=payload.importance_score,
        confidence_score=payload.confidence_score,
        metadata_json=payload.metadata,
    )
    if memory is None:
        raise ApiError(code="MEMORY_NOT_FOUND", message="Memory not found.", status_code=404)
    return memory


@router.post("/memory/{memory_id}/approve", response_model=MemoryFactSchema)
async def approve_memory_candidate(
    memory_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.deepspace.memory.memory_service import MemoryService

    memory = await MemoryService(db).approve_memory_candidate(
        tenant_id=auth.tenant_id, user_id=auth.user_id, memory_id=memory_id
    )
    if memory is None:
        raise ApiError(
            code="MEMORY_CANDIDATE_NOT_FOUND",
            message="Memory candidate not found.",
            status_code=404,
        )
    return memory


@router.delete("/memory/{memory_id}/candidate", status_code=204)
async def reject_memory_candidate(
    memory_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    from app.deepspace.memory.memory_service import MemoryService

    deleted = await MemoryService(db).reject_memory_candidate(
        tenant_id=auth.tenant_id, user_id=auth.user_id, memory_id=memory_id
    )
    if not deleted:
        raise ApiError(
            code="MEMORY_CANDIDATE_NOT_FOUND",
            message="Memory candidate not found.",
            status_code=404,
        )
    return Response(status_code=204)


@router.delete("/memory/clear", status_code=204)
async def clear_personal_memory(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    from app.deepspace.memory.memory_service import MemoryService

    await MemoryService(db).clear_personal_memories(tenant_id=auth.tenant_id, user_id=auth.user_id)
    return Response(status_code=204)


@router.delete("/memory/{key}")
async def forget_memory(
    key: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    from app.deepspace.memory.memory_service import MemoryService

    success = await MemoryService(db).forget_memory(
        tenant_id=auth.tenant_id, user_id=auth.user_id, key=key
    )
    if not success:
        raise ApiError(
            code="MEMORY_NOT_FOUND", message=f"Memory key '{key}' not found.", status_code=404
        )
    return Response(status_code=204)


@router.post("/memory/cleanup", response_model=dict[str, Any])
async def cleanup_memories(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    from app.deepspace.memory.memory_service import MemoryService

    return await MemoryService(db).cleanup_duplicate_memories(
        tenant_id=auth.tenant_id, user_id=auth.user_id
    )


@router.post("/memory/cleanup-stale", response_model=dict[str, Any])
async def cleanup_stale_memories(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    retention_days: Annotated[int, Query(ge=1, le=3650)] = 7,
) -> Any:
    from app.deepspace.memory.memory_service import MemoryService

    return await MemoryService(db).cleanup_stale_memories(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        retention_days=retention_days,
    )


@router.get("/memory/retention", response_model=MemoryRetentionReportSchema)
async def evaluate_memory_retention(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    retention_days: Annotated[int, Query(ge=1, le=3650)] = 7,
) -> Any:
    from app.deepspace.memory.memory_service import MemoryService

    return await MemoryService(db).evaluate_memory_retention(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        retention_days=retention_days,
    )


@router.get("/memory/evaluation", response_model=MemoryRetentionReportSchema)
async def evaluate_memory_quality(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    sample_queries: Annotated[list[str] | None, Query()] = None,
) -> MemoryRetentionReportSchema:
    from app.deepspace.memory.memory_service import MemoryService

    report = await MemoryService(db).evaluate_memory_quality(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        sample_queries=sample_queries or None,
    )
    retention_days = report.get("session_retention_days") or 7
    report["retention_policy"] = {
        "session_retention_days": retention_days,
        "decay_half_life_days": report.get("retention_policy", {}).get(
            "decay_half_life_days", 120.0
        ),
    }
    report.setdefault("session_retention_days", retention_days)
    return MemoryRetentionReportSchema.model_validate(report)
