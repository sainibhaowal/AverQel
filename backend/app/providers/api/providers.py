from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.auth.tenancy import require_request_tenant_id
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.platform.database.session import get_db, managed_db_session
from app.providers.models.provider_config import ProviderConfig
from app.providers.schemas import (
    MaskedProviderSecretResponse,
    ProviderAssignmentCreateRequest,
    ProviderAssignmentListResponse,
    ProviderAssignmentResponse,
    ProviderAssignmentUpdateRequest,
    ProviderCatalogEntry,
    ProviderCatalogResponse,
    ProviderConfigCreateRequest,
    ProviderConfigListResponse,
    ProviderConfigResponse,
    ProviderConfigUpdateRequest,
    ProviderDeleteResponse,
    ProviderDisconnectResponse,
    ProviderHealthResponse,
    ProviderModelListResponse,
    ProviderModelPreviewRequest,
    ProviderModelPullRequest,
    ProviderModelPullResponse,
    ProviderModelResponse,
    ProviderOAuthCallbackResponse,
    ProviderOAuthStartRequest,
    ProviderOAuthStartResponse,
    ProviderOAuthStatusResponse,
    ProviderRotateSecretRequest,
    ProviderTestResponse,
)
from app.providers.services import (
    ProviderHealthService,
    ProviderManagementService,
    ProviderModelsService,
    ProviderOAuthService,
)
from app.providers.services.base import ProviderRequestError
from app.providers.services.context_window import resolve_verified_context_window
from app.providers.services.provider_models_service import (
    acquire_model_discovery_slot,
    provider_request_error_to_api_error,
    release_model_discovery_slot,
)
from app.providers.services.registry import ProviderRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers", tags=["providers"])
OPTIONAL_WORKSPACE_QUERY = Query(default=None)
OPTIONAL_CODE_QUERY = Query(default=None)
OPTIONAL_STATE_QUERY = Query(default=None)
OPTIONAL_TENANT_QUERY = Query(default=None)


def _enforce_tenant_scope(request_tenant_id: uuid.UUID, auth: AuthContext) -> None:
    if request_tenant_id != auth.tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH",
            message="Requested tenant does not match authenticated tenant scope.",
            status_code=403,
        )


def _health_response(row: Any) -> ProviderHealthResponse | None:
    if row is None:
        return None
    return ProviderHealthResponse(
        status=row.status,
        latency_ms=row.latency_ms,
        http_status=row.http_status,
        error_code=row.error_code,
        error_message_redacted=row.error_message_redacted,
        metadata_json=dict(row.metadata_json or {}),
        checked_at=row.checked_at,
    )


def _masked_secret_response(row: Any) -> MaskedProviderSecretResponse:
    return MaskedProviderSecretResponse(
        secret_type=row.secret_type,
        masked_value=row.masked_value,
        expires_at=row.expires_at,
        metadata=dict(row.metadata or {}),
    )


def _provider_config_response(
    service: ProviderManagementService,
    *,
    tenant_id: uuid.UUID,
    provider: Any,
) -> ProviderConfigResponse:
    supports_web_search = provider.provider_type in {"tavily", "searxng"} or bool(
        dict(provider.metadata_json or {}).get("supports_web_search")
    )
    return ProviderConfigResponse(
        id=provider.id,
        tenant_id=provider.tenant_id,
        workspace_id=provider.workspace_id,
        owner_user_id=provider.owner_user_id,
        visibility_scope=provider.visibility_scope,
        provider_type=provider.provider_type,
        display_name=provider.display_name,
        api_base_url=provider.api_base_url,
        auth_mode=provider.auth_mode,
        enabled=provider.enabled,
        is_local=provider.is_local,
        supports_chat=provider.supports_chat,
        supports_embeddings=provider.supports_embeddings,
        supports_reranking=provider.supports_reranking,
        supports_web_search=supports_web_search,
        supports_model_listing=provider.supports_model_listing,
        supports_model_install=provider.supports_model_install,
        default_chat_model=provider.default_chat_model,
        default_embedding_model=provider.default_embedding_model,
        default_reranker_model=provider.default_reranker_model,
        timeout_seconds=provider.timeout_seconds,
        priority=provider.priority,
        metadata_json=dict(provider.metadata_json or {}),
        created_at=provider.created_at,
        updated_at=provider.updated_at,
        secrets=[
            _masked_secret_response(item)
            for item in service.list_masked_secrets(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
            )
        ],
        latest_health=_health_response(
            service.get_latest_health(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
            )
        ),
    )


def _assignment_response(row: Any) -> ProviderAssignmentResponse:
    return ProviderAssignmentResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        owner_user_id=row.owner_user_id,
        visibility_scope=row.visibility_scope,
        feature_scope=row.feature_scope,
        provider_config_id=row.provider_config_id,
        model_name=row.model_name,
        enabled=row.enabled,
        priority=row.priority,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _model_response(row: Any, *, provider_type: str | None = None) -> ProviderModelResponse:
    capabilities = dict(row.capabilities_json or {})
    context_window = row.context_window
    context_source = capabilities.get("context_window_source")
    if not isinstance(context_window, int) or context_window <= 0:
        verified = resolve_verified_context_window(
            row.model_name,
            provider_type=provider_type,
        )
        context_window = verified.context_window
        context_source = context_source or verified.source
    if context_source:
        capabilities["context_window_source"] = context_source
    return ProviderModelResponse(
        id=getattr(row, "id", None),
        provider_config_id=getattr(row, "provider_config_id", None),
        model_name=row.model_name,
        model_kind=row.model_kind,
        display_name=row.display_name,
        context_window=context_window,
        capabilities_json=capabilities,
        is_available=row.is_available,
        last_seen_at=row.last_seen_at,
    )


def _commit_or_rollback(
    *,
    db: Session,
    message: str,
    context: dict[str, str],
) -> None:
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning(message, extra=context, exc_info=True)
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Provider operation failed.",
            status_code=500,
        ) from exc


@router.get(
    "",
    response_model=ProviderConfigListResponse,
    dependencies=[Depends(require_permissions("providers:read"))],
)
async def list_providers(
    workspace_id: uuid.UUID | None = OPTIONAL_WORKSPACE_QUERY,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
) -> ProviderConfigListResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    from app.deepspace.integrations.client_proxy import (
        INTERACTIVE_STORAGE_RPC_TIMEOUT_SECONDS,
        client_proxy_registry,
    )

    if client_proxy_registry.is_client_connected(str(auth.tenant_id), str(auth.user_id)):
        try:
            items_data = await client_proxy_registry.db_proxy_call(
                str(auth.tenant_id),
                str(auth.user_id),
                "db.providers.list_providers",
                {"workspace_id": str(workspace_id) if workspace_id else None},
                timeout=INTERACTIVE_STORAGE_RPC_TIMEOUT_SECONDS,
            )
            return ProviderConfigListResponse(
                items=[ProviderConfigResponse.model_validate(item) for item in items_data]
            )
        except (TimeoutError, RuntimeError, OSError):
            logger.warning(
                "Client provider storage unavailable; using server-side provider data.",
                extra={"tenant_id": str(auth.tenant_id), "user_id": str(auth.user_id)},
            )

    # Do not acquire a database connection until the client-owned storage
    # branch is complete.  A suspended client must never occupy a pool slot
    # while its RPC timeout elapses.
    with managed_db_session() as db:
        service = ProviderManagementService(db)
        items = service.list_providers(
            tenant_id=auth.tenant_id,
            actor_user_id=auth.user_id,
            workspace_id=workspace_id,
        )
        return ProviderConfigListResponse(
            items=[
                _provider_config_response(service, tenant_id=auth.tenant_id, provider=item)
                for item in items
            ]
        )


@router.post(
    "",
    response_model=ProviderConfigResponse,
    dependencies=[Depends(require_permissions("providers:write"))],
)
async def create_provider(
    payload: ProviderConfigCreateRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderConfigResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    from app.deepspace.integrations.client_proxy import client_proxy_registry

    if client_proxy_registry.is_client_connected(str(auth.tenant_id), str(auth.user_id)):
        payload_dict = payload.model_dump()
        if "workspace_id" in payload_dict and payload_dict["workspace_id"]:
            payload_dict["workspace_id"] = str(payload_dict["workspace_id"])
        provider_data = await client_proxy_registry.db_proxy_call(
            str(auth.tenant_id), str(auth.user_id), "db.providers.create_provider", payload_dict
        )
        return ProviderConfigResponse.model_validate(provider_data)

    service = ProviderManagementService(db)
    provider = service.create_provider(
        tenant_id=auth.tenant_id,
        workspace_id=payload.workspace_id,
        actor_user_id=auth.user_id,
        provider_type=payload.provider_type,
        display_name=payload.display_name,
        api_base_url=payload.api_base_url,
        auth_mode=payload.auth_mode,
        enabled=payload.enabled,
        is_local=payload.is_local,
        supports_chat=payload.supports_chat,
        supports_embeddings=payload.supports_embeddings,
        supports_reranking=payload.supports_reranking,
        supports_web_search=payload.supports_web_search,
        supports_model_listing=payload.supports_model_listing,
        supports_model_install=payload.supports_model_install,
        default_chat_model=payload.default_chat_model,
        default_embedding_model=payload.default_embedding_model,
        default_reranker_model=payload.default_reranker_model,
        timeout_seconds=payload.timeout_seconds,
        priority=payload.priority,
        metadata_json=payload.metadata_json,
        api_key=payload.api_key,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to create provider config.",
        context={"tenant_id": str(auth.tenant_id), "user_id": str(auth.user_id)},
    )
    return _provider_config_response(service, tenant_id=auth.tenant_id, provider=provider)


@router.get(
    "/catalog/supported-types",
    response_model=ProviderCatalogResponse,
    dependencies=[Depends(require_permissions("providers:read"))],
)
def get_supported_provider_types(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderCatalogResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = ProviderManagementService(db)
    return ProviderCatalogResponse(
        items=[ProviderCatalogEntry.model_validate(item) for item in service.list_supported_types()]
    )


@router.post(
    "/models/preview",
    response_model=ProviderModelListResponse,
    dependencies=[Depends(require_permissions("providers:read"))],
)
def preview_models(
    payload: ProviderModelPreviewRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderModelListResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    provider = ProviderConfig(
        tenant_id=auth.tenant_id,
        workspace_id=payload.workspace_id,
        provider_type=payload.provider_type,
        display_name=payload.provider_type,
        api_base_url=payload.api_base_url,
        auth_mode=payload.auth_mode,
        enabled=True,
        is_local=payload.auth_mode == "local_no_key",
        supports_chat=payload.supports_chat,
        supports_embeddings=payload.supports_embeddings,
        supports_reranking=payload.supports_reranking,
        supports_model_listing=payload.supports_model_listing,
        supports_model_install=False,
        default_chat_model=None,
        default_embedding_model=None,
        default_reranker_model=None,
        timeout_seconds=30,
        priority=100,
        metadata_json={},
    )
    registry = ProviderRegistry(settings)
    acquire_model_discovery_slot("preview")
    try:
        discovery = registry.get_model_discovery_provider_from_config(
            provider, api_key=payload.api_key
        )
        logger.info(
            f"Model discovery for {payload.provider_type}: base_url={getattr(discovery, 'base_url', 'N/A')}"
        )
        infos = list(discovery.list_models()) if payload.supports_chat else []
        logger.info(f"Found {len(infos)} chat models, supports_chat={payload.supports_chat}")
        if payload.supports_embeddings:
            infos.extend(list(discovery.list_embedding_models()))
        if payload.supports_reranking:
            infos.extend(list(discovery.list_reranker_models()))
    except ProviderRequestError as exc:
        logger.error(f"ProviderRequestError: {exc}")
        raise provider_request_error_to_api_error(exc, operation="preview") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Exception in model preview: {exc}", exc_info=True)
        raise ApiError(
            code="PROVIDER_TEST_FAILED",
            message="Provider model preview failed.",
            status_code=502,
        ) from exc
    finally:
        release_model_discovery_slot()

    items: list[ProviderModelResponse] = []
    seen: set[tuple[str, str]] = set()
    for info in infos:
        key = (info.name, info.kind)
        if key in seen:
            continue
        seen.add(key)
        context_window = info.context_window
        context_source = info.context_window_source
        if not isinstance(context_window, int) or context_window <= 0:
            verified = resolve_verified_context_window(
                info.name,
                provider_type=payload.provider_type,
            )
            context_window = verified.context_window
            context_source = context_source or verified.source
        capabilities = dict(info.capabilities)
        if context_source:
            capabilities["context_window_source"] = context_source
        items.append(
            ProviderModelResponse(
                id=None,
                provider_config_id=None,
                model_name=info.name,
                model_kind=info.kind,
                display_name=info.display_name,
                context_window=context_window,
                capabilities_json=capabilities,
                is_available=True,
                last_seen_at=None,
            )
        )
    return ProviderModelListResponse(items=items)


@router.post(
    "/assignments",
    response_model=ProviderAssignmentResponse,
    dependencies=[Depends(require_permissions("providers:assign"))],
)
def create_assignment(
    payload: ProviderAssignmentCreateRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderAssignmentResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = ProviderManagementService(db).create_assignment(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        workspace_id=payload.workspace_id,
        feature_scope=payload.feature_scope,
        provider_config_id=payload.provider_config_id,
        model_name=payload.model_name,
        enabled=payload.enabled,
        priority=payload.priority,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to create provider assignment.",
        context={
            "tenant_id": str(auth.tenant_id),
            "provider_id": str(payload.provider_config_id),
        },
    )
    return _assignment_response(row)


@router.get(
    "/assignments",
    response_model=ProviderAssignmentListResponse,
    dependencies=[Depends(require_permissions("providers:assign"))],
)
def list_assignments(
    workspace_id: uuid.UUID | None = OPTIONAL_WORKSPACE_QUERY,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderAssignmentListResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    rows = ProviderManagementService(db).list_assignments(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        workspace_id=workspace_id,
    )
    return ProviderAssignmentListResponse(items=[_assignment_response(row) for row in rows])


@router.patch(
    "/assignments/{assignment_id}",
    response_model=ProviderAssignmentResponse,
    dependencies=[Depends(require_permissions("providers:assign"))],
)
def update_assignment(
    assignment_id: uuid.UUID,
    payload: ProviderAssignmentUpdateRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderAssignmentResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    values = payload.model_dump(exclude_none=True)
    row = ProviderManagementService(db).update_assignment(
        tenant_id=auth.tenant_id,
        assignment_id=assignment_id,
        actor_user_id=auth.user_id,
        values=values,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to update provider assignment.",
        context={"tenant_id": str(auth.tenant_id), "assignment_id": str(assignment_id)},
    )
    return _assignment_response(row)


@router.delete(
    "/assignments/{assignment_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("providers:assign"))],
)
def delete_assignment(
    assignment_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    _enforce_tenant_scope(request_tenant_id, auth)
    deleted = ProviderManagementService(db).delete_assignment(
        tenant_id=auth.tenant_id,
        assignment_id=assignment_id,
        actor_user_id=auth.user_id,
    )
    if not deleted:
        raise ApiError(
            code="PROVIDER_ASSIGNMENT_INVALID",
            message="Provider assignment not found.",
            status_code=404,
        )
    _commit_or_rollback(
        db=db,
        message="Failed to delete provider assignment.",
        context={"tenant_id": str(auth.tenant_id), "assignment_id": str(assignment_id)},
    )
    return Response(status_code=204)


@router.get(
    "/{provider_id}",
    response_model=ProviderConfigResponse,
    dependencies=[Depends(require_permissions("providers:read"))],
)
def get_provider(
    provider_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderConfigResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = ProviderManagementService(db)
    provider = service.get_provider(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
    )
    return _provider_config_response(service, tenant_id=auth.tenant_id, provider=provider)


@router.patch(
    "/{provider_id}",
    response_model=ProviderConfigResponse,
    dependencies=[Depends(require_permissions("providers:write"))],
)
def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderConfigUpdateRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderConfigResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    values = payload.model_dump(exclude_none=True, exclude={"api_key"})
    service = ProviderManagementService(db)
    provider = service.update_provider(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
        values=values,
        api_key=payload.api_key,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to update provider config.",
        context={"tenant_id": str(auth.tenant_id), "provider_id": str(provider_id)},
    )
    return _provider_config_response(service, tenant_id=auth.tenant_id, provider=provider)


@router.delete(
    "/{provider_id}",
    response_model=ProviderDeleteResponse,
    dependencies=[Depends(require_permissions("providers:write"))],
)
def delete_provider(
    provider_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderDeleteResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = ProviderManagementService(db)
    status = service.delete_or_disable_provider(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to delete or disable provider config.",
        context={"tenant_id": str(auth.tenant_id), "provider_id": str(provider_id)},
    )
    return ProviderDeleteResponse(provider_id=provider_id, status=status)


@router.post(
    "/{provider_id}/test",
    response_model=ProviderTestResponse,
    dependencies=[Depends(require_permissions("providers:test"))],
)
def test_provider(
    provider_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderTestResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = ProviderModelsService(db, ProviderRegistry(settings)).test_provider(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to test provider.",
        context={"tenant_id": str(auth.tenant_id), "provider_id": str(provider_id)},
    )
    return ProviderTestResponse(
        provider_id=str(provider_id),
        status=row.status,
        latency_ms=row.latency_ms,
        http_status=row.http_status,
        error_code=row.error_code,
        error_message_redacted=row.error_message_redacted,
        metadata_json=dict(row.metadata_json or {}),
        checked_at=row.checked_at,
    )


@router.get(
    "/{provider_id}/health",
    response_model=ProviderHealthResponse,
    dependencies=[Depends(require_permissions("providers:read"))],
)
def get_provider_health(
    provider_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderHealthResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    ProviderManagementService(db).get_provider(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
    )
    service = ProviderHealthService(db, ProviderRegistry(settings))
    row = service.latest(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
    )
    if row is None:
        raise ApiError(
            code="PROVIDER_HEALTH_CHECK_FAILED",
            message="Provider health has not been checked yet.",
            status_code=404,
        )
    response = _health_response(row)
    if response is None:
        raise ApiError(
            code="PROVIDER_HEALTH_CHECK_FAILED",
            message="Provider health has not been checked yet.",
            status_code=404,
        )
    return response


@router.post(
    "/{provider_id}/models/refresh",
    response_model=ProviderModelListResponse,
    dependencies=[Depends(require_permissions("providers:test"))],
)
def refresh_provider_models(
    provider_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderModelListResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    # Read the provider metadata while the request tenant context is active.
    # ``_commit_or_rollback`` commits the transaction, which intentionally
    # clears the transaction-local RLS setting.  Looking the provider up only
    # after that commit can make PostgreSQL evaluate the RLS UUID cast against
    # an empty setting and fail with ``invalid input syntax for type uuid``.
    provider = db.get(ProviderConfig, provider_id)
    provider_type = provider.provider_type if provider is not None else None
    models_service = ProviderModelsService(db, ProviderRegistry(settings))
    rows = models_service.refresh_models(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to refresh provider models.",
        context={"tenant_id": str(auth.tenant_id), "provider_id": str(provider_id)},
    )
    return ProviderModelListResponse(
        items=[_model_response(row, provider_type=provider_type) for row in rows]
    )


@router.get(
    "/{provider_id}/models",
    response_model=ProviderModelListResponse,
    dependencies=[Depends(require_permissions("providers:read"))],
)
def list_provider_models(
    provider_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderModelListResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    models_service = ProviderModelsService(db, ProviderRegistry(settings))
    rows = models_service.list_models(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
    )
    provider = db.get(ProviderConfig, provider_id)
    provider_type = provider.provider_type if provider is not None else None
    return ProviderModelListResponse(
        items=[_model_response(row, provider_type=provider_type) for row in rows]
    )


@router.post(
    "/{provider_id}/models/pull",
    response_model=ProviderModelPullResponse,
    dependencies=[Depends(require_permissions("providers:write"))],
)
def pull_provider_model(
    provider_id: uuid.UUID,
    payload: ProviderModelPullRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderModelPullResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    model_name = ProviderModelsService(db, ProviderRegistry(settings)).pull_model(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        model_name=payload.model_name,
        actor_user_id=auth.user_id,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to pull provider model.",
        context={"tenant_id": str(auth.tenant_id), "provider_id": str(provider_id)},
    )
    return ProviderModelPullResponse(
        status="accepted", message=f"Model {model_name} pull requested."
    )


@router.post(
    "/oauth/openai/start",
    response_model=ProviderOAuthStartResponse,
    dependencies=[Depends(require_permissions("providers:oauth"))],
)
def start_openai_oauth(
    payload: ProviderOAuthStartRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderOAuthStartResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    if payload.provider_type != "openai":
        raise ApiError(
            code="PROVIDER_OAUTH_UNSUPPORTED",
            message="OAuth is only defined for OpenAI/Codex in this phase.",
            status_code=400,
        )
    available, authorization_url, message = ProviderOAuthService(db, settings).start(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to initialize provider OAuth flow.",
        context={"tenant_id": str(auth.tenant_id), "provider_type": "openai"},
    )
    return ProviderOAuthStartResponse(
        available=available,
        authorization_url=authorization_url,
        message=message,
    )


@router.get("/oauth/openai/callback", response_model=ProviderOAuthCallbackResponse)
def openai_oauth_callback(
    code: str | None = OPTIONAL_CODE_QUERY,
    state: str | None = OPTIONAL_STATE_QUERY,
    tenant_id: uuid.UUID | None = OPTIONAL_TENANT_QUERY,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderOAuthCallbackResponse:
    if tenant_id is None:
        raise ApiError(
            code="TENANT_REQUIRED",
            message="tenant_id query parameter is required for OAuth callback handling.",
            status_code=400,
        )
    connected, message = ProviderOAuthService(db, settings).callback(
        tenant_id=tenant_id,
        actor_user_id=None,
        code=code,
        state=state,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to handle provider OAuth callback.",
        context={"tenant_id": str(tenant_id), "provider_type": "openai"},
    )
    return ProviderOAuthCallbackResponse(connected=connected, message=message)


@router.get(
    "/oauth/openai/status",
    response_model=ProviderOAuthStatusResponse,
    dependencies=[Depends(require_permissions("providers:oauth"))],
)
def openai_oauth_status(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProviderOAuthStatusResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = ProviderOAuthService(db, settings)
    available, message = service.status(tenant_id=auth.tenant_id)
    return ProviderOAuthStatusResponse(
        available=available,
        connected=service.connected(tenant_id=auth.tenant_id),
        provider_type="openai",
        message=message,
    )


@router.post(
    "/{provider_id}/disconnect",
    response_model=ProviderDisconnectResponse,
    dependencies=[Depends(require_permissions("providers:write"))],
)
def disconnect_provider(
    provider_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderDisconnectResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    count = ProviderManagementService(db).disconnect_provider(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to disconnect provider.",
        context={"tenant_id": str(auth.tenant_id), "provider_id": str(provider_id)},
    )
    return ProviderDisconnectResponse(provider_id=str(provider_id), revoked_secret_count=count)


@router.post(
    "/{provider_id}/refresh-token",
    dependencies=[Depends(require_permissions("providers:oauth"))],
)
def refresh_provider_token(
    provider_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderDisconnectResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    ProviderManagementService(db).get_provider(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        actor_user_id=auth.user_id,
    )
    raise ApiError(
        code="PROVIDER_OAUTH_UNSUPPORTED",
        message="Provider token refresh is not available until officially supported and implemented.",
        status_code=400,
    )


@router.post(
    "/{provider_id}/rotate-secret",
    response_model=ProviderDisconnectResponse,
    dependencies=[Depends(require_permissions("providers:write"))],
)
def rotate_provider_secret(
    provider_id: uuid.UUID,
    payload: ProviderRotateSecretRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ProviderDisconnectResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    ProviderManagementService(db).rotate_secret(
        tenant_id=auth.tenant_id,
        provider_config_id=provider_id,
        secret_type=payload.secret_type,
        secret_value=payload.secret_value,
        actor_user_id=auth.user_id,
    )
    _commit_or_rollback(
        db=db,
        message="Failed to rotate provider secret.",
        context={"tenant_id": str(auth.tenant_id), "provider_id": str(provider_id)},
    )
    return ProviderDisconnectResponse(provider_id=str(provider_id), revoked_secret_count=0)
