"""DeepSpace productivity chat, note, history, and memory endpoints."""

from __future__ import annotations

import asyncio
import json
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
from sqlalchemy import select
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
from app.auth.roles import is_admin_role
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.deepspace.repositories.request_metrics import DeepSpaceRequestMetricsRepository
from app.deepspace.schemas.chats import (
    ApprovalDecisionRequest,
    BulkDeleteRequest,
    ChatHistoryResponse,
    ConversationAppendContentRequest,
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationRetentionProtectionRequest,
    ConversationRetentionSchema,
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
    QueuedTurnSchema,
    QueueStateSchema,
    QueueTurnRequest,
    RegenerateRequest,
)
from app.deepspace.services.chat_service import DeepSpaceChatService, sse
from app.deepspace.services.context_cache import DeepSpaceContextCache
from app.deepspace.services.reasoning_privacy import (
    REASONING_REDACTION_VERSION,
    redact_reasoning_text,
)
from app.deepspace.services.run_events import (
    cancellation_key,
    channel_name,
    decode_live_event,
    event_name_from_frame,
    frames_after,
    is_terminal_event,
    latest_sequence,
    load_events,
    timeline_events,
)
from app.deepspace.services.runtime_store import DeepSpaceRuntimeStore
from app.deepspace.services.turn_queue import DeepSpaceTurnQueueStore
from app.deepspace.workers.tasks import dispatch_deepspace_turn_queue, run_deepspace_task
from app.platform.database.session import get_db, managed_db_session, set_db_tenant_context
from app.realtime.event_bus import publish_event
from app.system.models.storage_lifecycle import StorageArchiveManifest, StorageLifecycleItem
from app.system.services.cache_service import get_redis_client
from app.system.services.rate_limit_service import RateLimitService
from app.system.services.storage_lifecycle import StorageLifecycleService
from app.system.services.storage_quota import StorageQuotaExceededError

router = APIRouter(prefix="/deepspace/chats", tags=["deepspace-chats"])
logger = logging.getLogger(__name__)
CONVERSATION_KIND = "deepspace"
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _attachment_file_ids(value: Any) -> list[str]:
    """Normalize a small list of opaque Library references before queueing."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:10]:
        try:
            parsed = str(uuid.UUID(str(item)))
        except (TypeError, ValueError, AttributeError):
            raise ApiError(
                code="INVALID_ATTACHMENT",
                message="An attachment reference is invalid.",
                status_code=422,
            ) from None
        if parsed not in result:
            result.append(parsed)
    return result


async def _publish_conversation_event(
    *,
    auth: AuthContext,
    event_type: str,
    conversation_id: uuid.UUID,
    data: dict[str, Any] | None = None,
) -> None:
    """Best-effort realtime notification; REST remains authoritative."""
    try:
        await publish_event(
            get_settings(),
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            event_type=event_type,
            resource="conversations",
            data={"conversation_id": str(conversation_id), **(data or {})},
        )
    except Exception:  # noqa: BLE001
        logger.warning("Failed to publish conversation realtime event", exc_info=True)


@router.get(
    "/operational-summary",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def operational_summary(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Tenant/user-scoped, redacted provider latency and failure summary."""
    return DeepSpaceRequestMetricsRepository(db).summary(
        tenant_id=auth.tenant_id, user_id=auth.user_id
    )


def _safe_history_metadata(value: Any) -> dict[str, Any]:
    """Never return legacy raw reasoning from a history/reload response."""
    metadata = dict(value or {})
    thinking = metadata.get("thinking")
    if not isinstance(thinking, dict):
        return metadata
    if metadata.get("thinking_redaction_version") != REASONING_REDACTION_VERSION:
        metadata.pop("thinking", None)
        return metadata
    metadata["thinking"] = {
        **thinking,
        "content": redact_reasoning_text(str(thinking.get("content") or "")),
    }
    return metadata


def _serialize_message(message: Any) -> MessageSchema:
    versions = [
        MessageVersionSchema.model_validate(item).model_copy(
            update={"metadata_json": _safe_history_metadata(item.metadata_json)}
        )
        for item in message.versions
    ]
    active_version = message.active_version
    return MessageSchema(
        id=message.id,
        role=message.role,
        content=(active_version.content if active_version is not None else message.content),
        metadata_json=_safe_history_metadata(
            active_version.metadata_json if active_version is not None else message.metadata_json
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
    ticket = str(websocket.query_params.get("ticket") or "").strip()
    if ticket:
        raw = None
        try:
            redis_client = get_redis_client()
            key = f"collection_ws_ticket:{ticket}"
            raw = redis_client.get(key)
            if raw is not None:
                redis_client.delete(key)
        except Exception:  # noqa: BLE001
            logger.warning("Collection WebSocket ticket lookup failed", exc_info=True)
        if raw is None:
            raise ApiError(
                code="AUTH_REQUIRED",
                message="The WebSocket ticket is invalid or expired.",
                status_code=401,
            )
        try:
            payload = json.loads(raw)
            return AuthContext(
                user_id=uuid.UUID(str(payload["user_id"])),
                tenant_id=uuid.UUID(str(payload["tenant_id"])),
                roles=frozenset(str(role) for role in payload.get("roles", [])),
                permissions=frozenset(
                    str(permission) for permission in payload.get("permissions", [])
                ),
                token_id=str(payload.get("token_id") or "collection-ws-ticket"),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ApiError(
                code="AUTH_REQUIRED",
                message="The WebSocket ticket is invalid.",
                status_code=401,
            ) from exc
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
    include_archived: bool = False,
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
                "include_archived": include_archived,
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
        include_archived=include_archived,
    )
    return ConversationListResponse(
        items=[ConversationSchema.model_validate(item) for item in items],
        total=len(items),
    )


@router.get(
    "/archived",
    response_model=ConversationListResponse,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def list_archived_conversations(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationListResponse:
    """List archived DeepSpace conversations without exposing other sources."""
    repo = DeepSpaceChatRepository(db)
    items = repo.list_archived_conversations(
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


def _conversation_retention_item(
    db: Session, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> StorageLifecycleItem | None:
    return db.execute(
        select(StorageLifecycleItem).where(
            StorageLifecycleItem.tenant_id == tenant_id,
            StorageLifecycleItem.category == "chat_history",
            StorageLifecycleItem.source_type == "conversation",
            StorageLifecycleItem.source_id == str(conversation_id),
        )
    ).scalar_one_or_none()


def _conversation_retention_response(
    item: StorageLifecycleItem, *, restored_at: object | None = None
) -> ConversationRetentionSchema:
    # The caller may supply the restored timestamp through the item only when
    # needed; the archive manifest is queried by the route for full fidelity.
    return ConversationRetentionSchema(
        conversation_id=uuid.UUID(item.source_id),
        state=item.state,
        archived_at=item.archived_at,
        restored_at=restored_at if hasattr(restored_at, "isoformat") else None,
        pinned=bool(item.pinned),
        legal_hold=bool(item.legal_hold),
        admin_exempt=bool(item.admin_exempt),
        protection_reason=item.protection_reason,
    )


@router.get(
    "/retention/{conversation_id}",
    response_model=ConversationRetentionSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_conversation_retention(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ConversationRetentionSchema:
    repo = DeepSpaceChatRepository(db)
    if (
        repo.get_conversation(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
        is None
    ):
        raise ApiError(
            code="NOT_FOUND", message="DeepSpace conversation not found.", status_code=404
        )
    item = _conversation_retention_item(
        db, tenant_id=auth.tenant_id, conversation_id=conversation_id
    )
    if item is None:
        raise ApiError(
            code="NOT_FOUND", message="Retention state is not available.", status_code=404
        )
    manifest = db.execute(
        select(StorageArchiveManifest).where(
            StorageArchiveManifest.tenant_id == auth.tenant_id,
            StorageArchiveManifest.lifecycle_item_id == item.id,
        )
    ).scalar_one_or_none()
    return _conversation_retention_response(
        item, restored_at=manifest.restored_at if manifest else None
    )


@router.post(
    "/{conversation_id}/restore",
    response_model=ConversationRetentionSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def restore_conversation(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ConversationRetentionSchema:
    repo = DeepSpaceChatRepository(db)
    if (
        repo.get_conversation(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
        is None
    ):
        raise ApiError(
            code="NOT_FOUND", message="DeepSpace conversation not found.", status_code=404
        )
    item = _conversation_retention_item(
        db, tenant_id=auth.tenant_id, conversation_id=conversation_id
    )
    if item is None:
        raise ApiError(
            code="NOT_FOUND", message="Archived conversation was not found.", status_code=404
        )
    try:
        manifest = StorageLifecycleService(db).restore_item(
            tenant_id=auth.tenant_id,
            item_id=item.id,
            user_id=auth.user_id,
            is_admin=is_admin_role(auth.roles),
        )
        db.commit()
        return _conversation_retention_response(item, restored_at=manifest.restored_at)
    except ValueError as exc:
        db.rollback()
        raise ApiError(code="INVALID_REQUEST", message=str(exc), status_code=422) from exc


@router.patch(
    "/{conversation_id}/retention/protection",
    response_model=ConversationRetentionSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def update_conversation_retention_protection(
    conversation_id: uuid.UUID,
    payload: ConversationRetentionProtectionRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ConversationRetentionSchema:
    repo = DeepSpaceChatRepository(db)
    if (
        repo.get_conversation(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
        is None
    ):
        raise ApiError(
            code="NOT_FOUND", message="DeepSpace conversation not found.", status_code=404
        )
    if (payload.legal_hold is not None or payload.admin_exempt is not None) and not is_admin_role(
        auth.roles
    ):
        raise ApiError(
            code="FORBIDDEN",
            message="Only tenant admins can change legal holds or exemptions.",
            status_code=403,
        )
    item = _conversation_retention_item(
        db, tenant_id=auth.tenant_id, conversation_id=conversation_id
    )
    if item is None:
        raise ApiError(
            code="NOT_FOUND", message="Retention state is not available.", status_code=404
        )
    try:
        item = StorageLifecycleService(db).set_source_protection(
            tenant_id=auth.tenant_id,
            category="chat_history",
            source_type="conversation",
            source_id=str(conversation_id),
            pinned=payload.pinned,
            legal_hold=payload.legal_hold,
            admin_exempt=payload.admin_exempt,
            reason=payload.reason,
        )
        db.commit()
        return _conversation_retention_response(item)
    except ValueError as exc:
        db.rollback()
        raise ApiError(code="INVALID_REQUEST", message=str(exc), status_code=422) from exc


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
        result = ConversationSchema.model_validate(conversation)
        await _publish_conversation_event(
            auth=auth, event_type="conversation.created", conversation_id=conversation_id
        )
        return result

    repo = DeepSpaceChatRepository(db)
    conversation = repo.create_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
        title=data.title,
        content_html=data.content_html,
    )
    db.commit()
    result = ConversationSchema.model_validate(conversation)
    await _publish_conversation_event(
        auth=auth, event_type="conversation.created", conversation_id=conversation.id
    )
    return result


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

    proxied_messages: list[MessageSchema] | None = None
    if client_proxy_registry.is_storage_connected(str(auth.tenant_id), str(auth.user_id)):
        try:
            data = await client_proxy_registry.db_proxy_call(
                str(auth.tenant_id),
                str(auth.user_id),
                "db.chats.get_chat_history",
                {"conversation_id": str(conversation_id), "user_id": str(auth.user_id)},
                channel="storage",
            )
            proxied_messages = []
            for item in data:
                message = MessageSchema.model_validate(item)
                proxied_messages.append(
                    message.model_copy(
                        update={
                            "metadata_json": _safe_history_metadata(message.metadata_json),
                            "versions": [
                                version.model_copy(
                                    update={
                                        "metadata_json": _safe_history_metadata(
                                            version.metadata_json
                                        )
                                    }
                                )
                                for version in message.versions
                            ],
                        }
                    )
                )
        except Exception:  # noqa: BLE001
            # A suspended browser-side storage proxy must not hide the
            # server's durable chat history. Fall through to PostgreSQL,
            # which also contains the run/event journal used for reconnect.
            logger.warning(
                "DeepSpace storage proxy history read failed; using server history",
                exc_info=True,
            )

    # A connected proxy can be alive but briefly return an empty snapshot while
    # the server-side worker has already persisted the turn. Prefer the local
    # durable snapshot in that case when the conversation exists here.
    if proxied_messages == []:
        local_repo = DeepSpaceChatRepository(db)
        if (
            local_repo.get_conversation(
                tenant_id=auth.tenant_id,
                conversation_id=conversation_id,
                user_id=auth.user_id,
                kind=CONVERSATION_KIND,
            )
            is not None
        ):
            proxied_messages = None

    if proxied_messages is None:
        repo = DeepSpaceChatRepository(db)
        conversation = repo.get_conversation(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
        if conversation is None:
            raise ApiError(
                code="CONVERSATION_NOT_FOUND",
                message="Conversation not found",
                status_code=404,
            )
        messages = repo.get_messages(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
    else:
        messages = None
    runtime = DeepSpaceRuntimeStore(db)
    serialized_messages = proxied_messages or []
    if messages is not None:
        serialized_messages = [_serialize_message(item) for item in messages]
    elif proxied_messages is not None:
        # The browser storage proxy can be briefly stale while the worker has
        # already committed its assistant row and event journal. Merge the
        # server copy into the proxy snapshot before enrichment so a reload
        # cannot hide a completed thought timeline behind an older local row.
        try:
            server_repo = DeepSpaceChatRepository(db)
            server_conversation = server_repo.get_conversation(
                tenant_id=auth.tenant_id,
                conversation_id=conversation_id,
                user_id=auth.user_id,
                kind=CONVERSATION_KIND,
            )
            if server_conversation is not None:
                server_messages = [
                    _serialize_message(item)
                    for item in server_repo.get_messages(
                        tenant_id=auth.tenant_id,
                        conversation_id=conversation_id,
                        user_id=auth.user_id,
                        kind=CONVERSATION_KIND,
                    )
                ]
                server_by_id = {str(item.id): item for item in server_messages}
                merged: list[MessageSchema] = []
                for proxy_message in proxied_messages:
                    durable = server_by_id.pop(str(proxy_message.id), None)
                    if durable is None:
                        merged.append(proxy_message)
                        continue
                    # Keep client-owned text/versions when present, but let
                    # the server win for durable assistant metadata and any
                    # content that the proxy has not received yet.
                    merged.append(
                        proxy_message.model_copy(
                            update={
                                "content": (
                                    durable.content
                                    if durable.role == "assistant" and durable.content.strip()
                                    else proxy_message.content
                                ),
                                "metadata_json": {
                                    **(proxy_message.metadata_json or {}),
                                    **(durable.metadata_json or {}),
                                },
                                "versions": proxy_message.versions or durable.versions,
                                "active_version_id": proxy_message.active_version_id
                                or durable.active_version_id,
                                "active_version_index": proxy_message.active_version_index
                                or durable.active_version_index,
                                "version_count": proxy_message.version_count
                                or durable.version_count,
                            }
                        )
                    )
                merged.extend(server_by_id.values())
                serialized_messages = sorted(
                    merged,
                    key=lambda item: (str(item.created_at), str(item.id)),
                )
        except Exception:  # noqa: BLE001
            # A proxy-backed conversation may intentionally not exist in the
            # server database. Its local snapshot remains a valid fallback.
            logger.debug("DeepSpace durable history merge skipped", exc_info=True)
    for serialized in serialized_messages:
        if serialized.role == "assistant":
            try:
                assistant_message_id = uuid.UUID(str(serialized.id))
            except (TypeError, ValueError):
                # A malformed proxy record must not prevent the rest of the
                # conversation from loading.
                continue
            live_run = runtime.live_worker_run_for_message(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
            )
            if serialized.metadata_json.get("status") == "streaming":
                serialized.metadata_json = {
                    **serialized.metadata_json,
                    "runtime_active": live_run is not None,
                }
                if live_run is None:
                    serialized.metadata_json["status"] = "ready"
                    serialized.metadata_json["runtime_state"] = "expired"
            durable_steps = runtime.history_steps_for_message(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
            )
            if durable_steps:
                serialized.metadata_json = {
                    **serialized.metadata_json,
                    "agent_steps": durable_steps,
                }
            request_ids = [
                str(serialized.metadata_json.get("client_request_id") or "").strip(),
                str(serialized.metadata_json.get("retry_of_request_id") or "").strip(),
            ]
            request_ids = list(
                dict.fromkeys(request_id for request_id in request_ids if request_id)
            )
            if request_ids:
                durable_events = []
                for request_id in request_ids:
                    durable_events.extend(
                        load_events(
                            db,
                            tenant_id=auth.tenant_id,
                            user_id=auth.user_id,
                            conversation_id=conversation_id,
                            client_request_id=request_id,
                        )
                    )
                ordered_events = timeline_events(
                    sorted(durable_events, key=lambda event: event.created_at)
                )
                if ordered_events:
                    serialized.metadata_json = {
                        **serialized.metadata_json,
                        "timeline_events": ordered_events,
                    }
        # The list is already populated for both the proxy and PostgreSQL
        # paths; this loop only enriches each message in place.
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
            code="INVALID_REQUEST",
            message="A title or note body is required.",
            status_code=400,
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
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
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
    result = ConversationSchema.model_validate(conversation)
    await _publish_conversation_event(
        auth=auth, event_type="conversation.updated", conversation_id=conversation_id
    )
    return result


@router.post(
    "/{conversation_id}/append-content",
    response_model=ConversationSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def append_conversation_content(
    conversation_id: uuid.UUID,
    payload: ConversationAppendContentRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ConversationSchema:
    """Append document text to the current user's active DeepSpace note."""
    repo = DeepSpaceChatRepository(db)
    conversation = repo.append_conversation_content(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        content_html=payload.content_html,
        title=payload.title,
        kind=CONVERSATION_KIND,
    )
    if conversation is None:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )
    db.commit()
    result = ConversationSchema.model_validate(conversation)
    await _publish_conversation_event(
        auth=auth, event_type="conversation.updated", conversation_id=conversation_id
    )
    return result


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
    conversation = repo.get_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
        for_update=True,
    )
    if conversation is None:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )

    DeepSpaceRuntimeStore(db).request_cancel(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        commit=False,
    )
    DeepSpaceTurnQueueStore(db).cancel_all_for_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        commit=False,
    )
    DeepSpaceContextCache().invalidate_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if not repo.delete_conversation(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    ):
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )
    db.commit()
    await _publish_conversation_event(
        auth=auth, event_type="conversation.deleted", conversation_id=conversation_id
    )
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
    if request_id:
        cancelled = (
            DeepSpaceTurnQueueStore(db).request_cancel(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                client_request_id=request_id,
            )
            or cancelled
        )
    if cancelled:
        # This is harmless while a worker is still running (the active-run
        # guard prevents a second claim), but it is required when cancellation
        # releases a paused approval/question turn whose worker already ended.
        dispatch_deepspace_turn_queue.apply_async(
            kwargs={
                "tenant_id": str(auth.tenant_id),
                "user_id": str(auth.user_id),
                "conversation_id": str(conversation_id),
            }
        )
    return Response(
        status_code=204,
        headers={"X-DeepSpace-Cancel-Requested": "1" if cancelled else "0"},
    )


@router.post(
    "/queued/{client_request_id}/cancel",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def cancel_queued_deepspace_run(
    client_request_id: str,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
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
    queue_store = DeepSpaceTurnQueueStore(db)
    conversation_id = queue_store.conversation_id_for_request_id(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        client_request_id=client_request_id,
    )
    cancelled = queue_store.request_cancel_by_request_id(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        client_request_id=client_request_id,
    )
    if cancelled and conversation_id is not None:
        dispatch_deepspace_turn_queue.apply_async(
            kwargs={
                "tenant_id": str(auth.tenant_id),
                "user_id": str(auth.user_id),
                "conversation_id": str(conversation_id),
            }
        )
    return Response(
        status_code=204,
        headers={"X-DeepSpace-Cancel-Requested": "1" if cancelled else "0"},
    )


@router.get(
    "/{conversation_id}/queue/state",
    response_model=QueueStateSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
def get_deepspace_queue_state(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> QueueStateSchema:
    repo = DeepSpaceChatRepository(db)
    if (
        repo.get_conversation(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            kind=CONVERSATION_KIND,
        )
        is None
    ):
        raise ApiError(
            code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404
        )
    state = DeepSpaceTurnQueueStore(db).state(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    return QueueStateSchema(
        paused=state.paused,
        reason=state.reason,
        failed_request_id=state.failed_request_id,
        paused_at=state.paused_at,
    )


@router.post(
    "/{conversation_id}/queue/pause",
    response_model=QueueStateSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def pause_deepspace_queue(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> QueueStateSchema:
    queue_store = DeepSpaceTurnQueueStore(db)
    queue_store.pause(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    active_request_id = queue_store.active_request_id(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if active_request_id:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.set(
                cancellation_key(auth.tenant_id, auth.user_id, active_request_id),
                "1",
                ex=60 * 60 * 24,
            )
        finally:
            await client.close()
        DeepSpaceRuntimeStore(db).request_cancel(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
        )
        queue_store.request_cancel(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            client_request_id=active_request_id,
        )
    state = queue_store.state(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    return QueueStateSchema(
        paused=state.paused,
        reason=state.reason,
        failed_request_id=state.failed_request_id,
        paused_at=state.paused_at,
    )


@router.post(
    "/{conversation_id}/queue/resume",
    response_model=QueueStateSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
def resume_deepspace_queue(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> QueueStateSchema:
    queue_store = DeepSpaceTurnQueueStore(db)
    resumed_request_id: str | None = None
    previous_state = queue_store.state(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if previous_state.paused and previous_state.failed_request_id:
        try:
            retry = queue_store.retry_failed(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                failed_request_id=previous_state.failed_request_id,
            )
            resumed_request_id = retry.client_request_id
        except StorageQuotaExceededError as exc:
            raise ApiError(
                code="STORAGE_QUOTA_EXCEEDED",
                message="Your workspace storage limit has been reached.",
                status_code=413,
                details={
                    "plan": exc.plan.id,
                    "storage_limit_bytes": exc.plan.storage_limit_bytes,
                    "usage_bytes": exc.usage_bytes,
                    "requested_bytes": exc.requested_bytes,
                },
            ) from exc
        except ValueError as exc:
            raise ApiError(
                code="RETRY_CHECKPOINT_NOT_FOUND", message=str(exc), status_code=409
            ) from exc
        except OverflowError as exc:
            raise ApiError(code="DEEPSPACE_QUEUE_FULL", message=str(exc), status_code=409) from exc
    state = queue_store.resume(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    dispatch_deepspace_turn_queue.apply_async(
        kwargs={
            "tenant_id": str(auth.tenant_id),
            "user_id": str(auth.user_id),
            "conversation_id": str(conversation_id),
        }
    )
    return QueueStateSchema(
        paused=state.paused,
        reason=state.reason,
        failed_request_id=state.failed_request_id,
        active_request_id=resumed_request_id,
        paused_at=state.paused_at,
    )


@router.get(
    "/{conversation_id}/queue",
    response_model=list[QueuedTurnSchema],
    dependencies=[Depends(require_permissions("queries:run"))],
)
def list_deepspace_turn_queue(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[QueuedTurnSchema]:
    repo = DeepSpaceChatRepository(db)
    if (
        repo.get_conversation(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            kind=CONVERSATION_KIND,
        )
        is None
    ):
        raise ApiError(
            code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404
        )
    queue_store = DeepSpaceTurnQueueStore(db)
    recovered = queue_store.recover_stale_claims(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if (
        recovered
        and not queue_store.state(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
        ).paused
    ):
        try:
            dispatch_deepspace_turn_queue.apply_async(
                kwargs={
                    "tenant_id": str(auth.tenant_id),
                    "user_id": str(auth.user_id),
                    "conversation_id": str(conversation_id),
                }
            )
        except Exception:  # noqa: BLE001
            # The next durable queue poll can retry dispatch. Never hide the
            # recovered queue rows just because the broker is temporarily down.
            logger.exception("Failed to redispatch a recovered DeepSpace queue")
    return [
        QueuedTurnSchema.model_validate(turn)
        for turn in queue_store.list_open(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
        )
    ]


@router.post(
    "/{conversation_id}/queue/clear",
    response_model=QueueStateSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def clear_deepspace_queue(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> QueueStateSchema:
    """Clear pending queue work without deleting conversation messages.

    A currently running turn receives the normal cancellation signal; queued,
    paused, failed, and retry-checkpoint rows are retained as audit history but
    become terminal and disappear from the visible queue.
    """
    repo = DeepSpaceChatRepository(db)
    if (
        repo.get_conversation(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            kind=CONVERSATION_KIND,
        )
        is None
    ):
        raise ApiError(
            code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404
        )

    queue_store = DeepSpaceTurnQueueStore(db)
    active_request_id = queue_store.active_request_id(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if active_request_id:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.set(
                cancellation_key(auth.tenant_id, auth.user_id, active_request_id),
                "1",
                ex=60 * 60 * 24,
            )
        finally:
            await client.close()
        DeepSpaceRuntimeStore(db).request_cancel(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            commit=False,
        )

    queue_store.clear_for_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    if active_request_id:
        dispatch_deepspace_turn_queue.apply_async(
            kwargs={
                "tenant_id": str(auth.tenant_id),
                "user_id": str(auth.user_id),
                "conversation_id": str(conversation_id),
            }
        )
    state = queue_store.state(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    )
    return QueueStateSchema(
        paused=state.paused,
        reason=state.reason,
        failed_request_id=state.failed_request_id,
        paused_at=state.paused_at,
    )


@router.post(
    "/{conversation_id}/queue",
    response_model=QueuedTurnSchema,
    status_code=202,
    dependencies=[Depends(require_permissions("queries:run"))],
)
def enqueue_deepspace_turn(
    conversation_id: uuid.UUID,
    payload: QueueTurnRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QueuedTurnSchema:
    RateLimitService(settings).enforce_deepspace_user_limit(
        request=request, user_id=str(auth.user_id)
    )
    request_id = str(payload.client_request_id or "").strip() or str(uuid.uuid4())
    try:
        turn = DeepSpaceTurnQueueStore(db).enqueue(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            client_request_id=request_id,
            prompt=payload.message,
            thinking_enabled=payload.thinking_enabled,
            reasoning_effort=payload.reasoning_effort,
            roles=sorted(auth.roles),
            permissions=sorted(auth.permissions),
            steer=payload.steer,
            attachment_file_ids=[str(file_id) for file_id in payload.attachment_file_ids],
        )
    except StorageQuotaExceededError as exc:
        raise ApiError(
            code="STORAGE_QUOTA_EXCEEDED",
            message="Your workspace storage limit has been reached.",
            status_code=413,
            details={
                "plan": exc.plan.id,
                "storage_limit_bytes": exc.plan.storage_limit_bytes,
                "usage_bytes": exc.usage_bytes,
                "requested_bytes": exc.requested_bytes,
            },
        ) from exc
    except ValueError as exc:
        raise ApiError(code="CONVERSATION_NOT_FOUND", message=str(exc), status_code=404) from exc
    except OverflowError as exc:
        raise ApiError(code="DEEPSPACE_QUEUE_FULL", message=str(exc), status_code=409) from exc
    dispatch_deepspace_turn_queue.apply_async(
        kwargs={
            "tenant_id": str(auth.tenant_id),
            "user_id": str(auth.user_id),
            "conversation_id": str(conversation_id),
        }
    )
    return QueuedTurnSchema.model_validate(turn)


@router.post(
    "/{conversation_id}/queue/{client_request_id}/steer",
    response_model=QueuedTurnSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
def steer_deepspace_queued_turn(
    conversation_id: uuid.UUID,
    client_request_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> QueuedTurnSchema:
    turn = DeepSpaceTurnQueueStore(db).promote(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
    )
    if turn is None:
        raise ApiError(
            code="QUEUE_TURN_NOT_FOUND", message="Queued message not found.", status_code=404
        )
    queue_store = DeepSpaceTurnQueueStore(db)
    if queue_store.state(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    ).paused:
        queue_store.resume(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
        )
        dispatch_deepspace_turn_queue.apply_async(
            kwargs={
                "tenant_id": str(auth.tenant_id),
                "user_id": str(auth.user_id),
                "conversation_id": str(conversation_id),
            }
        )
    return QueuedTurnSchema.model_validate(turn)


@router.post(
    "/{conversation_id}/queue/{client_request_id}/retry",
    response_model=QueuedTurnSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
def retry_deepspace_failed_turn(
    conversation_id: uuid.UUID,
    client_request_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> QueuedTurnSchema:
    queue_store = DeepSpaceTurnQueueStore(db)
    try:
        turn = queue_store.retry_failed(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            failed_request_id=client_request_id,
        )
    except StorageQuotaExceededError as exc:
        raise ApiError(
            code="STORAGE_QUOTA_EXCEEDED",
            message="Your workspace storage limit has been reached.",
            status_code=413,
            details={
                "plan": exc.plan.id,
                "storage_limit_bytes": exc.plan.storage_limit_bytes,
                "usage_bytes": exc.usage_bytes,
                "requested_bytes": exc.requested_bytes,
            },
        ) from exc
    except ValueError as exc:
        raise ApiError(code="QUEUE_TURN_NOT_FOUND", message=str(exc), status_code=404) from exc
    except OverflowError as exc:
        raise ApiError(code="DEEPSPACE_QUEUE_FULL", message=str(exc), status_code=409) from exc
    if queue_store.state(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
    ).paused:
        queue_store.resume(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
        )
    dispatch_deepspace_turn_queue.apply_async(
        kwargs={
            "tenant_id": str(auth.tenant_id),
            "user_id": str(auth.user_id),
            "conversation_id": str(conversation_id),
        }
    )
    return QueuedTurnSchema.model_validate(turn)


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
            code="APPROVAL_NOT_FOUND",
            message="Approval request not found.",
            status_code=404,
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
    runtime_store = DeepSpaceRuntimeStore(db)
    queue_store = DeepSpaceTurnQueueStore(db)
    for cid in payload.conversation_ids:
        runtime_store.request_cancel(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=cid,
            commit=False,
        )
        queue_store.cancel_all_for_conversation(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=cid,
            commit=False,
        )
    repo = DeepSpaceChatRepository(db)
    count = repo.bulk_delete_conversations(
        tenant_id=auth.tenant_id,
        conversation_ids=payload.conversation_ids,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    db.commit()
    for conversation_id in payload.conversation_ids:
        await _publish_conversation_event(
            auth=auth, event_type="conversation.deleted", conversation_id=conversation_id
        )
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
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    raw_payload = await request.json()
    prompt = str(raw_payload.get("message", ""))
    conversation_id_raw = raw_payload.get("conversation_id")
    conversation_id = uuid.UUID(str(conversation_id_raw)) if conversation_id_raw else None
    resume_approval_id = str(raw_payload.get("resume_approval_id") or "").strip() or None
    resume_user_question_id = str(raw_payload.get("resume_user_question_id") or "").strip() or None
    if not prompt.strip() and not resume_approval_id and not resume_user_question_id:

        async def empty_stream() -> AsyncIterator[str]:
            yield sse(
                "error",
                {"code": "EMPTY_MESSAGE", "message": "Message cannot be empty."},
            )

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
    run_now = bool(raw_payload.get("run_now", False))
    reasoning_effort = str(raw_payload.get("reasoning_effort") or "").strip().lower() or None
    if reasoning_effort not in {"low", "medium", "high", "very_high", "extreme_high"}:
        reasoning_effort = None
    if run_now and conversation_id is not None:
        with managed_db_session() as run_now_db:
            set_db_tenant_context(run_now_db, auth.tenant_id)
            queue_store = DeepSpaceTurnQueueStore(run_now_db)
            queue_state = queue_store.state(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
            if not queue_state.paused:
                raise ApiError(
                    code="DEEPSPACE_QUEUE_NOT_PAUSED",
                    message="Run-now chat is available only while the queue is paused.",
                    status_code=409,
                )
            if queue_store.active_request_id(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            ):
                raise ApiError(
                    code="DEEPSPACE_QUEUE_STILL_RUNNING",
                    message="Wait for the active queued turn to stop before running a separate chat.",
                    status_code=409,
                )
    # Clarification answers are claimed synchronously, before a worker is
    # scheduled.  This is the ownership boundary: exactly one request may
    # advance an awaiting question; retries merely attach to that same run.
    question_claimed = False
    if not reconnect and not resume_approval_id and not resume_user_question_id:
        RateLimitService(settings).enforce_deepspace_user_limit(
            request=request,
            user_id=str(auth.user_id),
        )
        if conversation_id is not None:
            try:
                with managed_db_session() as queue_db:
                    set_db_tenant_context(queue_db, auth.tenant_id)
                    queue_store = DeepSpaceTurnQueueStore(queue_db)
                    queue_store.enqueue(
                        tenant_id=auth.tenant_id,
                        user_id=auth.user_id,
                        conversation_id=conversation_id,
                        client_request_id=client_request_id,
                        prompt=prompt,
                        thinking_enabled=thinking_enabled,
                        reasoning_effort=reasoning_effort,
                        roles=sorted(auth.roles),
                        permissions=sorted(auth.permissions),
                        attachment_file_ids=_attachment_file_ids(
                            raw_payload.get("attachment_file_ids")
                        ),
                    )
            except StorageQuotaExceededError as exc:
                raise ApiError(
                    code="STORAGE_QUOTA_EXCEEDED",
                    message="Your workspace storage limit has been reached.",
                    status_code=413,
                    details={
                        "plan": exc.plan.id,
                        "storage_limit_bytes": exc.plan.storage_limit_bytes,
                        "usage_bytes": exc.usage_bytes,
                        "requested_bytes": exc.requested_bytes,
                    },
                ) from exc
            except ValueError as exc:
                raise ApiError(
                    code="CONVERSATION_NOT_FOUND", message=str(exc), status_code=404
                ) from exc
            except OverflowError as exc:
                raise ApiError(
                    code="DEEPSPACE_QUEUE_FULL", message=str(exc), status_code=409
                ) from exc
    elif conversation_id is not None and resume_user_question_id:
        with managed_db_session() as resume_db:
            set_db_tenant_context(resume_db, auth.tenant_id)
            runtime = DeepSpaceRuntimeStore(resume_db)
            claim = runtime.claim_user_question(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                question_id=resume_user_question_id,
                answer=prompt,
            )
            if claim is None:
                # A stale card must never create another worker or show a
                # provider failure. The browser will refresh durable history.
                active_request_id = DeepSpaceTurnQueueStore(resume_db).active_request_id(
                    tenant_id=auth.tenant_id,
                    user_id=auth.user_id,
                    conversation_id=conversation_id,
                )
                if active_request_id:
                    client_request_id = active_request_id
            elif claim.claimed:
                DeepSpaceChatRepository(resume_db).add_message(
                    tenant_id=auth.tenant_id,
                    conversation_id=conversation_id,
                    role="user",
                    content=prompt,
                    metadata_json={
                        "answer_to_question_id": resume_user_question_id,
                        "client_request_id": client_request_id,
                    },
                )
                resumed_request_id = DeepSpaceTurnQueueStore(resume_db).resume_paused(
                    tenant_id=auth.tenant_id,
                    user_id=auth.user_id,
                    conversation_id=conversation_id,
                    commit=False,
                )
                if resumed_request_id:
                    client_request_id = resumed_request_id
                    # A paused run deliberately keeps its request id. Start
                    # this new browser subscription after the old terminal
                    # `awaiting_user` frame; replaying it would immediately
                    # close the SSE reader before continuation events arrive.
                    after_sequence = max(
                        after_sequence,
                        latest_sequence(
                            resume_db,
                            tenant_id=auth.tenant_id,
                            user_id=auth.user_id,
                            conversation_id=conversation_id,
                            client_request_id=client_request_id,
                        ),
                    )
                question_claimed = True
                resume_db.commit()
            else:
                active_request_id = DeepSpaceTurnQueueStore(resume_db).active_request_id(
                    tenant_id=auth.tenant_id,
                    user_id=auth.user_id,
                    conversation_id=conversation_id,
                )
                if active_request_id:
                    client_request_id = active_request_id
    elif conversation_id is not None and resume_approval_id:
        # Keep the paused turn's stream key and queue slot when a user answers
        # a clarification or approves an action.  A new id would leave the
        # original paused record active forever and block following messages.
        with managed_db_session() as queue_db:
            set_db_tenant_context(queue_db, auth.tenant_id)
            resumed_request_id = DeepSpaceTurnQueueStore(queue_db).resume_paused(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
            if resumed_request_id:
                client_request_id = resumed_request_id
                # See the clarification-resume cursor above. Approval
                # continuations use the same durable stream and must not
                # replay their old terminal pause event into a new live
                # subscription.
                after_sequence = max(
                    after_sequence,
                    latest_sequence(
                        queue_db,
                        tenant_id=auth.tenant_id,
                        user_id=auth.user_id,
                        conversation_id=conversation_id,
                        client_request_id=client_request_id,
                    ),
                )

    async def iterator() -> AsyncIterator[str]:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        last_sequence = after_sequence
        try:
            await pubsub.subscribe(channel_name(client_request_id))
            if not reconnect:
                try:
                    if (
                        conversation_id is not None
                        and not run_now
                        and not resume_approval_id
                        and not resume_user_question_id
                    ):
                        dispatch_deepspace_turn_queue.apply_async(
                            kwargs={
                                "tenant_id": str(auth.tenant_id),
                                "user_id": str(auth.user_id),
                                "conversation_id": str(conversation_id),
                            }
                        )
                    elif resume_user_question_id and not question_claimed:
                        # The answer was already accepted by another request.
                        # Subscribe/replay its durable stream; never execute a
                        # second continuation merely to report stale state.
                        yield sse(
                            "done",
                            {
                                "conversation_id": str(conversation_id),
                                "status": "running",
                                "reconnected": True,
                            },
                        )
                        return
                    else:
                        run_deepspace_task.apply_async(
                            kwargs={
                                "tenant_id": str(auth.tenant_id),
                                "user_id": str(auth.user_id),
                                "roles": sorted(auth.roles),
                                "permissions": sorted(auth.permissions),
                                "conversation_id": (
                                    str(conversation_id) if conversation_id else None
                                ),
                                "prompt": prompt,
                                "client_request_id": client_request_id,
                                "thinking_enabled": thinking_enabled,
                                "reasoning_effort": reasoning_effort,
                                "attachment_file_ids": _attachment_file_ids(
                                    raw_payload.get("attachment_file_ids")
                                ),
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
                    # Do not keep a request-scoped database session open for
                    # the lifetime of an SSE stream. Long-running responses
                    # would otherwise reserve pool connections until the
                    # model finishes, starving history and other UI requests.
                    with managed_db_session() as replay_db:
                        stored = load_events(
                            replay_db,
                            tenant_id=auth.tenant_id,
                            user_id=auth.user_id,
                            conversation_id=conversation_id,
                            client_request_id=client_request_id,
                            after_sequence=last_sequence,
                        )
                        # Materialize plain (sequence, frame) tuples while the
                        # ORM session is still open. Accessing ORM attributes
                        # after managed_db_session() rolls back and closes the
                        # session raises DetachedInstanceError, which aborts the
                        # SSE stream with no terminal event and makes the UI
                        # report "The chat provider returned an empty stream."
                        replay_frames = frames_after(stored, after_sequence=last_sequence)
                    for sequence, frame in replay_frames:
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
            code="MESSAGE_NOT_FOUND",
            message="DeepSpace turn not found.",
            status_code=404,
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
            code="MESSAGE_NOT_FOUND",
            message="DeepSpace turn not found.",
            status_code=404,
        )
    user_message = next(
        (item for item in reversed(messages[:source_index]) if item.role == "user"),
        None,
    )
    if user_message is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND",
            message="DeepSpace source prompt not found.",
            status_code=404,
        )
    source_prompt = (
        user_message.active_version.content
        if user_message.active_version is not None
        else user_message.content
    )
    repo.create_message_version(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=auth.user_id,
        content="",
        source_type="regenerate",
        activate=True,
    )
    db.commit()
    service = DeepSpaceChatService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        async for chunk in service.stream_turn(
            auth=auth,
            conversation_id=conversation_id,
            prompt=source_prompt,
            existing_assistant_message_id=message_id,
            client_request_id=payload.client_request_id,
            thinking_enabled=payload.thinking_enabled,
            reasoning_effort=payload.reasoning_effort,
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
    client_request_id = str(raw_payload.get("client_request_id") or "").strip() or None
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
            code="MESSAGE_NOT_FOUND",
            message="DeepSpace message not found.",
            status_code=404,
        )
    latest_user, assistant = repo.get_latest_turn_pair(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
    )
    if latest_user is None or assistant is None or latest_user.id != message_id:
        raise ApiError(
            code="MESSAGE_EDIT_NOT_ALLOWED",
            message="Only the latest user message can be edited.",
            status_code=409,
        )
    repo.create_message_version(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        message_id=assistant.id,
        user_id=auth.user_id,
        content="",
        source_type="edit_regenerate",
        activate=True,
    )
    db.commit()
    service = DeepSpaceChatService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        async for chunk in service.stream_turn(
            auth=auth,
            conversation_id=conversation_id,
            prompt=content,
            existing_assistant_message_id=assistant.id,
            client_request_id=client_request_id,
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
            code="MEMORY_NOT_FOUND",
            message=f"Memory key '{key}' not found.",
            status_code=404,
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
