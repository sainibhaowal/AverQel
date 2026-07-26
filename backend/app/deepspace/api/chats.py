"""DeepSpace productivity chat, note, history, and memory endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

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
    BulkDeleteRequest,
    ChatHistoryResponse,
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationSchema,
    ConversationUpdate,
    MemoryFactSchema,
    MemoryRetentionReportSchema,
    MessageEditRequest,
    MessageSchema,
    MessageVersionSchema,
    RegenerateRequest,
)
from app.deepspace.services.chat_service import DeepSpaceChatService
from app.deepspace.services.runtime_store import DeepSpaceRuntimeStore
from app.platform.database.session import get_db

router = APIRouter(prefix="/deepspace/chats", tags=["deepspace-chats"])
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
        active_version_index=(
            active_version.version_index if active_version is not None else 1
        ),
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
            {"limit": limit, "offset": offset, "user_id": str(auth.user_id), "kind": CONVERSATION_KIND},
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
        if repo.get_conversation(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        ) is None:
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
        return ChatHistoryResponse(
            messages=[MessageSchema.model_validate(item) for item in data]
        )

    repo = DeepSpaceChatRepository(db)
    conversation = repo.get_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    if conversation is None:
        raise ApiError(code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404)
    messages = repo.get_messages(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
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
    repo = DeepSpaceChatRepository(db)
    if payload.title is None and payload.content_html is None:
        raise ApiError(code="INVALID_REQUEST", message="A title or note body is required.", status_code=400)
    updated = repo.update_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        title=payload.title,
        content_html=payload.content_html,
        kind=CONVERSATION_KIND,
    )
    if not updated:
        raise ApiError(code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404)
    db.commit()
    conversation = repo.get_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    if conversation is None:
        raise ApiError(code="CONVERSATION_NOT_FOUND", message="Conversation not found after update", status_code=404)
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
        raise ApiError(code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404)
    db.commit()
    return Response(status_code=204)


@router.post(
    "/{conversation_id}/cancel",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def cancel_deepspace_chat(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    cancelled = DeepSpaceRuntimeStore(db).request_cancel(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    return Response(status_code=204, headers={"X-DeepSpace-Cancel-Requested": "1" if cancelled else "0"})


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
        raise ApiError(code="INVALID_MESSAGE_ROLE", message="Only assistant messages can be deleted.", status_code=400)
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
        raise ApiError(code="MESSAGE_EDIT_NOT_ALLOWED", message="Only the latest user message can be edited.", status_code=409)
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
    service = DeepSpaceChatService(db=db, settings=settings)

    return StreamingResponse(
        service.stream_turn(
            auth=auth,
            conversation_id=conversation_id,
            prompt=prompt,
            thinking_enabled=bool(raw_payload.get("thinking_enabled", False)),
            request=request,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


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
    user_message, _assistant_message = repo.get_latest_turn_pair(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
    )
    if user_message is None:
        raise ApiError(code="MESSAGE_NOT_FOUND", message="DeepSpace turn not found.", status_code=404)
    service = DeepSpaceChatService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        async for chunk in service.stream_turn(
            auth=auth,
            conversation_id=conversation_id,
            prompt=user_message.content,
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
        raise ApiError(code="MESSAGE_NOT_FOUND", message="DeepSpace message not found.", status_code=404)
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

    return await MemoryService(db).list_all_memories(
        tenant_id=auth.tenant_id, user_id=auth.user_id
    )


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
        raise ApiError(code="MEMORY_NOT_FOUND", message=f"Memory key '{key}' not found.", status_code=404)
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
        "decay_half_life_days": report.get("retention_policy", {}).get("decay_half_life_days", 120.0),
    }
    report.setdefault("session_retention_days", retention_days)
    return MemoryRetentionReportSchema.model_validate(report)
