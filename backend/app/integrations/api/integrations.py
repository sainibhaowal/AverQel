from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.config import get_settings
from app.core.errors import ApiError
from app.auth.rbac import require_permissions
from app.db.session import get_db
from app.documents.models.document import Document
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.connector_secret import ConnectorSecret
from app.integrations.models.integration import Integration
from app.system.models.audit_log import AuditLog
from app.documents.schemas.documents import DocumentMetadataResponse
from app.integrations.schemas.connectors import (
    ConnectorCreate,
    ConnectorFleetSummary,
    ConnectorOAuthStartResponse,
    ConnectorRead,
    ConnectorSummary,
    ConnectorSyncAuditEntry,
    IntegrationRead,
    SyncResult,
)
from app.integrations.services.connector_oauth_service import ConnectorOAuthService
from app.integrations.services.connector_orchestrator import ConnectorOrchestrator
from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _seconds_since(value: datetime | None) -> int | None:
    if value is None:
        return None
    delta = datetime.now(tz=UTC) - value
    return max(0, int(delta.total_seconds()))


def _connector_retry_state(
    *,
    connector: Connector,
    health: dict[str, Any],
    sync_checkpoint: dict[str, Any],
) -> str:
    if sync_checkpoint.get("retryable") is False:
        return "blocked"

    retry_after_at = Connector._parse_iso_datetime(
        sync_checkpoint.get("retry_after_at")
    )
    if retry_after_at is None:
        if connector.status == ConnectorStatus.SYNCING:
            return "scheduled"
        if connector.status in {ConnectorStatus.PAUSED, ConnectorStatus.ERROR}:
            return "blocked"
        return "none"

    if retry_after_at <= datetime.now(tz=UTC):
        return "due"
    return "waiting"


def _increment_counter(breakdown: dict[str, int], key: str | None) -> None:
    normalized = str(key or "").strip().lower()
    if not normalized:
        normalized = "unknown"
    breakdown[normalized] = breakdown.get(normalized, 0) + 1


def _schedule_oauth_sync(connector_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        ConnectorOrchestrator(session).sync_connector(connector_id, tenant_id)


@router.get("", response_model=list[IntegrationRead])
def list_integrations(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[IntegrationRead]:
    """List all available integration types."""
    result = session.execute(select(Integration).where(Integration.is_active))
    service = ConnectorOAuthService(session, get_settings())
    integrations = []
    for integration in result.scalars().all():
        payload = IntegrationRead.model_validate(integration).model_dump()
        payload["oauth_status"] = service.readiness(integration=integration)
        integrations.append(IntegrationRead.model_validate(payload))
    return integrations


@router.get("/connectors", response_model=list[ConnectorRead])
def list_connectors(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[ConnectorRead]:
    """List all active connectors for the current tenant."""
    result = session.execute(
        select(Connector).where(Connector.tenant_id == auth.tenant_id)
    )
    return [
        ConnectorRead.model_validate(connector) for connector in result.scalars().all()
    ]


@router.get("/connectors/summary", response_model=ConnectorFleetSummary)
def connector_fleet_summary(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ConnectorFleetSummary:
    """Return a tenant-level connector fleet summary for operations visibility."""
    connectors = (
        session.execute(select(Connector).where(Connector.tenant_id == auth.tenant_id))
        .scalars()
        .all()
    )
    recent_audit_count = session.execute(
        select(AuditLog.id).where(
            AuditLog.tenant_id == auth.tenant_id,
            AuditLog.resource_type == "connector",
        )
    ).all()

    status_breakdown: dict[str, int] = {}
    integration_breakdown: dict[str, int] = {}
    error_domain_breakdown: dict[str, int] = {}
    health_status_breakdown: dict[str, int] = {}
    retry_state_breakdown: dict[str, int] = {}
    attention_connectors: list[dict[str, Any]] = []
    active_count = syncing_count = paused_count = error_count = healthy_count = 0
    stale_count = retryable_count = due_sync_count = 0
    now = datetime.now(tz=UTC)

    for connector in connectors:
        status_value = str(getattr(connector.status, "value", connector.status)).lower()
        status_breakdown[status_value] = status_breakdown.get(status_value, 0) + 1
        integration = connector.integration.slug if connector.integration else "unknown"
        integration_breakdown[integration] = (
            integration_breakdown.get(integration, 0) + 1
        )
        health = connector.health_contract()
        health_status = (
            str(health.get("status") or status_value).strip().lower() or "unknown"
        )
        _increment_counter(health_status_breakdown, health_status)
        if status_value == "active":
            active_count += 1
        elif status_value == "syncing":
            syncing_count += 1
        elif status_value == "paused":
            paused_count += 1
        elif status_value == "error":
            error_count += 1

        if bool(health.get("healthy")):
            healthy_count += 1
        if str(health.get("status") or "").lower() == "stale":
            stale_count += 1
        sync_checkpoint = dict(connector.config or {}).get(
            Connector.SYNC_CHECKPOINT_CONFIG_KEY
        )
        if isinstance(sync_checkpoint, dict):
            if bool(sync_checkpoint.get("retryable")):
                retryable_count += 1
            retry_after_at = Connector._parse_iso_datetime(
                sync_checkpoint.get("retry_after_at")
            )
            if retry_after_at is not None and retry_after_at <= now:
                due_sync_count += 1
            error_domain = str(sync_checkpoint.get("error_domain") or "").strip()
            if error_domain:
                error_domain_breakdown[error_domain] = (
                    error_domain_breakdown.get(error_domain, 0) + 1
                )
        else:
            sync_checkpoint = {}
        retry_state = _connector_retry_state(
            connector=connector,
            health=health,
            sync_checkpoint=sync_checkpoint,
        )
        _increment_counter(retry_state_breakdown, retry_state)
        health_age_seconds = _seconds_since(connector.last_checked_at)
        checkpoint_age_seconds = _seconds_since(
            Connector._parse_iso_datetime(sync_checkpoint.get("updated_at"))
        )
        if health.get("status") not in {"healthy", None} or retry_state != "none":
            attention_connectors.append(
                {
                    "id": str(connector.id),
                    "name": connector.name,
                    "integration_slug": integration,
                    "status": status_value,
                    "live_status": str(health.get("status") or status_value),
                    "retry_state": retry_state,
                    "retryable": (
                        bool(sync_checkpoint.get("retryable"))
                        if sync_checkpoint
                        else None
                    ),
                    "retry_after_at": (
                        Connector._parse_iso_datetime(
                            sync_checkpoint.get("retry_after_at")
                        )
                        if sync_checkpoint
                        else None
                    ),
                    "retry_after_seconds": (
                        (
                            ConnectorOrchestrator._retry_after_seconds(
                                str(sync_checkpoint.get("retry_after_at"))
                            )
                            if sync_checkpoint.get("retry_after_at")
                            else None
                        )
                        if sync_checkpoint
                        else None
                    ),
                    "health_age_seconds": health_age_seconds,
                    "sync_checkpoint_age_seconds": checkpoint_age_seconds,
                    "error_domain": (
                        (str(sync_checkpoint.get("error_domain") or "").strip() or None)
                        if sync_checkpoint
                        else None
                    ),
                }
            )

    attention_connectors = attention_connectors[:8]
    daemon_heartbeat = None
    try:
        from app.services.deepspace.subagents.subagent_registry import SubagentRegistry

        daemon_heartbeat = SubagentRegistry().get_daemon_heartbeat()
    except Exception:
        daemon_heartbeat = None

    return ConnectorFleetSummary(
        total_connectors=len(connectors),
        active_count=active_count,
        syncing_count=syncing_count,
        paused_count=paused_count,
        error_count=error_count,
        healthy_count=healthy_count,
        stale_count=stale_count,
        retryable_count=retryable_count,
        due_sync_count=due_sync_count,
        recent_audit_count=len(recent_audit_count),
        status_breakdown=status_breakdown,
        integration_breakdown=integration_breakdown,
        error_domain_breakdown=error_domain_breakdown,
        health_status_breakdown=health_status_breakdown,
        retry_state_breakdown=retry_state_breakdown,
        attention_connectors=attention_connectors,
        daemon_heartbeat=daemon_heartbeat,
    )


@router.post("/connectors", response_model=ConnectorRead)
def create_connector(
    payload: ConnectorCreate,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ConnectorRead:
    """Create a new connector and store encrypted credentials."""
    # Verify integration exists
    integration = session.get(Integration, payload.integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    connector = Connector(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        integration_id=payload.integration_id,
        collection_id=payload.collection_id,
        name=payload.name,
        config=payload.config,
        sync_frequency=payload.sync_frequency,
    )
    session.add(connector)
    session.flush()  # Get connector ID

    # Store credentials if provided
    if payload.credentials:
        crypto = ConnectorSecretCrypto()
        for key, value in payload.credentials.items():
            encrypted = crypto.encrypt(value, aad=str(auth.tenant_id).encode())
            secret = ConnectorSecret(
                connector_id=connector.id,
                tenant_id=auth.tenant_id,
                secret_ciphertext=encrypted.ciphertext,
                secret_nonce=encrypted.nonce,
                secret_kid=encrypted.kid,
                secret_type=key,
            )
            session.add(secret)

    session.commit()
    session.refresh(connector)
    return ConnectorRead.model_validate(connector)


@router.post(
    "/connectors/{connector_id}/oauth/start",
    response_model=ConnectorOAuthStartResponse,
    dependencies=[Depends(require_permissions("providers:oauth"))],
)
def start_connector_oauth(
    connector_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ConnectorOAuthStartResponse:
    """Start the OAuth flow for an OAuth-capable connector."""
    connector = session.get(Connector, connector_id)
    if not connector or connector.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Connector not found")

    integration = session.get(Integration, connector.integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    service = ConnectorOAuthService(session, get_settings())
    available, authorization_url, message = service.start(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        connector_id=connector_id,
    )
    return ConnectorOAuthStartResponse(
        available=available,
        authorization_url=authorization_url,
        message=message,
        connector_id=connector_id,
        integration_slug=integration.slug,
    )


@router.get("/connectors/oauth/callback")
async def connector_oauth_callback(
    background_tasks: BackgroundTasks,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    session: Session = Depends(get_db),
) -> RedirectResponse:
    """Handle OAuth callbacks for connector account linking."""
    settings = get_settings()
    frontend_base = (
        (settings.connector_oauth_frontend_redirect_uri or "").strip().rstrip("/")
    )
    redirect_base = frontend_base or "/dashboard/connectors"

    if error:
        redirect_url = f"{redirect_base}?oauth=error&message={error}" + (
            f"&description={error_description}" if error_description else ""
        )
        return RedirectResponse(url=redirect_url, status_code=302)

    try:
        connector = await ConnectorOAuthService(session, settings).callback(
            code=code, state=state
        )
    except ApiError as exc:
        redirect_url = f"{redirect_base}?oauth=error&message={exc.message}"
        return RedirectResponse(url=redirect_url, status_code=302)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "OAuth callback failed."
        redirect_url = f"{redirect_base}?oauth=error&message={detail}"
        return RedirectResponse(url=redirect_url, status_code=302)

    redirect_url = (
        f"{redirect_base}?oauth=connected&connector_id={connector.id}"
        f"&integration_id={connector.integration_id}"
    )
    background_tasks.add_task(_schedule_oauth_sync, connector.id, connector.tenant_id)
    return RedirectResponse(
        url=redirect_url, status_code=302, background=background_tasks
    )


@router.post("/connectors/{connector_id}/sync", response_model=SyncResult)
def trigger_sync(
    connector_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> SyncResult:
    """Manually trigger a connector sync."""
    connector = session.get(Connector, connector_id)
    if not connector or connector.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Use a fresh orchestrator inside the task to avoid session closure issues
    logger.info(
        f"🔄 Handing off sync for connector {connector_id} to background worker..."
    )
    orchestrator = ConnectorOrchestrator(session)
    background_tasks.add_task(orchestrator.sync_connector, connector_id, auth.tenant_id)

    return SyncResult(status="accepted", message="Sync job queued in background")


@router.get("/connectors/{connector_id}/summary", response_model=ConnectorSummary)
def connector_summary(
    connector_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ConnectorSummary:
    """Return a live connector summary for operator visibility."""
    connector = session.get(Connector, connector_id)
    if not connector or connector.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Connector not found")

    connector_read = ConnectorRead.model_validate(connector)
    health = connector.health_contract()
    sync_checkpoint = dict(connector.config or {}).get(
        Connector.SYNC_CHECKPOINT_CONFIG_KEY
    )
    if not isinstance(sync_checkpoint, dict):
        sync_checkpoint = {}
    retry_state = _connector_retry_state(
        connector=connector,
        health=health,
        sync_checkpoint=sync_checkpoint,
    )
    retry_after_at = sync_checkpoint.get("retry_after_at")
    retry_after_seconds = (
        ConnectorOrchestrator._retry_after_seconds(str(retry_after_at))
        if retry_after_at
        else None
    )
    health_age_seconds = _seconds_since(connector.last_checked_at)
    sync_checkpoint_age_seconds = _seconds_since(
        Connector._parse_iso_datetime(sync_checkpoint.get("updated_at"))
    )

    audit = (
        session.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == auth.tenant_id,
                AuditLog.resource_type == "connector",
                AuditLog.resource_id == str(connector_id),
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    recent_audit_count = session.execute(
        select(AuditLog.id).where(
            AuditLog.tenant_id == auth.tenant_id,
            AuditLog.resource_type == "connector",
            AuditLog.resource_id == str(connector_id),
        )
    ).all()
    last_sync_audit = None
    if audit is not None:
        last_sync_audit = {
            "id": str(audit.id),
            "action": audit.action,
            "status": audit.status,
            "resource_type": audit.resource_type,
            "resource_id": audit.resource_id,
            "details": dict(audit.details or {}),
            "created_at": audit.created_at,
        }

    retryable = sync_checkpoint.get("retryable")
    retry_after_at = sync_checkpoint.get("retry_after_at")
    retry_after_seconds = sync_checkpoint.get("retry_after_seconds")
    error_domain = sync_checkpoint.get("error_domain")
    live_status = (
        str(sync_checkpoint.get("status") or connector.status.value).strip().lower()
    )
    if health:
        live_status = str(health.get("status") or live_status).strip().lower()

    return ConnectorSummary(
        connector=connector_read,
        health=health,
        sync_checkpoint=sync_checkpoint,
        last_sync_audit=last_sync_audit,
        live_status=live_status,
        retry_state=retry_state,
        retryable=bool(retryable) if retryable is not None else None,
        retry_after_at=Connector._parse_iso_datetime(retry_after_at),
        retry_after_seconds=(
            int(retry_after_seconds) if retry_after_seconds is not None else None
        ),
        error_domain=str(error_domain) if error_domain else None,
        health_age_seconds=health_age_seconds,
        sync_checkpoint_age_seconds=sync_checkpoint_age_seconds,
        recent_audit_count=len(recent_audit_count),
    )


@router.get(
    "/connectors/{connector_id}/sync-history",
    response_model=list[ConnectorSyncAuditEntry],
)
def connector_sync_history(
    connector_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[ConnectorSyncAuditEntry]:
    """Return recent sync audit history for a connector."""
    connector = session.get(Connector, connector_id)
    if not connector or connector.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Connector not found")

    audits = (
        session.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == auth.tenant_id,
                AuditLog.resource_type == "connector",
                AuditLog.resource_id == str(connector_id),
                AuditLog.action == "connector_sync",
            )
            .order_by(AuditLog.created_at.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    def _optional_int(value: Any) -> int | None:
        return int(value) if value is not None else None

    history: list[ConnectorSyncAuditEntry] = []
    for audit in audits:
        details = dict(audit.details or {})
        history.append(
            ConnectorSyncAuditEntry(
                id=audit.id,
                action=audit.action,
                status=audit.status,
                phase=(
                    str(details.get("phase"))
                    if details.get("phase") is not None
                    else None
                ),
                error_code=(
                    str(details.get("error_code"))
                    if details.get("error_code") is not None
                    else None
                ),
                error_domain=(
                    str(details.get("error_domain"))
                    if details.get("error_domain") is not None
                    else None
                ),
                retryable=(
                    bool(details.get("retryable"))
                    if details.get("retryable") is not None
                    else None
                ),
                retry_after_at=Connector._parse_iso_datetime(
                    details.get("retry_after_at")
                ),
                retry_after_seconds=_optional_int(details.get("retry_after_seconds")),
                attempt=_optional_int(details.get("attempt")),
                duration_ms=_optional_int(details.get("duration_ms")),
                details=details,
                created_at=audit.created_at,
            )
        )
    return history


@router.patch("/connectors/{connector_id}", response_model=ConnectorRead)
def update_connector(
    connector_id: uuid.UUID,
    payload: dict[str, Any],
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ConnectorRead:
    """Update connector configuration or name."""
    connector = session.get(Connector, connector_id)
    if not connector or connector.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Connector not found")

    if "name" in payload:
        connector.name = payload["name"]
    if "config" in payload:
        connector.config.update(payload["config"])
    if "sync_frequency" in payload:
        connector.sync_frequency = payload["sync_frequency"]

    session.commit()
    session.refresh(connector)
    return ConnectorRead.model_validate(connector)


@router.delete("/connectors/{connector_id}")
def delete_connector(
    connector_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, str]:
    """Permanently delete a connector and its secrets."""
    connector = session.get(Connector, connector_id)
    if not connector or connector.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Delete secrets first
    session.execute(
        select(ConnectorSecret).where(ConnectorSecret.connector_id == connector_id)
    )
    # The secrets should ideally be deleted via relationship cascade or manually
    secrets = (
        session.execute(
            select(ConnectorSecret).where(ConnectorSecret.connector_id == connector_id)
        )
        .scalars()
        .all()
    )
    for secret in secrets:
        session.delete(secret)

    session.delete(connector)
    session.commit()
    return {"status": "success", "message": "Connector deleted successfully"}


@router.get(
    "/connectors/{connector_id}/documents",
    response_model=list[DocumentMetadataResponse],
)
def list_connector_documents(
    connector_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[DocumentMetadataResponse]:
    """List recent documents ingested by this connector."""
    # Verify connector exists and belongs to tenant
    connector = session.get(Connector, connector_id)
    if not connector or connector.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Connector not found")

    result = session.execute(
        select(Document)
        .where(Document.connector_id == connector_id)
        .order_by(Document.created_at.desc())
        .limit(10)
    )
    return [
        DocumentMetadataResponse.model_validate(document)
        for document in result.scalars().all()
    ]
