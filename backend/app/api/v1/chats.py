from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.auth.rbac import require_permissions
from app.db.session import get_db
from app.repositories.query.chat import ChatRepository
from app.schemas.query.chats import (
    BulkDeleteRequest,
    ChatHistoryResponse,
    ConversationListResponse,
    ConversationSchema,
    ConversationUpdate,
    MessageEditRequest,
    MessageSchema,
    MessageVersionSchema,
    RegenerateRequest,
)
from app.services.query.query_service import QueryService
from app.services.system.rate_limit_service import RateLimitService

router = APIRouter(prefix="/chats", tags=["chats"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _validate_top_k_bounds(*, top_k: int, settings: Settings) -> None:
    if top_k < settings.query_top_k_min or top_k > settings.query_top_k_max:
        raise ApiError(
            code="TOP_K_OUT_OF_RANGE",
            message="top_k is outside allowed bounds.",
            status_code=400,
            details={
                "min": settings.query_top_k_min,
                "max": settings.query_top_k_max,
            },
        )


def _serialize_message(message: Any) -> MessageSchema:
    versions = [MessageVersionSchema.model_validate(item) for item in message.versions]
    active_version = message.active_version
    return MessageSchema(
        id=message.id,
        role=message.role,
        content=(
            active_version.content if active_version is not None else message.content
        ),
        metadata_json=(
            dict(active_version.metadata_json)
            if active_version is not None
            else dict(message.metadata_json or {})
        ),
        created_at=message.created_at,
        active_version_id=message.active_version_id,
        active_version_index=(
            active_version.version_index if active_version is not None else 1
        ),
        version_count=max(len(versions), 1),
        versions=versions,
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
    from app.services.deepspace.integrations.client_proxy import client_proxy_registry
    if client_proxy_registry.is_storage_connected(str(auth.tenant_id), str(auth.user_id)):
        items_data = await client_proxy_registry.db_proxy_call(
            str(auth.tenant_id), str(auth.user_id),
            "db.chats.list_conversations",
            {"limit": limit, "offset": offset, "user_id": str(auth.user_id)},
            channel="storage",
        )
        return ConversationListResponse(
            items=[ConversationSchema.model_validate(item) for item in items_data],
            total=len(items_data),
        )

    repo = ChatRepository(db)
    items = repo.list_conversations(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        limit=limit,
        offset=offset,
    )
    from app.core.config import get_settings
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    missions = MissionRegistry(get_settings(), db=db).list_missions(
        tenant_id=str(auth.tenant_id), user_id=str(auth.user_id), limit=100
    )
    by_conversation: dict[str, dict[str, Any]] = {}
    for mission in missions:
        key = str(mission.get("parent_id") or mission.get("conversation_id") or "")
        if key and key not in by_conversation:
            by_conversation[key] = mission
    serialized = []
    active_states = {"planning", "ready", "running", "awaiting_approval", "blocked", "failed", "repairing"}
    for item in items:
        payload = ConversationSchema.model_validate(item).model_dump()
        mission = by_conversation.get(str(item.id))
        if mission and str(mission.get("status") or "") in active_states:
            payload["live_status"] = str(mission["status"])
            payload["live_mission_id"] = str(mission.get("id"))
        serialized.append(ConversationSchema.model_validate(payload))
    return ConversationListResponse(
        items=serialized,
        total=len(items),
    )


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
    from app.services.deepspace.integrations.client_proxy import client_proxy_registry
    if client_proxy_registry.is_storage_connected(str(auth.tenant_id), str(auth.user_id)):
        messages_data = await client_proxy_registry.db_proxy_call(
            str(auth.tenant_id), str(auth.user_id),
            "db.chats.get_chat_history",
            {"conversation_id": str(conversation_id), "user_id": str(auth.user_id)},
            channel="storage",
        )
        # In proxy mode, messages_data is already formatted correctly as MessageSchema
        return ChatHistoryResponse(messages=[MessageSchema.model_validate(item) for item in messages_data])

    repo = ChatRepository(db)
    conversation = repo.get_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )

    messages = repo.get_messages(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    return ChatHistoryResponse(messages=[_serialize_message(item) for item in messages])


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
    repo = ChatRepository(db)
    if payload.title is None:
        raise ApiError(
            code="INVALID_REQUEST",
            message="Conversation title is required.",
            status_code=400,
        )

    updated = repo.update_conversation_title(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        title=payload.title,
    )
    if not updated:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )

    db.commit()

    conversation = repo.get_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
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
    repo = ChatRepository(db)

    deleted = repo.delete_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if not deleted:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )

    db.commit()
    return Response(status_code=204)


@router.post(
    "/bulk-delete",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def bulk_delete_conversations(
    payload: BulkDeleteRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = ChatRepository(db)
    count = repo.bulk_delete_conversations(
        tenant_id=auth.tenant_id,
        conversation_ids=payload.conversation_ids,
        user_id=auth.user_id,
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
    repo = ChatRepository(db)
    message = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    if message is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND",
            message="Message not found.",
            status_code=404,
        )
    if message.role != "assistant":
        raise ApiError(
            code="INVALID_MESSAGE_ROLE",
            message="Only assistant messages can be deleted from this route.",
            status_code=400,
        )

    repo.delete_message(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
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
    repo = ChatRepository(db)
    user_message, assistant_message = repo.get_latest_turn_pair(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if (
        user_message is None
        or assistant_message is None
        or user_message.id != message_id
    ):
        raise ApiError(
            code="MESSAGE_EDIT_NOT_ALLOWED",
            message="Only the latest user message can be edited.",
            status_code=409,
        )

    if user_message.role != "user":
        raise ApiError(
            code="INVALID_MESSAGE_ROLE",
            message="Only user messages can be edited.",
            status_code=400,
        )

    repo.create_message_version(
        tenant_id=auth.tenant_id,
        message_id=message_id,
        content=payload.content,
        metadata_json=user_message.metadata_json,
        source_type="user_edit",
        activate=True,
    )
    db.commit()

    updated = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    if updated is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND",
            message="Message not found after edit.",
            status_code=404,
        )
    return _serialize_message(updated)


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
    repo = ChatRepository(db)
    message = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    if message is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND",
            message="Message not found.",
            status_code=404,
        )
    try:
        updated = repo.activate_message_version(
            tenant_id=auth.tenant_id,
            message_id=message_id,
            version_id=version_id,
            user_id=auth.user_id,
        )
    except ValueError as exc:
        raise ApiError(
            code="MESSAGE_VERSION_NOT_FOUND",
            message=str(exc),
            status_code=404,
        ) from exc
    db.commit()
    return _serialize_message(updated)


@router.post(
    "/{conversation_id}/messages/{message_id}/regenerate/stream",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def regenerate_message_stream(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )
    payload = RegenerateRequest.model_validate(
        await request.json()
        if request.headers.get("content-length") not in (None, "0")
        else {}
    )
    _validate_top_k_bounds(top_k=payload.top_k, settings=settings)
    service = QueryService(db=db, settings=settings)

    async def event_generator() -> AsyncIterator[str]:
        async for chunk in service.regenerate_message_stream(
            auth=auth,
            conversation_id=conversation_id,
            assistant_message_id=message_id,
            top_k=payload.top_k,
            search_mode=payload.search_mode,
            document_id=payload.document_id,
            thinking_enabled=payload.thinking_enabled,
        ):
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


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
    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )
    raw_payload = await request.json()
    content = str(raw_payload.get("content", ""))
    top_k = int(raw_payload.get("top_k", 5))
    search_mode = str(raw_payload.get("search_mode", "hybrid"))
    document_id = raw_payload.get("document_id")
    thinking_enabled = bool(raw_payload.get("thinking_enabled", False))
    payload = MessageEditRequest(content=content)
    regenerate = RegenerateRequest(
        top_k=top_k,
        search_mode=search_mode,
        document_id=document_id,
        thinking_enabled=thinking_enabled,
    )
    _validate_top_k_bounds(top_k=regenerate.top_k, settings=settings)
    service = QueryService(db=db, settings=settings)

    async def event_generator() -> AsyncIterator[str]:
        async for chunk in service.edit_and_regenerate_message_stream(
            auth=auth,
            conversation_id=conversation_id,
            user_message_id=message_id,
            updated_content=payload.content,
            top_k=regenerate.top_k,
            search_mode=regenerate.search_mode,
            document_id=regenerate.document_id,
            thinking_enabled=regenerate.thinking_enabled,
        ):
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
