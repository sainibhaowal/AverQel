from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
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
from app.schemas.deepspace.runtime import (
    ResolveMissionApprovalRequest,
    UpdateExecutionModeRequest,
    UpdateRuntimePreferencesRequest,
)
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.auth.rbac import require_permissions, resolve_permissions
from app.db.session import get_db, set_db_tenant_context
from app.repositories.query.chat import ChatRepository
from app.schemas.query.chats import (
    BulkDeleteRequest,
    ChatHistoryResponse,
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationSchema,
    ConversationUpdate,
    MemoryFactSchema,
    MemoryLifecycleReportSchema,
    MemoryRetentionReportSchema,
    MessageEditRequest,
    MessageSchema,
    MessageVersionSchema,
    ProactiveTaskSummarySchema,
    RegenerateRequest,
    SubagentRunSchema,
    SubagentSummarySchema,
    TodoTaskCreateRequest,
    TodoTaskSchema,
    TodoTaskUpdateRequest,
)
from app.services.deepspace.orchestration.deepspace_service import DeepSpaceService
from app.services.query.answer_service import AnswerService, StreamEvent
from app.services.system.rate_limit_service import RateLimitService

router = APIRouter(prefix="/deepspace/chats", tags=["deepspace-chats"])
logger = logging.getLogger(__name__)

CONVERSATION_KIND = "deepspace"


def _durable_mission_or_404(*, registry: Any, mission_id: str, auth: AuthContext) -> dict[str, Any]:
    mission = registry.get_mission(mission_id)
    if not mission:
        raise ApiError(code="DURABLE_RUN_NOT_FOUND", message="Durable run not found.", status_code=404)
    if str(mission.get("tenant_id")) != str(auth.tenant_id) or str(mission.get("user_id")) != str(auth.user_id):
        raise ApiError(code="DURABLE_RUN_FORBIDDEN", message="Durable run access denied.", status_code=403)
    return mission


def _mission_as_durable_run(mission: dict[str, Any]) -> dict[str, Any]:
    status = str(mission.get("status") or "queued")
    status_map = {"planning": "queued", "ready": "queued", "blocked": "paused", "awaiting_approval": "awaiting_approval", "running": "running", "completed": "completed", "cancelled": "cancelled", "failed": "failed"}
    return {
        "id": str(mission.get("id")),
        "status": status_map.get(status, status),
        "objective": str(mission.get("objective") or ""),
        "current_sequence": len(mission.get("events") or []),
        "continuation_epoch": int(mission.get("continuation_count") or 0),
        "recovery_count": int(mission.get("continuation_count") or 0),
        "execution_contract": {"mode": mission.get("execution_mode") or "auto_review"},
        "budget_json": mission.get("budget") or {},
        "runtime_state": {"status": status, "last_event": mission.get("last_event_type")},
        "conversation_id": mission.get("parent_id"),
        "final_output_json": {"content": mission.get("final_output") or ""},
        "created_at": mission.get("created_at"),
        "updated_at": mission.get("updated_at"),
    }

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _stream_headers() -> dict[str, str]:
    return dict(SSE_HEADERS)

WEBSOCKET_CHAT_ROUTE_RE = re.compile(
    r"^/deepspace/chats/(?P<conversation_id>[0-9a-fA-F-]+)/messages/(?P<message_id>[0-9a-fA-F-]+)/(?:regenerate|edit-and-regenerate)/stream$"
)


def _make_rate_limit_request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace())


async def _send_websocket_sse_error(
    websocket: WebSocket,
    *,
    code: str,
    message: str,
) -> None:
    from app.services.query.answer_service import AnswerService, StreamEvent

    await websocket.send_text(
        AnswerService.encode_sse_event(
            StreamEvent(
                event="error",
                data={"code": code, "message": message},
            )
        )
    )


async def _authenticate_websocket_auth_context(
    websocket: WebSocket,
    *,
    db: Session,
    settings: Settings,
) -> AuthContext:
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
        key_hash = repo.hash_key(token)
        api_key = repo.get_by_hash(key_hash=key_hash)
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

    claims = decode_access_token(token, settings)
    return build_auth_context_from_jwt(
        claims=claims,
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


async def _stream_service_over_websocket(
    websocket: WebSocket,
    *,
    service: DeepSpaceService,
    auth: AuthContext,
    settings: Settings,
    db: Session,
    payload: dict[str, Any],
) -> None:
    from app.services.query.answer_service import AnswerService

    endpoint = str(payload.get("endpoint") or payload.get("path") or "").strip()
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    request = _make_rate_limit_request()
    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )

    async def send_sse_chunk(chunk: str) -> None:
        await websocket.send_text(chunk)

    try:
        if endpoint == "/deepspace/chats/stream":
            query_text = str(body.get("query", "")).strip()
            if not query_text:
                raise ApiError(
                    code="QUERY_VALIDATION_ERROR",
                    message="query is required.",
                    status_code=422,
                )

            conversation_id_raw = body.get("conversation_id")
            conversation_id = (
                uuid.UUID(str(conversation_id_raw)) if conversation_id_raw else None
            )
            note_content = body.get("note_content")
            thinking_enabled = bool(body.get("thinking_enabled", True))
            web_search_enabled = bool(body.get("web_search_enabled", True))
            agentic_mode = bool(body.get("agentic_mode", True))
            async for chunk in service.stream_chat(
                auth=auth,
                query_text=query_text,
                conversation_id=conversation_id,
                note_content=note_content,
                thinking_enabled=thinking_enabled,
                web_search_enabled=web_search_enabled,
                background_tasks=None,
                agentic_mode=agentic_mode,
            ):
                await send_sse_chunk(chunk)
            return

        if endpoint == "/deepspace/chats/resume":
            conversation_id_raw = body.get("conversation_id")
            conversation_id = (
                uuid.UUID(str(conversation_id_raw)) if conversation_id_raw else None
            )
            step_id = str(body.get("step_id") or "").strip()
            tool_id = body.get("tool_id")
            approved = bool(body.get("approved", True))
            if not conversation_id or not step_id:
                raise ApiError(
                    code="RESUME_VALIDATION_ERROR",
                    message="conversation_id and step_id are required.",
                    status_code=422,
                )

            async for chunk in service.resume_chat(
                auth=auth,
                conversation_id=conversation_id,
                step_id=step_id,
                tool_id=tool_id,
                approved=approved,
                background_tasks=None,
            ):
                await send_sse_chunk(chunk)
            return

        regenerate_match = WEBSOCKET_CHAT_ROUTE_RE.match(endpoint)
        if regenerate_match and "regenerate" in endpoint:
            conversation_id = uuid.UUID(regenerate_match.group("conversation_id"))
            message_id = uuid.UUID(regenerate_match.group("message_id"))
            regenerate_payload = {
                "top_k": body.get("top_k", 5),
                "search_mode": body.get("search_mode", "hybrid"),
                "document_id": body.get("document_id"),
                "thinking_enabled": body.get("thinking_enabled", False),
                "agentic_mode": body.get("agentic_mode", True),
            }
            regenerate = RegenerateRequest.model_validate(regenerate_payload)
            _validate_top_k_bounds(top_k=regenerate.top_k, settings=settings)
            async for chunk in service.regenerate_message_stream(
                auth=auth,
                conversation_id=conversation_id,
                assistant_message_id=message_id,
                thinking_enabled=regenerate.thinking_enabled,
                agentic_mode=regenerate.agentic_mode,
            ):
                await send_sse_chunk(chunk)
            return

        if regenerate_match and "edit-and-regenerate" in endpoint:
            conversation_id = uuid.UUID(regenerate_match.group("conversation_id"))
            message_id = uuid.UUID(regenerate_match.group("message_id"))
            content = str(body.get("content", ""))
            edit_request = MessageEditRequest.model_validate({"content": content})
            regenerate = RegenerateRequest.model_validate(
                {
                    "top_k": body.get("top_k", 5),
                    "search_mode": body.get("search_mode", "hybrid"),
                    "document_id": body.get("document_id"),
                    "thinking_enabled": body.get("thinking_enabled", False),
                    "agentic_mode": body.get("agentic_mode", True),
                }
            )
            _validate_top_k_bounds(top_k=regenerate.top_k, settings=settings)
            async for chunk in service.edit_and_regenerate_message_stream(
                auth=auth,
                conversation_id=conversation_id,
                user_message_id=message_id,
                updated_content=edit_request.content,
                thinking_enabled=regenerate.thinking_enabled,
                agentic_mode=regenerate.agentic_mode,
            ):
                await send_sse_chunk(chunk)
            return

        if endpoint == "/deepspace/chats/orchestrations/stream":
            from app.services.deepspace.missions.mission_registry import MissionRegistry
            from app.services.deepspace.orchestration.master_orchestrator import MasterOrchestrator
            from app.services.query.answer_service import AnswerService

            objective = str(body.get("objective") or body.get("query") or "").strip()
            if not objective:
                raise ApiError(
                    code="MISSION_VALIDATION_ERROR",
                    message="objective is required.",
                    status_code=422,
                )
            conversation_id_raw = body.get("conversation_id")
            conversation_id = (
                uuid.UUID(str(conversation_id_raw)) if conversation_id_raw else None
            )
            mission_id_raw = body.get("mission_id")
            mission_id = str(uuid.UUID(str(mission_id_raw))) if mission_id_raw else None
            note_content = body.get("note_content")
            previous_messages = body.get("previous_messages")
            if not isinstance(previous_messages, list):
                previous_messages = None
            registry = MissionRegistry(settings, db=db)
            execution_mode = registry.get_execution_mode(
                tenant_id=str(auth.tenant_id),
                user_id=str(auth.user_id),
                conversation_id=str(conversation_id) if conversation_id else None,
            )
            orchestrator = MasterOrchestrator(
                db=db,
                auth=auth,
                settings=settings,
                background_tasks=None,
            )
            async for chunk in orchestrator.stream_mission(
                objective=objective,
                note_content=note_content,
                previous_messages=previous_messages,
                conversation_id=conversation_id,
                execution_mode=execution_mode,
                mission_id=mission_id,
            ):
                await send_sse_chunk(AnswerService.encode_sse_event(chunk))
            return

        raise ApiError(
            code="WS_ENDPOINT_NOT_SUPPORTED",
            message="Unsupported websocket endpoint.",
            status_code=400,
        )
    except ApiError as exc:
        await _send_websocket_sse_error(websocket, code=exc.code, message=exc.message)
        return


def _serialize_runtime_preferences(
    *,
    registry: Any,
    tenant_id: str,
    user_id: str,
    conversation_id: str | None,
) -> dict[str, Any]:
    preferences = registry.get_runtime_preferences(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    payload = {
        "conversation_id": conversation_id,
        "execution_mode": preferences.get("execution_mode", "auto_review"),
        "planner_mode": preferences.get("planner_mode", "default"),
        "subagent_profile": preferences.get("subagent_profile", "default"),
        "runtime_hooks_enabled": preferences.get("runtime_hooks_enabled") == "true",
        "workspace_mode_enabled": preferences.get("workspace_mode_enabled") == "true",
    }
    # Preserve the legacy response shape for the default-off state. The UI
    # treats an omitted value as false; enabled conversations expose it.
    if preferences.get("full_autonomy_enabled") == "true":
        payload["full_autonomy_enabled"] = True
    return payload


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
            items=[ConversationSchema.model_validate(item) for item in items_data],
            total=len(items_data),
        )
    repo = ChatRepository(db)
    items = repo.list_conversations(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
        limit=limit,
        offset=offset,
    )
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    missions = MissionRegistry(get_settings(), db=db).list_missions(
        tenant_id=str(auth.tenant_id), user_id=str(auth.user_id), limit=100
    )
    by_conversation: dict[str, dict[str, Any]] = {}
    for mission in missions:
        conversation_key = str(mission.get("parent_id") or mission.get("conversation_id") or "")
        if conversation_key and conversation_key not in by_conversation:
            by_conversation[conversation_key] = mission
    serialized = []
    for item in items:
        payload = ConversationSchema.model_validate(item).model_dump()
        mission = by_conversation.get(str(item.id))
        if mission and str(mission.get("status") or "") in {
            "planning", "ready", "running", "awaiting_approval", "blocked", "failed", "repairing"
        }:
            payload["live_status"] = str(mission.get("status"))
            payload["live_mission_id"] = str(mission.get("id"))
        serialized.append(ConversationSchema.model_validate(payload))
    return ConversationListResponse(
        items=serialized,
        total=len(items),
    )


@router.get("/activity", response_model=list[dict[str, Any]])
async def get_agent_activity(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    limit: int = 10,
):
    from app.models.deepspace.agent_activity import AgentActivity

    activities = (
        db.query(AgentActivity)
        .filter(AgentActivity.tenant_id == auth.tenant_id)
        .order_by(AgentActivity.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": str(a.id),
            "type": a.activity_type,
            "description": a.description,
            "source": a.source,
            "created_at": a.created_at.isoformat(),
            "metadata": a.metadata_json,
        }
        for a in activities
    ]


@router.get("/vitals", response_model=dict[str, Any])
async def get_system_vitals(
    auth: AuthContext = Depends(get_auth_context),
):
    from app.services.system.vitals_service import VitalsService

    return await VitalsService.get_system_vitals(auth.tenant_id)


@router.get("/runtime", response_model=dict[str, Any])
async def get_deepspace_runtime(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    from app.services.deepspace.execution.agent_executor import AgentExecutor
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    try:
        executor = AgentExecutor(db=db, auth=auth, settings=settings)
        return {
            "model_name": executor.model_name,
            "provider_type": executor.provider_type,
            "context_limit": executor.reported_context_limit,
            "context_limit_source": executor.context_limit_source,
            "execution_mode": registry.get_execution_mode(
                tenant_id=str(auth.tenant_id),
                user_id=str(auth.user_id),
            ),
        }
    except Exception as exc:
        logger.warning(
            "Falling back to runtime defaults for tenant %s user %s: %s",
            auth.tenant_id,
            auth.user_id,
            exc,
            exc_info=True,
        )
        return {
            "model_name": settings.llm_model or None,
            "provider_type": settings.llm_provider,
            "context_limit": None,
            "context_limit_source": "unknown",
            "execution_mode": registry.get_execution_mode(
                tenant_id=str(auth.tenant_id),
                user_id=str(auth.user_id),
            ),
        }


@router.get(
    "/execution-mode",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_execution_mode(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    conversation_id: uuid.UUID | None = Query(default=None),  # noqa: B008
) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    mode = registry.get_execution_mode(
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
        conversation_id=str(conversation_id) if conversation_id else None,
    )
    return {
        "execution_mode": mode,
        "conversation_id": str(conversation_id) if conversation_id else None,
    }


@router.patch(
    "/execution-mode",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def update_execution_mode(
    payload: UpdateExecutionModeRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    mode = registry.set_execution_mode(
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
        conversation_id=(
            str(payload.conversation_id) if payload.conversation_id else None
        ),
        mode=payload.execution_mode,
    )
    return {
        "execution_mode": mode,
        "conversation_id": (
            str(payload.conversation_id) if payload.conversation_id else None
        ),
    }


@router.get(
    "/runtime-preferences",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_runtime_preferences(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    conversation_id: uuid.UUID | None = Query(default=None),  # noqa: B008
) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    serialized_conversation_id = str(conversation_id) if conversation_id else None
    return _serialize_runtime_preferences(
        registry=registry,
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
        conversation_id=serialized_conversation_id,
    )


@router.patch(
    "/runtime-preferences",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def update_runtime_preferences(
    payload: UpdateRuntimePreferencesRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    conversation_id = str(payload.conversation_id) if payload.conversation_id else None
    tenant_id = str(auth.tenant_id)
    user_id = str(auth.user_id)

    if payload.execution_mode is not None:
        registry.set_execution_mode(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            mode=payload.execution_mode,
        )
    if payload.planner_mode is not None:
        registry.set_planner_mode(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            mode=payload.planner_mode,
        )
    if payload.subagent_profile is not None:
        registry.set_subagent_profile(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            profile=payload.subagent_profile,
        )
    if payload.runtime_hooks_enabled is not None:
        registry.set_runtime_hooks_enabled(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            enabled=payload.runtime_hooks_enabled,
        )
    if payload.workspace_mode_enabled is not None:
        registry.set_workspace_mode_enabled(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            enabled=payload.workspace_mode_enabled,
        )
    if payload.full_autonomy_enabled is not None:
        registry.set_full_autonomy_enabled(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            enabled=payload.full_autonomy_enabled,
        )

    return _serialize_runtime_preferences(
        registry=registry,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )


@router.get(
    "/orchestration",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_global_orchestration(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    conversation_id: str | None = Query(default=None),
) -> dict[str, Any]:
    from app.services.deepspace.orchestration.orchestration_service import OrchestrationService

    service = OrchestrationService()
    return await service.get_orchestration_overview(
        auth=auth, db=db, settings=settings, conversation_id=conversation_id
    )


@router.get(
    "/orchestrations/missions",
    response_model=list[dict[str, Any]],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def list_orchestration_missions(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    status: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    return registry.list_missions(
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
        status=status,
        limit=limit,
    )


@router.get(
    "/orchestrations/missions/{mission_id}",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_orchestration_mission(
    mission_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    mission = registry.get_mission(mission_id)
    if not mission:
        raise ApiError(
            code="MISSION_NOT_FOUND",
            message="Mission not found.",
            status_code=404,
        )
    if str(mission.get("tenant_id") or "") != str(auth.tenant_id) or str(
        mission.get("user_id") or ""
    ) != str(auth.user_id):
        raise ApiError(
            code="MISSION_FORBIDDEN",
            message="You cannot access another user's mission.",
            status_code=403,
        )
    return mission


@router.get("/runs/{run_id}", dependencies=[Depends(require_permissions("queries:run"))])
async def get_legacy_durable_run(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry
    mission = _durable_mission_or_404(registry=MissionRegistry(settings, db=db), mission_id=run_id, auth=auth)
    return _mission_as_durable_run(mission)


@router.get("/runs/{run_id}/events", dependencies=[Depends(require_permissions("queries:run"))])
async def get_legacy_durable_events(
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=250, ge=1, le=500),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry
    mission = _durable_mission_or_404(registry=MissionRegistry(settings, db=db), mission_id=run_id, auth=auth)
    events = []
    for index, event in enumerate(list(mission.get("events") or []), start=1):
        if index <= after_sequence:
            continue
        events.append({"id": f"{run_id}:{index}", "run_id": run_id, "sequence": index, "event_type": event.get("type", "mission_event"), "node_id": event.get("lane_id"), "payload_json": event.get("data", event), "occurred_at": event.get("timestamp")})
        if len(events) >= limit:
            break
    return {"events": events, "after_sequence": after_sequence, "last_sequence": len(mission.get("events") or [])}


@router.get("/runs/{run_id}/graph", dependencies=[Depends(require_permissions("queries:run"))])
async def get_legacy_durable_graph(run_id: str, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry
    mission = _durable_mission_or_404(registry=MissionRegistry(settings, db=db), mission_id=run_id, auth=auth)
    lanes = mission.get("lane_states") or (mission.get("plan") or {}).get("lanes") or []
    return {"nodes": [{"id": str(lane.get("lane_id") or lane.get("id") or index), "node_key": str(lane.get("lane_id") or lane.get("id") or index), "node_type": str(lane.get("lane_type") or "task"), "status": str(lane.get("status") or "planned"), "dependencies": lane.get("depends_on") or [], "metadata": lane.get("metadata") or {}} for index, lane in enumerate(lanes)]}


@router.get("/runs/{run_id}/observability", dependencies=[Depends(require_permissions("queries:run"))])
async def get_legacy_durable_observability(run_id: str, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry
    mission = _durable_mission_or_404(registry=MissionRegistry(settings, db=db), mission_id=run_id, auth=auth)
    run = _mission_as_durable_run(mission)
    return {"run_id": run_id, "trace_id": run_id, "status": run["status"], "sequence": run["current_sequence"], "continuation_epoch": run["continuation_epoch"], "recovery_count": run["recovery_count"], "budget": run["budget_json"], "trajectory": {}, "evaluation": {}, "decision": mission.get("last_event_type"), "dead_letter": False, "projection": run["runtime_state"]}


@router.get("/runs/{run_id}/stream", dependencies=[Depends(require_permissions("queries:run"))])
async def stream_legacy_durable_events(run_id: str, after_sequence: int = Query(default=0, ge=0), auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> StreamingResponse:
    from app.services.deepspace.missions.mission_registry import MissionRegistry
    mission = _durable_mission_or_404(registry=MissionRegistry(settings, db=db), mission_id=run_id, auth=auth)
    events = list(mission.get("events") or [])[after_sequence:]
    terminal = str(mission.get("status")) in {"completed", "failed", "cancelled"}
    async def iterator() -> AsyncIterator[str]:
        for index, event in enumerate(events, start=after_sequence + 1):
            payload = {"id": f"{run_id}:{index}", "run_id": run_id, "sequence": index, "event_type": event.get("type", "mission_event"), "node_id": event.get("lane_id"), "payload_json": event.get("data", event), "occurred_at": event.get("timestamp")}
            yield f"id: {index}\ndata: {json.dumps(payload, default=str)}\n\n"
        if terminal:
            payload = {"id": f"{run_id}:terminal", "run_id": run_id, "sequence": len(mission.get("events") or []) + 1, "event_type": f"run_{str(mission.get('status'))}", "payload_json": {}}
            yield f"id: {payload['sequence']}\ndata: {json.dumps(payload)}\n\n"
    return StreamingResponse(iterator(), media_type="text/event-stream", headers=_stream_headers())


@router.post("/runs/{run_id}/replay", dependencies=[Depends(require_permissions("queries:run"))])
async def replay_legacy_durable_run(run_id: str, after_sequence: int = Query(default=0, ge=0), auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    from app.services.deepspace.missions.mission_registry import MissionRegistry
    mission = _durable_mission_or_404(registry=MissionRegistry(settings, db=db), mission_id=run_id, auth=auth)
    events = list(mission.get("events") or [])[after_sequence:]
    return {"sequence": len(mission.get("events") or []), "status": mission.get("status"), "nodes": {}, "approvals": mission.get("approval_queue") or [], "events": events, "read_only": True, "cursor": {"after_sequence": after_sequence, "last_sequence": len(mission.get("events") or [])}}


@router.post(
    "/orchestrations/stream",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def stream_global_orchestration(
    request: Request,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Run a federated orchestration mission across OpenChat, subagents, and proactive work."""
    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )

    raw_payload = await request.json()
    objective = str(
        raw_payload.get("objective") or raw_payload.get("query") or ""
    ).strip()
    if not objective:
        raise ApiError(
            code="MISSION_VALIDATION_ERROR",
            message="objective is required.",
            status_code=422,
        )

    conversation_id_raw = raw_payload.get("conversation_id")
    conversation_id = (
        uuid.UUID(str(conversation_id_raw)) if conversation_id_raw else None
    )
    mission_id_raw = raw_payload.get("mission_id")
    mission_id = str(uuid.UUID(str(mission_id_raw))) if mission_id_raw else None

    note_content = raw_payload.get("note_content")
    previous_messages = raw_payload.get("previous_messages")
    if not isinstance(previous_messages, list):
        previous_messages = None

    from app.services.deepspace.missions.mission_registry import MissionRegistry
    from app.services.deepspace.orchestration.master_orchestrator import MasterOrchestrator

    registry = MissionRegistry(settings, db=db)
    execution_mode = registry.get_execution_mode(
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
        conversation_id=str(conversation_id) if conversation_id else None,
    )

    orchestrator = MasterOrchestrator(
        db=db,
        auth=auth,
        settings=settings,
        background_tasks=background_tasks,
    )

    async def iterator() -> AsyncIterator[str]:
        try:
            async for chunk in orchestrator.stream_mission(
                objective=objective,
                note_content=note_content,
                previous_messages=previous_messages,
                conversation_id=conversation_id,
                execution_mode=execution_mode,
                mission_id=mission_id,
            ):
                yield AnswerService.encode_sse_event(chunk)
        except ApiError as exc:
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="error",
                    data={"code": exc.code, "message": exc.message},
                )
            )
        except Exception:
            logger.exception(
                "Global orchestration stream failed for tenant %s user %s conversation %s",
                auth.tenant_id,
                auth.user_id,
                conversation_id,
            )
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="error",
                    data={
                        "code": "ORCHESTRATION_STREAM_FAILURE",
                        "message": "Orchestration failed before producing a response.",
                    },
                )
            )

    return StreamingResponse(
        iterator(),
        media_type="text/event-stream",
        headers=_stream_headers(),
    )


@router.post(
    "/orchestrations/missions/{mission_id}/approval",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def resolve_orchestration_approval(
    mission_id: str,
    payload: ResolveMissionApprovalRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Resolve a queued mission approval gate; the active mission stream resumes in place."""
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    mission = registry.get_mission(mission_id)
    if not mission:
        raise ApiError(
            code="MISSION_NOT_FOUND",
            message="Mission not found.",
            status_code=404,
        )
    if str(mission.get("tenant_id") or "") != str(auth.tenant_id) or str(
        mission.get("user_id") or ""
    ) != str(auth.user_id):
        raise ApiError(
            code="MISSION_FORBIDDEN",
            message="You cannot access another user's mission.",
            status_code=403,
        )

    registry.resolve_approval(mission_id, payload.lane_id, payload.approved)
    updated = registry.get_mission(mission_id)
    if not updated:
        raise ApiError(
            code="MISSION_NOT_FOUND",
            message="Mission not found after approval resolution.",
            status_code=404,
        )
    return updated


@router.get(
    "/subagents",
    response_model=list[SubagentRunSchema],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def list_subagent_runs(
    auth: AuthContext = Depends(get_auth_context),
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: str | None = Query(default=None),
) -> list[SubagentRunSchema]:
    from app.services.deepspace.subagents.subagent_registry import SubagentRegistry

    registry = SubagentRegistry()
    runs = registry.list_runs(
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
        status=status,
        limit=limit,
    )
    return [SubagentRunSchema.model_validate(run) for run in runs]


@router.get(
    "/subagents/summary",
    response_model=SubagentSummarySchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_subagent_summary(
    auth: AuthContext = Depends(get_auth_context),
) -> SubagentSummarySchema:
    from app.services.deepspace.subagents.subagent_registry import SubagentRegistry

    registry = SubagentRegistry()
    runs = registry.list_runs(
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
        limit=100,
    )
    running_count = sum(
        1 for run in runs if str(run.get("status") or "").lower() == "running"
    )
    terminating_count = sum(
        1 for run in runs if str(run.get("status") or "").lower() == "terminating"
    )
    cancelled_count = sum(
        1 for run in runs if str(run.get("status") or "").lower() == "cancelled"
    )
    stale_count = sum(
        1 for run in runs if str(run.get("status") or "").lower() == "stale"
    )
    pressure_count = running_count + terminating_count
    max_concurrency = registry.max_concurrency
    return SubagentSummarySchema(
        backend_available=registry.is_backend_available(),
        max_concurrency=max_concurrency,
        active_count=len(runs),
        live_count=pressure_count,
        running_count=running_count,
        terminating_count=terminating_count,
        cancelled_count=cancelled_count,
        stale_count=stale_count,
        pressure_count=pressure_count,
        pressure_ratio=round(pressure_count / max(1, max_concurrency), 4),
        daemon_heartbeat=registry.get_daemon_heartbeat(),
    )


@router.post(
    "/subagents/{run_id}/terminate",
    response_model=SubagentRunSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def terminate_subagent_run(
    run_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> SubagentRunSchema:
    from app.services.deepspace.subagents.subagent_registry import SubagentRegistry

    registry = SubagentRegistry()
    run = registry.get_run(run_id)
    if not run:
        raise ApiError(
            code="SUBAGENT_RUN_NOT_FOUND",
            message="Sub-agent run not found.",
            status_code=404,
        )
    if str(run.get("tenant_id") or "") != str(auth.tenant_id) or str(
        run.get("user_id") or ""
    ) != str(auth.user_id):
        raise ApiError(
            code="SUBAGENT_RUN_FORBIDDEN",
            message="You cannot terminate another user's sub-agent run.",
            status_code=403,
        )

    terminated = registry.request_termination(run_id)
    if not terminated:
        raise ApiError(
            code="SUBAGENT_RUN_NOT_FOUND",
            message="Sub-agent run not found.",
            status_code=404,
        )
    return SubagentRunSchema.model_validate(terminated)


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
    from app.services.deepspace.integrations.client_proxy import client_proxy_registry
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
        # Keep only an ownership/index record on the VPS. Message content
        # remains in the client-owned store when this channel is active.
        repo = ChatRepository(db)
        if repo.get_conversation(
            tenant_id=auth.tenant_id,
            conversation_id=uuid.UUID(str(conversation["id"])),
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        ) is None:
            repo.create_conversation(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=uuid.UUID(str(conversation["id"])),
                kind=CONVERSATION_KIND,
                title=str(conversation.get("title") or data.title),
                content_html=None,
            )
            db.commit()
        return ConversationSchema.model_validate(conversation)
    repo = ChatRepository(db)
    conversation = repo.create_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
        title=data.title,
        content_html=data.content_html,
    )
    db.commit()
    return ConversationSchema.model_validate(conversation)


@router.post(
    "/stream",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def stream_deepspace_chat(
    request: Request,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )

    raw_payload = await request.json()
    query_text = str(raw_payload.get("query", "")).strip()
    if not query_text:
        raise ApiError(
            code="QUERY_VALIDATION_ERROR",
            message="query is required.",
            status_code=422,
        )

    conversation_id_raw = raw_payload.get("conversation_id")
    conversation_id = (
        uuid.UUID(str(conversation_id_raw)) if conversation_id_raw else None
    )
    note_content = raw_payload.get("note_content")
    thinking_enabled = bool(raw_payload.get("thinking_enabled", True))
    web_search_enabled = bool(raw_payload.get("web_search_enabled", True))
    agentic_mode = bool(raw_payload.get("agentic_mode", True))
    service = DeepSpaceService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        try:
            async for chunk in service.stream_chat(
                auth=auth,
                query_text=query_text,
                conversation_id=conversation_id,
                note_content=note_content,
                thinking_enabled=thinking_enabled,
                web_search_enabled=web_search_enabled,
                background_tasks=background_tasks,
                agentic_mode=agentic_mode,
            ):
                yield chunk
        except ApiError as exc:
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="error",
                    data={"code": exc.code, "message": exc.message},
                )
            )
        except Exception:
            logger.exception(
                "DeepSpace stream failed for tenant %s user %s conversation %s",
                auth.tenant_id,
                auth.user_id,
                conversation_id,
            )
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="error",
                    data={
                        "code": "DEEPSPACE_STREAM_FAILURE",
                        "message": "DeepSpace failed before producing a reply.",
                    },
                )
            )

    return StreamingResponse(
        iterator(),
        media_type="text/event-stream",
        headers=_stream_headers(),
    )


@router.post(
    "/resume",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def resume_deepspace_chat(
    request: Request,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Resume a paused agent execution after a permission request was approved."""
    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )

    raw_payload = await request.json()
    conversation_id_raw = raw_payload.get("conversation_id")
    conversation_id = (
        uuid.UUID(str(conversation_id_raw)) if conversation_id_raw else None
    )
    step_id = raw_payload.get("step_id")
    tool_id = raw_payload.get("tool_id")
    approved = bool(raw_payload.get("approved", True))

    if not conversation_id or not step_id:
        raise ApiError(
            code="RESUME_VALIDATION_ERROR",
            message="conversation_id and step_id are required.",
            status_code=422,
        )

    service = DeepSpaceService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        try:
            async for chunk in service.resume_chat(
                auth=auth,
                conversation_id=conversation_id,
                step_id=step_id,
                tool_id=tool_id,
                approved=approved,
                background_tasks=background_tasks,
            ):
                yield chunk
        except ApiError as exc:
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="error",
                    data={"code": exc.code, "message": exc.message},
                )
            )
        except Exception:
            logger.exception(
                "DeepSpace resume failed for tenant %s user %s conversation %s step %s tool %s",
                auth.tenant_id,
                auth.user_id,
                conversation_id,
                step_id,
                tool_id,
            )
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="error",
                    data={
                        "code": "DEEPSPACE_RESUME_FAILURE",
                        "message": "DeepSpace could not resume the paused agent step.",
                    },
                )
            )

    return StreamingResponse(
        iterator(),
        media_type="text/event-stream",
        headers=_stream_headers(),
    )


@router.websocket("/ws")
async def websocket_deepspace_chat(
    websocket: WebSocket,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    await websocket.accept()
    try:
        auth = await _authenticate_websocket_auth_context(
            websocket, db=db, settings=settings
        )
        # HTTP requests receive tenant context from the tenancy dependency, but
        # websocket handlers authenticate manually.  Bind the tenant on this
        # SQLAlchemy transaction before any RLS-protected DeepSpace query.
        set_db_tenant_context(db, auth.tenant_id)
        _require_websocket_permissions(auth)
        payload = await websocket.receive_json()
        service = DeepSpaceService(db=db, settings=settings)
        await _stream_service_over_websocket(
            websocket,
            service=service,
            auth=auth,
            settings=settings,
            db=db,
            payload=payload if isinstance(payload, dict) else {},
        )
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        return
    except ApiError as exc:
        try:
            await _send_websocket_sse_error(
                websocket, code=exc.code, message=exc.message
            )
        finally:
            await websocket.close(code=1008)
    except Exception:
        logger.exception("DeepSpace websocket stream failed")
        try:
            await _send_websocket_sse_error(
                websocket,
                code="DEEPSPACE_WEBSOCKET_FAILURE",
                message="DeepSpace websocket stream failed before producing a response.",
            )
        finally:
            await websocket.close(code=1011)


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
            str(auth.tenant_id),
            str(auth.user_id),
            "db.chats.get_chat_history",
            {"conversation_id": str(conversation_id), "user_id": str(auth.user_id)},
            channel="storage",
        )
        # Older turns may have been written to the server before the
        # client-owned assistant-write path was corrected.  Merge those
        # records back into the response so a reload does not hide replies
        # that already exist in the VPS history.
        repo = ChatRepository(db)
        server_messages = repo.get_messages(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
        known_ids = {str(item.get("id")) for item in messages_data if item.get("id")}
        messages_data = list(messages_data) + [
            _serialize_message(item).model_dump()
            for item in server_messages
            if str(item.id) not in known_ids
        ]
        messages_data.sort(key=lambda item: str(item.get("created_at") or ""))
        return ChatHistoryResponse(
            messages=[MessageSchema.model_validate(item) for item in messages_data]
        )
    repo = ChatRepository(db)
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
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )
    if not deleted:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )
    from sqlalchemy import update

    from app.models.deepspace.agent_todo import AgentTodo

    db.execute(
        update(AgentTodo)
        .where(
            AgentTodo.tenant_id == str(auth.tenant_id),
            AgentTodo.user_id == str(auth.user_id),
            AgentTodo.thread_id == str(conversation_id),
        )
        .values(status="deleted")
    )
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
    settings: Settings = Depends(get_settings),
) -> Response:
    from app.services.deepspace.missions.mission_registry import MissionRegistry

    registry = MissionRegistry(settings, db=db)
    active = registry.active_missions(
        tenant_id=str(auth.tenant_id),
        user_id=str(auth.user_id),
    )
    cancelled_count = 0
    for mission in active:
        parent_id = mission.get("parent_id")
        if parent_id and str(parent_id) == str(conversation_id):
            registry.request_cancellation(str(mission["mission_id"]))
            cancelled_count += 1
    return Response(
        status_code=200, headers={"X-Cancelled-Count": str(cancelled_count)}
    )


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
        kind=CONVERSATION_KIND,
    )
    from sqlalchemy import update

    from app.models.deepspace.agent_todo import AgentTodo

    db.execute(
        update(AgentTodo)
        .where(
            AgentTodo.tenant_id == str(auth.tenant_id),
            AgentTodo.user_id == str(auth.user_id),
            AgentTodo.thread_id.in_([str(cid) for cid in payload.conversation_ids]),
        )
        .values(status="deleted")
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
        kind=CONVERSATION_KIND,
    )
    if message is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND", message="Message not found.", status_code=404
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
    repo = ChatRepository(db)
    user_message, assistant_message = repo.get_latest_turn_pair(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
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
        raise ApiError(
            code="MESSAGE_NOT_FOUND", message="Message not found.", status_code=404
        )
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
    repo = ChatRepository(db)
    message = repo.get_message_by_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        kind=CONVERSATION_KIND,
    )
    if message is None:
        raise ApiError(
            code="MESSAGE_NOT_FOUND", message="Message not found.", status_code=404
        )
    repo.activate_message_version(
        tenant_id=auth.tenant_id,
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
        raise ApiError(
            code="MESSAGE_NOT_FOUND", message="Message not found.", status_code=404
        )
    return _serialize_message(refreshed)


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
    _validate_top_k_bounds(top_k=payload.top_k, settings=settings)
    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )
    service = DeepSpaceService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        async for chunk in service.regenerate_message_stream(
            auth=auth,
            conversation_id=conversation_id,
            assistant_message_id=message_id,
            thinking_enabled=payload.thinking_enabled,
            agentic_mode=payload.agentic_mode,
        ):
            yield chunk

    return StreamingResponse(
        iterator(), media_type="text/event-stream", headers=SSE_HEADERS
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
    thinking_enabled = bool(raw_payload.get("thinking_enabled", True))
    agentic_mode = bool(raw_payload.get("agentic_mode", True))
    payload = MessageEditRequest(content=content)
    regenerate = RegenerateRequest(
        top_k=top_k,
        search_mode=search_mode,
        document_id=document_id,
        thinking_enabled=thinking_enabled,
        agentic_mode=agentic_mode,
    )
    _validate_top_k_bounds(top_k=regenerate.top_k, settings=settings)
    service = DeepSpaceService(db=db, settings=settings)

    async def iterator() -> AsyncIterator[str]:
        async for chunk in service.edit_and_regenerate_message_stream(
            auth=auth,
            conversation_id=conversation_id,
            user_message_id=message_id,
            updated_content=payload.content,
            thinking_enabled=regenerate.thinking_enabled,
            agentic_mode=regenerate.agentic_mode,
        ):
            yield chunk

    return StreamingResponse(
        iterator(), media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.get("/memory/search", response_model=dict[str, Any])
async def search_memories(
    query: str = Query(..., min_length=1),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.memory.memory_service import MemoryService

    service = MemoryService(db)
    results = await service.search_memories(
        tenant_id=auth.tenant_id, user_id=auth.user_id, query=query
    )
    return {"results": results}


@router.get("/memory", response_model=list[MemoryFactSchema])
async def list_memories(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.memory.memory_service import MemoryService

    service = MemoryService(db)
    return await service.list_all_memories(
        tenant_id=auth.tenant_id, user_id=auth.user_id
    )


@router.delete("/memory/{key}")
async def forget_memory(
    key: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.memory.memory_service import MemoryService

    service = MemoryService(db)
    success = await service.forget_memory(
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
):
    from app.services.deepspace.memory.memory_service import MemoryService

    service = MemoryService(db)
    return await service.cleanup_duplicate_memories(
        tenant_id=auth.tenant_id, user_id=auth.user_id
    )


@router.post("/memory/cleanup-stale", response_model=dict[str, Any])
async def cleanup_stale_memories(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    retention_days: Annotated[int, Query(ge=1, le=3650)] = 7,
):
    from app.services.deepspace.memory.memory_service import MemoryService

    service = MemoryService(db)
    return await service.cleanup_stale_memories(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        retention_days=retention_days,
    )


@router.get("/memory/retention", response_model=MemoryRetentionReportSchema)
async def evaluate_memory_retention(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    retention_days: Annotated[int, Query(ge=1, le=3650)] = 7,
):
    from app.services.deepspace.memory.memory_service import MemoryService

    service = MemoryService(db)
    return await service.evaluate_memory_retention(
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
    from app.services.deepspace.memory.memory_service import MemoryService

    service = MemoryService(db)
    report = await service.evaluate_memory_quality(
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


@router.get("/memory/lifecycle", response_model=MemoryLifecycleReportSchema)
async def preview_memory_lifecycle(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    retention_days: Annotated[int, Query(ge=1, le=3650)] = 7,
    sample_queries: Annotated[list[str] | None, Query()] = None,
) -> MemoryLifecycleReportSchema:
    from app.services.deepspace.memory.memory_service import MemoryService

    service = MemoryService(db)
    report = await service.preview_memory_lifecycle(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        retention_days=retention_days,
        sample_queries=sample_queries or None,
    )
    report["retention_policy"] = {
        "session_retention_days": retention_days,
        "decay_half_life_days": report.get("retention_policy", {}).get(
            "decay_half_life_days", 120.0
        ),
    }
    report.setdefault("session_retention_days", retention_days)
    return MemoryLifecycleReportSchema.model_validate(report)


@router.get("/tasks", response_model=list[TodoTaskSchema])
async def list_tasks(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.memory.memory_service import TodoService

    try:
        service = TodoService(db)
        return await service.list_todos(tenant_id=auth.tenant_id, user_id=auth.user_id)
    except Exception as exc:
        logger.warning(
            "Task list lookup failed for tenant %s user %s: %s",
            auth.tenant_id,
            auth.user_id,
            exc,
            exc_info=True,
        )
        return []


@router.get("/tasks/summary", response_model=ProactiveTaskSummarySchema)
async def get_task_summary(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProactiveTaskSummarySchema:
    from app.models.deepspace.agent_activity import AgentActivity
    from app.services.deepspace.memory.memory_service import TodoService

    service = TodoService(db)
    try:
        tasks = await service.list_todos(tenant_id=auth.tenant_id, user_id=auth.user_id)
    except Exception as exc:
        logger.warning(
            "Task summary lookup failed for tenant %s user %s: %s",
            auth.tenant_id,
            auth.user_id,
            exc,
            exc_info=True,
        )
        tasks = []

    source_breakdown: dict[str, int] = {}
    approval_required = 0
    due = 0
    paused = 0
    enabled = 0
    recurring = 0
    pending = 0
    in_progress = 0
    completed = 0
    now = datetime.now(UTC)

    for task in tasks:
        status = str(task.get("status") or "pending")
        if status == "pending":
            pending += 1
        elif status == "in_progress":
            in_progress += 1
        elif status == "completed":
            completed += 1
        if bool(task.get("is_recurring")):
            recurring += 1
        if bool(task.get("enabled", True)):
            enabled += 1
        else:
            paused += 1
        automation = task.get("automation_json")
        metadata = (
            task.get("metadata_json")
            if isinstance(task.get("metadata_json"), dict)
            else {}
        )
        if isinstance(automation, dict):
            if automation.get("requires_approval"):
                approval_required += 1
            source = str(
                automation.get("source") or metadata.get("source") or ""
            ).strip()
            if source:
                source_breakdown[source] = source_breakdown.get(source, 0) + 1
        next_run_at = task.get("next_run_at")
        if (
            next_run_at is not None
            and bool(task.get("enabled", True))
            and bool(task.get("is_recurring"))
        ):
            try:
                parsed_next_run = (
                    next_run_at
                    if isinstance(next_run_at, datetime)
                    else datetime.fromisoformat(str(next_run_at).replace("Z", "+00:00"))
                )
                if parsed_next_run.tzinfo is None:
                    parsed_next_run = parsed_next_run.replace(tzinfo=UTC)
                if parsed_next_run <= now:
                    due += 1
            except ValueError:
                pass

    recent_activity_count = (
        db.query(AgentActivity)
        .filter(AgentActivity.tenant_id == auth.tenant_id)
        .count()
    )
    recent_error_count = (
        db.query(AgentActivity)
        .filter(
            AgentActivity.tenant_id == auth.tenant_id,
            AgentActivity.activity_type == "error",
        )
        .count()
    )

    recent_activity_rows = (
        db.query(AgentActivity)
        .filter(AgentActivity.tenant_id == auth.tenant_id)
        .order_by(AgentActivity.created_at.desc())
        .limit(250)
        .all()
    )
    cycle_ids: list[str] = []
    cycle_metadata_by_id: dict[str, dict[str, Any]] = {}
    for activity in recent_activity_rows:
        metadata = (
            activity.metadata_json if isinstance(activity.metadata_json, dict) else {}
        )
        cycle_id = str(metadata.get("proactive_cycle_id") or "").strip()
        if not cycle_id:
            continue
        if cycle_id not in cycle_ids:
            cycle_ids.append(cycle_id)
        cycle_metadata_by_id.setdefault(cycle_id, metadata)

    latest_cycle_id = cycle_ids[0] if cycle_ids else None
    latest_cycle_metadata = cycle_metadata_by_id.get(latest_cycle_id or "", {})
    latest_cycle_activities = [
        activity
        for activity in recent_activity_rows
        if isinstance(activity.metadata_json, dict)
        and str(activity.metadata_json.get("proactive_cycle_id") or "").strip()
        == latest_cycle_id
    ]
    recent_cycle_failure_count = sum(
        1
        for activity in latest_cycle_activities
        if activity.activity_type == "error"
        or str((activity.metadata_json or {}).get("phase") or "")
        in {"error", "gmail_scan", "gmail_message"}
    )
    gmail_scan_failure_count = sum(
        1
        for activity in recent_activity_rows
        if activity.source == "gmail"
        and isinstance(activity.metadata_json, dict)
        and activity.metadata_json.get("error_code") == "gmail_scan_failed"
    )
    gmail_message_failure_count = sum(
        1
        for activity in recent_activity_rows
        if activity.source == "gmail"
        and isinstance(activity.metadata_json, dict)
        and activity.metadata_json.get("error_code") == "gmail_message_failed"
    )
    last_cycle_at = (
        latest_cycle_activities[0].created_at if latest_cycle_activities else None
    )
    last_cycle_status = None
    if latest_cycle_id is not None:
        last_cycle_status = (
            "degraded"
            if recent_cycle_failure_count > 0
            else str(latest_cycle_metadata.get("status") or "healthy")
        )

    return ProactiveTaskSummarySchema(
        total=len(tasks),
        pending=pending,
        in_progress=in_progress,
        completed=completed,
        recurring=recurring,
        enabled=enabled,
        paused=paused,
        due=due,
        approval_required=approval_required,
        source_breakdown=source_breakdown,
        recent_activity_count=recent_activity_count,
        recent_error_count=recent_error_count,
        recent_cycle_count=len(cycle_ids),
        recent_cycle_failure_count=recent_cycle_failure_count,
        gmail_scan_failure_count=gmail_scan_failure_count,
        gmail_message_failure_count=gmail_message_failure_count,
        last_cycle_at=last_cycle_at,
        last_cycle_status=last_cycle_status,
    )


@router.post("/tasks", response_model=TodoTaskSchema)
async def create_task(
    payload: TodoTaskCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.memory.memory_service import TodoService

    service = TodoService(db)
    return service.create_task(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        content=payload.content,
        active_form=payload.active_form,
        status=payload.status,
        priority=payload.priority,
        thread_id=payload.thread_id,
        metadata_json=payload.metadata_json,
        automation_json=payload.automation_json,
        is_recurring=payload.is_recurring,
        enabled=payload.enabled,
        next_run_at=payload.next_run_at,
        last_run_at=payload.last_run_at,
    )


@router.patch("/tasks/{task_id}", response_model=TodoTaskSchema)
async def update_task(
    task_id: str,
    payload: TodoTaskUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.core.errors import ApiError
    from app.services.deepspace.memory.memory_service import TodoService

    service = TodoService(db)
    try:
        return service.update_task(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            task_id=task_id,
            updates=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise ApiError(
            code="TASK_NOT_FOUND", message=str(exc), status_code=404
        ) from exc


@router.delete(
    "/tasks/{task_id}",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def delete_task(
    task_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    from app.core.errors import ApiError
    from app.services.deepspace.memory.memory_service import TodoService

    service = TodoService(db)
    try:
        service.delete_task(
            tenant_id=str(auth.tenant_id),
            user_id=str(auth.user_id),
            task_id=task_id,
        )
        return Response(status_code=204)
    except ValueError as exc:
        raise ApiError(
            code="TASK_NOT_FOUND", message=str(exc), status_code=404
        ) from exc


@router.post("/tasks/{task_id}/run-now", response_model=TodoTaskSchema)
async def run_task_now(
    task_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.memory.memory_service import TodoService
    from app.worker.tasks_proactive import _run_recurring_rule

    service = TodoService(db)
    task = service.get_task(
        tenant_id=auth.tenant_id, user_id=auth.user_id, task_id=task_id
    )
    if task is None:
        raise ApiError(
            code="TASK_NOT_FOUND", message="Task not found.", status_code=404
        )

    await _run_recurring_rule(db=db, todo_service=service, rule=task)

    refreshed = service.get_task(
        tenant_id=auth.tenant_id, user_id=auth.user_id, task_id=task_id
    )
    return service._task_to_dict(refreshed or task)


@router.post("/{conversation_id}/fork", response_model=ConversationSchema)
async def fork_conversation(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    repo = ChatRepository(db)
    forked = repo.fork_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        kind=CONVERSATION_KIND,
    )
    db.commit()
    return ConversationSchema.model_validate(forked)


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    repo = ChatRepository(db)
    messages = repo.get_messages(
        tenant_id=auth.tenant_id,
        conversation_id=conversation_id,
        user_id=auth.user_id,
        kind=CONVERSATION_KIND,
    )

    md = f"# DeepSpace Session: {conversation_id}\n\n"
    for m in messages:
        md += f"## {m.role.upper()}\n{m.active_version.content if m.active_version else m.content}\n\n"

    return Response(
        content=md,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename=deepspace_session_{conversation_id}.md"
        },
    )


@router.post("/{conversation_id}/rewind")
async def rewind_conversation(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    repo = ChatRepository(db)
    success = repo.rewind_last_turn(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        kind=CONVERSATION_KIND,
    )
    db.commit()
    return {"success": success}


# --- PRODUCTION SaaS ALIASED ENDPOINTS ---


@router.post("/session/create", response_model=ConversationSchema)
async def create_session(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    repo = ChatRepository(db)
    session = repo.create_conversation(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        title="New Mission",
        kind=CONVERSATION_KIND,
    )
    db.commit()
    return ConversationSchema.model_validate(session)


@router.get("/session/{session_id}/context")
async def get_session_context(
    session_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.execution.agent_executor import AgentExecutor
    from app.services.deepspace.deepspace_runtime.runtime_contracts import (
        estimate_messages_tokens,
        normalize_conversation_compaction_state,
        resolve_compacted_session_messages,
    )

    repo = ChatRepository(db)
    messages = list(
        repo.get_messages(
            tenant_id=auth.tenant_id,
            conversation_id=session_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
    )
    latest_compaction = None
    history_payload: list[dict[str, Any]] = []
    for message in messages:
        active_version = getattr(message, "active_version", None)
        content = (
            active_version.content
            if active_version is not None and isinstance(active_version.content, str)
            else message.content
        )
        metadata = (
            dict(active_version.metadata_json)
            if active_version is not None
            and isinstance(active_version.metadata_json, dict)
            else dict(getattr(message, "metadata_json", {}) or {})
        )
        compacted_state = normalize_conversation_compaction_state(
            metadata.get("conversation_compaction")
        )
        if compacted_state is not None:
            latest_compaction = compacted_state
        if not str(content or "").strip():
            continue
        history_payload.append(
            {
                "id": str(message.id),
                "message_id": str(message.id),
                "role": str(message.role),
                "content": str(content),
            }
        )
    effective_messages = resolve_compacted_session_messages(
        history_messages=history_payload,
        compaction_state=latest_compaction,
    )
    tokens = estimate_messages_tokens(effective_messages)
    try:
        executor = AgentExecutor(db=db, auth=auth)
        reported_context_limit = executor.reported_context_limit
        resolved_context_limit = executor.context_limit
        context_limit_source = executor.context_limit_source
    except Exception as exc:
        logger.warning(
            "Falling back to session context defaults for tenant %s user %s: %s",
            auth.tenant_id,
            auth.user_id,
            exc,
            exc_info=True,
        )
        reported_context_limit = None
        resolved_context_limit = None
        fallback_limit = None
        context_limit_source = "unknown"
    else:
        fallback_limit = resolved_context_limit
    return {
        "session_id": session_id,
        "token_count": tokens,
        "usage_pct": (
            min(tokens / max(fallback_limit or 1, 1), 1.0) if fallback_limit else 0.0
        ),
        "limit": reported_context_limit,
        "context_limit_source": context_limit_source,
        "compaction": latest_compaction.to_metadata() if latest_compaction else None,
    }


@router.post("/session/{session_id}/compact")
async def trigger_compaction(
    session_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.execution.agent_executor import AgentExecutor

    executor = AgentExecutor(db, auth)
    result = await executor.force_compact(session_id)
    return result


@router.post("/tools/execute")
async def direct_tool_execute(
    request: dict[str, Any],
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from app.services.deepspace.execution.agent_tools import ToolExecutor

    executor = ToolExecutor(db, auth)
    conversation_id = request.get("conversation_id")
    try:
        conversation_uuid = uuid.UUID(str(conversation_id)) if conversation_id else None
    except (TypeError, ValueError):
        conversation_uuid = None
    result = await executor.execute(
        request["name"],
        request["args"],
        conversation_id=conversation_uuid,
    )
    return result
