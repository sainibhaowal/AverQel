import hashlib
import logging
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.db.session import get_session_factory, set_db_tenant_context
from app.models.deepspace.agent_activity import AgentActivity
from app.documents.models.collection_notification import CollectionNotification
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.connector_secret import ConnectorSecret
from app.integrations.models.integration import Integration
from app.documents.repositories.collection_notifications import (
    CollectionNotificationsRepository,
)
from app.services.deepspace.memory.memory_service import TodoService
from app.ingestion.services.ingestion_service import IngestionService
from app.integrations.services.connector_service import ConnectorService
from app.integrations.services.health_utils import (
    ConnectorHealthStatus,
    backoff_seconds,
    build_health_report,
    classify_health_status,
    future_iso,
    now_iso,
)
from app.integrations.services.mcp_runtime import UniversalMCPConnector
from app.integrations.services.web.web_connector import WebConnector
from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto
from app.services.system.audit_service import AuditService

logger = logging.getLogger(__name__)


def _notify_user(
    *,
    session: Session,
    recipient_user_id: uuid.UUID,
    message: str,
    event_type: str = "agent_intervention",
    collection_name: str = "AverQel Proactive",
    actor_user_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> None:
    CollectionNotificationsRepository(session).create(
        CollectionNotification(
            recipient_user_id=recipient_user_id,
            actor_user_id=actor_user_id,
            collection_name=collection_name,
            event_type=event_type,
            idempotency_key=idempotency_key
            or hashlib.sha256(
                "|".join(
                    [
                        str(recipient_user_id),
                        str(actor_user_id or ""),
                        collection_name,
                        event_type,
                        message,
                    ]
                ).encode("utf-8")
            ).hexdigest(),
            message=message,
        )
    )


class ConnectorOrchestrator:
    """
    Main entry point for running connector syncs.
    Maps integration types to their respective services.
    """

    _REGISTRY: dict[str, type[ConnectorService]] = {
        "web-crawler": WebConnector,
        "google-drive": UniversalMCPConnector,
        "github": UniversalMCPConnector,
        "slack": UniversalMCPConnector,
        "notion": UniversalMCPConnector,
        "gmail": UniversalMCPConnector,
        "google-calendar": UniversalMCPConnector,
    }

    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()
        self.audit = AuditService(session)

    @staticmethod
    def _emit_progress(
        progress_callback: Any | None,
        *,
        phase: str,
        message: str,
        **extra: Any,
    ) -> None:
        if not callable(progress_callback):
            return
        try:
            progress_callback({"phase": phase, "message": message, **extra})
        except Exception:
            logger.debug("Connector progress callback failed", exc_info=True)

    @staticmethod
    def _parse_health_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _connector_health_state(self, connector: Connector) -> dict[str, Any]:
        config = connector.config if isinstance(connector.config, dict) else {}
        health = config.get(Connector.HEALTH_CONFIG_KEY)
        return dict(health) if isinstance(health, dict) else {}

    def _last_success_snapshot(self, connector: Connector) -> dict[str, Any] | None:
        config = connector.config if isinstance(connector.config, dict) else {}
        snapshot = config.get(Connector.LAST_SUCCESS_SNAPSHOT_KEY)
        return dict(snapshot) if isinstance(snapshot, dict) else None

    def _health_circuit_open(self, connector: Connector) -> bool:
        circuit_open_until = self._parse_health_datetime(
            self._connector_health_state(connector).get("circuit_open_until")
        )
        return bool(circuit_open_until and circuit_open_until > datetime.now(tz=UTC))

    @staticmethod
    def _apply_tenant_context(session: Session, tenant_id: uuid.UUID) -> None:
        set_db_tenant_context(session, tenant_id)

    @staticmethod
    def _normalize_health_report(report: Any) -> dict[str, Any]:
        if not isinstance(report, dict):
            report = {}
        healthy = bool(report.get("healthy"))
        raw_status = (
            str(report.get("status") or ("healthy" if healthy else "degraded"))
            .strip()
            .lower()
        )
        status: ConnectorHealthStatus = cast(
            ConnectorHealthStatus,
            (
                raw_status
                if raw_status
                in {"healthy", "degraded", "auth_expired", "offline", "stale"}
                else ("healthy" if healthy else "degraded")
            ),
        )
        metadata = report.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "healthy": healthy,
            "status": status,
            "error_code": report.get("error_code"),
            "error_message": report.get("error_message") or report.get("message"),
            "http_status": report.get("http_status"),
            "metadata": metadata,
            "checked_at": str(report.get("checked_at") or now_iso()),
            "last_good_at": report.get("last_good_at"),
            "circuit_open_until": report.get("circuit_open_until"),
            "consecutive_failures": int(report.get("consecutive_failures") or 0),
            "latency_ms": report.get("latency_ms"),
        }

    def _apply_health_report(
        self,
        *,
        connector: Connector,
        integration_slug: str,
        report: Any,
        phase: str,
    ) -> dict[str, Any]:
        normalized = self._normalize_health_report(report)
        current_health = self._connector_health_state(connector)
        checked_at = normalized["checked_at"]
        metadata = dict(current_health.get("metadata") or {})
        metadata.update(normalized.get("metadata") or {})

        if normalized["healthy"]:
            consecutive_failures = 0
            circuit_open_until = None
            last_good_at = checked_at
            connector.status = ConnectorStatus.ACTIVE
            connector.last_error = None
            connector.error_count = 0
        else:
            consecutive_failures = max(
                1, int(current_health.get("consecutive_failures") or 0) + 1
            )
            circuit_open_until = future_iso(backoff_seconds(consecutive_failures))
            last_good_at = current_health.get("last_good_at")
            connector.error_count = consecutive_failures
            connector.last_error = (
                normalized["error_message"] or normalized["error_code"]
            )
            connector.status = (
                ConnectorStatus.ERROR
                if normalized["status"] == "auth_expired"
                else ConnectorStatus.PAUSED
            )

        health_contract = {
            "status": normalized["status"],
            "healthy": normalized["healthy"],
            "last_checked_at": checked_at,
            "last_good_at": last_good_at,
            "circuit_open_until": circuit_open_until,
            "consecutive_failures": consecutive_failures,
            "last_error_code": normalized["error_code"],
            "last_error_message": normalized["error_message"],
            "http_status": normalized["http_status"],
            "latency_ms": normalized["latency_ms"],
            "metadata": {
                **metadata,
                "integration_slug": integration_slug,
                "phase": phase,
            },
        }
        config = dict(connector.config or {})
        config[Connector.HEALTH_CONFIG_KEY] = health_contract
        connector.config = config
        return health_contract

    def _decorate_with_cached_snapshot(
        self,
        *,
        connector: Connector,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = self._last_success_snapshot(connector)
        if not snapshot:
            return report

        decorated = dict(report)
        metadata = dict(decorated.get("metadata") or {})
        metadata.update(
            {
                "has_fallback_snapshot": True,
                "fallback_mode": "last_success_snapshot",
                "last_success_snapshot_document_id": snapshot.get("document_id"),
                "last_success_snapshot_title": snapshot.get("title"),
                "last_success_snapshot_synced_at": snapshot.get("synced_at"),
            }
        )
        decorated["metadata"] = metadata
        if not decorated.get("healthy"):
            decorated["status"] = "stale"
        return decorated

    def _persist_success_snapshot(
        self,
        *,
        connector: Connector,
        integration_slug: str,
        result: dict[str, Any],
        document_id: Any | None,
    ) -> dict[str, Any]:
        snapshot = {
            "integration_slug": integration_slug,
            "document_id": str(document_id) if document_id is not None else None,
            "filename": result.get("filename"),
            "title": result.get("title") or connector.name,
            "summary": result.get("summary") or result.get("description"),
            "hash": result.get("hash"),
            "synced_at": now_iso(),
        }
        config = dict(connector.config or {})
        config[Connector.LAST_SUCCESS_SNAPSHOT_KEY] = snapshot
        connector.config = config
        return snapshot

    def _update_sync_checkpoint(
        self,
        *,
        connector: Connector,
        integration_slug: str,
        run_id: str,
        phase: str,
        attempt: int = 1,
        status: str = "running",
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool | None = None,
        retry_after_at: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checkpoint = {
            "run_id": run_id,
            "connector_id": str(connector.id),
            "connector_name": connector.name,
            "integration_slug": integration_slug,
            "phase": phase,
            "status": status,
            "attempt": attempt,
            "updated_at": now_iso(),
            "error_code": error_code,
            "error_message": error_message,
            "retryable": retryable,
            "retry_after_at": retry_after_at,
            **dict(extra or {}),
        }
        config = dict(connector.config or {})
        config[Connector.SYNC_CHECKPOINT_CONFIG_KEY] = checkpoint
        connector.config = config
        self.session.flush()
        return checkpoint

    @staticmethod
    def _compute_retry_after_at(*, attempt: int | None) -> str | None:
        if attempt is None:
            return None
        delay_seconds = min(15 * 60, max(30, 30 * (2 ** max(0, int(attempt) - 1))))
        return future_iso(delay_seconds)

    @staticmethod
    def _retry_after_seconds(retry_after_at: str | None) -> int | None:
        if not retry_after_at:
            return None
        parsed = ConnectorOrchestrator._parse_health_datetime(retry_after_at)
        if parsed is None:
            return None
        remaining = int((parsed - datetime.now(tz=UTC)).total_seconds())
        return max(0, remaining)

    @staticmethod
    def _sync_error_domain(
        *, error_code: str | None, phase: str | None, retryable: bool | None = None
    ) -> str:
        normalized_code = str(error_code or "").strip().lower()
        normalized_phase = str(phase or "").strip().lower()
        if normalized_code in {"credential_decryption_failed"}:
            return "credentials"
        if normalized_code in {"integration_not_found", "integration_service_missing"}:
            return "configuration"
        if normalized_code in {"validation_failed", "invalid_config"}:
            return "validation"
        if normalized_code in {"auth_expired", "unauthorized"}:
            return "authorization"
        if normalized_code in {
            "connectivity_failure",
            "rate_limited",
            "provider_timeout",
            "temporary_failure",
        }:
            return "upstream"
        if normalized_phase in {"credentials"}:
            return "credentials"
        if normalized_phase in {"sync_preflight"}:
            return "health"
        if normalized_phase in {"fetch"}:
            return "fetch"
        if normalized_phase in {"ingest", "finalize", "sync_error"}:
            return "execution" if retryable is not False else "execution"
        return "unknown"

    @staticmethod
    def _is_retryable_connector_error(error_code: str | None) -> bool:
        return str(error_code or "") in {
            "connectivity_failure",
            "rate_limited",
            "provider_timeout",
            "temporary_failure",
        }

    @staticmethod
    def _build_sync_response(
        *,
        status: str,
        message: str,
        run_id: str | None,
        phase: str | None = None,
        attempt: int | None = None,
        duration_ms: int | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        error_code: str | None = None,
        retryable: bool | None = None,
        retry_after_at: str | None = None,
        health: dict[str, Any] | None = None,
        fallback_snapshot: dict[str, Any] | None = None,
        document_id: Any | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            "status": status,
            "message": message,
            "sync": {
                "run_id": run_id,
                "phase": phase,
                "attempt": attempt,
                "duration_ms": duration_ms,
                "started_at": started_at,
                "completed_at": completed_at,
                "error_code": error_code,
                "retryable": retryable,
                "retry_after_at": retry_after_at,
                "retry_after_seconds": ConnectorOrchestrator._retry_after_seconds(
                    retry_after_at
                ),
                "error_domain": ConnectorOrchestrator._sync_error_domain(
                    error_code=error_code, phase=phase, retryable=retryable
                ),
            },
        }
        if health is not None:
            response["health"] = health
        if fallback_snapshot is not None:
            response["fallback_snapshot"] = fallback_snapshot
        if document_id is not None:
            response["document_id"] = document_id
        if extra:
            nested_sync = extra.pop("sync", None)
            response.update(extra)
            if isinstance(nested_sync, dict):
                response.setdefault("sync", {}).update(nested_sync)
                sync_payload = response.setdefault("sync", {})
                if sync_payload.get("retry_after_at") is not None:
                    sync_payload["retry_after_seconds"] = (
                        ConnectorOrchestrator._retry_after_seconds(
                            str(sync_payload.get("retry_after_at"))
                        )
                    )
        return response

    @staticmethod
    def _build_sync_error_metadata(
        *,
        connector: Connector,
        integration_slug: str,
        run_id: str,
        phase: str,
        error_code: str | None,
        retryable: bool | None,
        attempt: int | None = None,
        health: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "connector_id": str(connector.id),
            "connector_name": connector.name,
            "integration_slug": integration_slug,
            "run_id": run_id,
            "phase": phase,
            "error_code": error_code,
            "retryable": retryable,
        }
        if attempt is not None:
            metadata["attempt"] = attempt
        metadata["error_domain"] = ConnectorOrchestrator._sync_error_domain(
            error_code=error_code, phase=phase, retryable=retryable
        )
        if health is not None:
            metadata["health"] = health
        return metadata

    def _write_sync_audit_event(
        self,
        *,
        connector: Connector,
        integration_slug: str,
        run_id: str,
        phase: str,
        status: str,
        attempt: int | None = None,
        error_code: str | None = None,
        retryable: bool | None = None,
        retry_after_at: str | None = None,
        duration_ms: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        details: dict[str, Any] = {
            "connector_id": str(connector.id),
            "connector_name": connector.name,
            "integration_slug": integration_slug,
            "run_id": run_id,
            "phase": phase,
            "status": status,
            "attempt": attempt,
            "error_code": error_code,
            "retryable": retryable,
            "retry_after_at": retry_after_at,
            "retry_after_seconds": self._retry_after_seconds(retry_after_at),
            "duration_ms": duration_ms,
            "error_domain": self._sync_error_domain(
                error_code=error_code, phase=phase, retryable=retryable
            ),
            **dict(extra or {}),
        }
        self.audit.write_event(
            tenant_id=connector.tenant_id,
            actor_user_id=connector.user_id,
            action="connector_sync",
            resource_type="connector",
            resource_id=str(connector.id),
            status=status,
            details=details,
        )

    @staticmethod
    def _runtime_connector_with_secrets(
        *,
        connector: Connector,
        runtime_secret_values: dict[str, str],
    ) -> Any:
        runtime_config = dict(connector.config or {})
        runtime_config.update(runtime_secret_values)
        return SimpleNamespace(
            id=connector.id,
            tenant_id=connector.tenant_id,
            user_id=connector.user_id,
            integration_id=connector.integration_id,
            collection_id=connector.collection_id,
            name=connector.name,
            status=connector.status,
            config=runtime_config,
            sync_frequency=connector.sync_frequency,
            last_sync_at=connector.last_sync_at,
            next_sync_at=connector.next_sync_at,
            last_error=connector.last_error,
            error_count=connector.error_count,
            created_at=connector.created_at,
            updated_at=connector.updated_at,
            integration=connector.integration,
            secrets=connector.secrets,
        )

    def _circuit_open_report(
        self, connector: Connector, integration_slug: str
    ) -> dict[str, Any]:
        health = self._connector_health_state(connector)
        raw_status = str(health.get("status") or "degraded").strip().lower()
        status: ConnectorHealthStatus = cast(
            ConnectorHealthStatus,
            (
                raw_status
                if raw_status
                in {"healthy", "degraded", "auth_expired", "offline", "stale"}
                else "degraded"
            ),
        )
        return build_health_report(
            status=status,
            healthy=False,
            message=(
                f"Circuit open until {health.get('circuit_open_until')}"
                if health.get("circuit_open_until")
                else "Circuit is open."
            ),
            error_code="circuit_open",
            metadata={
                "integration_slug": integration_slug,
                "phase": "circuit_breaker",
                **(health.get("metadata") or {}),
            },
            last_good_at=health.get("last_good_at"),
            circuit_open_until=health.get("circuit_open_until"),
            consecutive_failures=int(health.get("consecutive_failures") or 0),
        )

    def _run_health_check(
        self,
        *,
        connector: Connector,
        integration_slug: str,
        service: ConnectorService,
        phase: str,
    ) -> dict[str, Any]:
        if self._health_circuit_open(connector):
            report = self._decorate_with_cached_snapshot(
                connector=connector,
                report=self._circuit_open_report(connector, integration_slug),
            )
            config = dict(connector.config or {})
            config[Connector.HEALTH_CONFIG_KEY] = report
            connector.config = config
            self.session.flush()
            return report

        try:
            report = service.validate_health()
        except Exception as exc:  # noqa: BLE001
            health_status, error_code = classify_health_status(exception=exc)
            report = build_health_report(
                status=health_status,
                healthy=False,
                message=str(exc),
                error_code=error_code,
                metadata={
                    "integration_slug": integration_slug,
                    "phase": phase,
                    "exception_type": type(exc).__name__,
                },
            )

        applied = self._apply_health_report(
            connector=connector,
            integration_slug=integration_slug,
            report=report,
            phase=phase,
        )
        applied = self._decorate_with_cached_snapshot(
            connector=connector, report=applied
        )
        config = dict(connector.config or {})
        config[Connector.HEALTH_CONFIG_KEY] = applied
        connector.config = config
        self.session.flush()
        return applied

    def sync_connector(
        self,
        connector_id: uuid.UUID,
        tenant_id: uuid.UUID,
        progress_callback: Any | None = None,
        attempt: int = 1,
    ) -> dict[str, Any]:
        """
        Run a single connector sync with automated secret decryption.
        Uses a fresh session for background task stability.
        """
        with get_session_factory()() as session:
            self.session = session
            self.audit = AuditService(session)
            session.execute(text("SET ROLE aks_app"))
            self._apply_tenant_context(session, tenant_id)
            sync_run_id = str(uuid.uuid4())
            sync_started_at = datetime.now(tz=UTC)
            integration_slug = "unknown"

            def sync_elapsed_ms() -> int:
                return int(
                    (datetime.now(tz=UTC) - sync_started_at).total_seconds() * 1000
                )

            connector = self.session.get(Connector, connector_id)
            if not connector:
                logger.error(f"Sync failed: Connector {connector_id} not found")
                return self._build_sync_response(
                    status="error",
                    message="Connector not found",
                    run_id=sync_run_id,
                    phase="start",
                    duration_ms=sync_elapsed_ms(),
                    started_at=sync_started_at.isoformat(),
                    completed_at=datetime.now(tz=UTC).isoformat(),
                )

            logger.info(f"🚀 [Sync Start] {connector.name} ({connector_id})")
            self._write_sync_audit_event(
                connector=connector,
                integration_slug=integration_slug,
                run_id=sync_run_id,
                phase="start",
                status="started",
                attempt=attempt,
                extra={"connector_status": connector.status.value},
            )
            self._emit_progress(
                progress_callback,
                phase="start",
                message=f"Starting sync for {connector.name}.",
                connector_id=str(connector.id),
                connector_name=connector.name,
                run_id=sync_run_id,
            )

            integration = self.session.get(Integration, connector.integration_id)
            if not integration:
                connector.status = ConnectorStatus.ERROR
                connector.last_error = "Integration not found"
                self._update_sync_checkpoint(
                    connector=connector,
                    integration_slug="unknown",
                    run_id=sync_run_id,
                    phase="start",
                    status="failed",
                    error_code="integration_not_found",
                    error_message="Integration not found",
                    retryable=False,
                    attempt=attempt,
                    extra={
                        "started_at": sync_started_at.isoformat(),
                        "duration_ms": sync_elapsed_ms(),
                    },
                )
                self.session.commit()
                self._write_sync_audit_event(
                    connector=connector,
                    integration_slug="unknown",
                    run_id=sync_run_id,
                    phase="start",
                    status="error",
                    attempt=attempt,
                    error_code="integration_not_found",
                    retryable=False,
                    duration_ms=sync_elapsed_ms(),
                )
                return self._build_sync_response(
                    status="error",
                    message="Integration not found",
                    run_id=sync_run_id,
                    phase="start",
                    duration_ms=sync_elapsed_ms(),
                    started_at=sync_started_at.isoformat(),
                    completed_at=datetime.now(tz=UTC).isoformat(),
                )
            integration_slug = integration.slug
            self._log_activity(
                tenant_id=connector.tenant_id,
                activity_type="heartbeat",
                description=f"Connector heartbeat for {connector.name}.",
                source=integration.slug,
                metadata={
                    "phase": "start",
                    "connector_id": str(connector.id),
                    "integration_slug": integration.slug,
                    "connector_name": connector.name,
                    "status": connector.status.value,
                    "run_id": sync_run_id,
                },
            )

            # Update status to syncing immediately
            connector.status = ConnectorStatus.SYNCING
            connector.last_error = None
            self.session.flush()
            self._update_sync_checkpoint(
                connector=connector,
                integration_slug=integration.slug,
                run_id=sync_run_id,
                phase="credentials",
                status="running",
                attempt=attempt,
                extra={"started_at": sync_started_at.isoformat()},
            )
            self._emit_progress(
                progress_callback,
                phase="credentials",
                message=f"Decrypting credentials for {connector.name}.",
                connector_id=str(connector.id),
                integration_slug=integration.slug,
                run_id=sync_run_id,
            )

            # Decrypt and inject secrets into connector config
            try:
                stmt = select(ConnectorSecret).where(
                    ConnectorSecret.connector_id == connector_id
                )
                secrets = self.session.execute(stmt).scalars().all()
                runtime_secret_values: dict[str, str] = {}
                if secrets:
                    crypto = ConnectorSecretCrypto()
                    for secret in secrets:
                        decrypted = crypto.decrypt(
                            ciphertext=secret.secret_ciphertext,
                            nonce=secret.secret_nonce,
                            kid=secret.secret_kid,
                            aad=str(connector.tenant_id).encode(),
                        )
                        runtime_secret_values[secret.secret_type] = decrypted.decode()
                runtime_connector = self._runtime_connector_with_secrets(
                    connector=connector,
                    runtime_secret_values=runtime_secret_values,
                )
            except Exception as secret_err:
                logger.error(
                    f"Failed to decrypt secrets for connector {connector_id}: {secret_err}"
                )
                self._update_sync_checkpoint(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="credentials",
                    status="failed",
                    error_code="credential_decryption_failed",
                    error_message="Invalid connector credentials",
                    retryable=False,
                    attempt=attempt,
                    extra={
                        "started_at": sync_started_at.isoformat(),
                        "duration_ms": sync_elapsed_ms(),
                    },
                )
                connector.status = ConnectorStatus.ERROR
                connector.last_error = "Decryption failure: Invalid credentials"
                self.session.commit()
                self._write_sync_audit_event(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="credentials",
                    status="error",
                    attempt=attempt,
                    error_code="credential_decryption_failed",
                    retryable=False,
                    duration_ms=sync_elapsed_ms(),
                )
                self._emit_progress(
                    progress_callback,
                    phase="error",
                    message=f"Failed to decrypt credentials for {connector.name}.",
                    connector_id=str(connector.id),
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                )
                return self._build_sync_response(
                    status="error",
                    message="Failed to decrypt credentials",
                    run_id=sync_run_id,
                    phase="credentials",
                    duration_ms=sync_elapsed_ms(),
                    started_at=sync_started_at.isoformat(),
                    completed_at=datetime.now(tz=UTC).isoformat(),
                    error_code="credential_decryption_failed",
                    retryable=False,
                    health=connector.health_contract(),
                )

            service_cls = self._REGISTRY.get(integration.slug)
            if not service_cls:
                connector.status = ConnectorStatus.ERROR
                connector.last_error = (
                    f"No service implementation for integration: {integration.slug}"
                )
                self._update_sync_checkpoint(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="start",
                    status="failed",
                    error_code="integration_service_missing",
                    error_message=connector.last_error,
                    retryable=False,
                    attempt=attempt,
                    extra={
                        "started_at": sync_started_at.isoformat(),
                        "duration_ms": sync_elapsed_ms(),
                    },
                )
                self.session.commit()
                self._write_sync_audit_event(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="start",
                    status="error",
                    attempt=attempt,
                    error_code="integration_service_missing",
                    retryable=False,
                    duration_ms=sync_elapsed_ms(),
                )
                return self._build_sync_response(
                    status="error",
                    message=f"No service implementation for integration: {integration.slug}",
                    run_id=sync_run_id,
                    phase="start",
                    duration_ms=sync_elapsed_ms(),
                    started_at=sync_started_at.isoformat(),
                    completed_at=datetime.now(tz=UTC).isoformat(),
                )

            service = service_cls(runtime_connector, self.session)
            todo_service = TodoService(self.session)

            try:
                health = self._run_health_check(
                    connector=connector,
                    integration_slug=integration.slug,
                    service=service,
                    phase="sync_preflight",
                )
                if not health["healthy"]:
                    retryable = self._is_retryable_connector_error(
                        health.get("last_error_code") or health.get("error_code")
                    )
                    self._update_sync_checkpoint(
                        connector=connector,
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                        phase="sync_preflight",
                        status="blocked",
                        error_code=health.get("last_error_code")
                        or health.get("error_code"),
                        error_message=health.get("last_error_message")
                        or health.get("error_message"),
                        retryable=retryable,
                        attempt=attempt,
                        retry_after_at=(
                            health.get("circuit_open_until") if retryable else None
                        ),
                        extra={
                            "started_at": sync_started_at.isoformat(),
                            "duration_ms": sync_elapsed_ms(),
                        },
                    )
                    connector.status = (
                        ConnectorStatus.ERROR
                        if health["status"] == "auth_expired"
                        else ConnectorStatus.PAUSED
                    )
                    connector.error_count = int(health.get("consecutive_failures") or 0)
                    connector.last_error = (
                        health.get("last_error_message")
                        or health.get("error_message")
                        or connector.last_error
                    )
                    self.session.commit()
                    self._write_sync_audit_event(
                        connector=connector,
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                        phase="sync_preflight",
                        status="blocked",
                        attempt=attempt,
                        error_code=health.get("last_error_code")
                        or health.get("error_code"),
                        retryable=retryable,
                        retry_after_at=(
                            health.get("circuit_open_until") if retryable else None
                        ),
                        duration_ms=sync_elapsed_ms(),
                    )
                    self._log_activity(
                        tenant_id=connector.tenant_id,
                        activity_type="error",
                        description=f"Connector health check blocked sync for {connector.name}.",
                        source=integration.slug,
                        metadata={
                            "phase": "sync_preflight",
                            "connector_id": str(connector.id),
                            "integration_slug": integration.slug,
                            "connector_name": connector.name,
                            "health": health,
                        },
                    )
                    self._emit_progress(
                        progress_callback,
                        phase="blocked",
                        message=f"Health check blocked sync for {connector.name}.",
                        connector_id=str(connector.id),
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                    )
                    return self._build_sync_response(
                        status=health["status"],
                        message=health.get("last_error_message")
                        or health.get("error_message")
                        or f"Health check blocked sync for {connector.name}",
                        run_id=sync_run_id,
                        phase="sync_preflight",
                        duration_ms=sync_elapsed_ms(),
                        started_at=sync_started_at.isoformat(),
                        completed_at=datetime.now(tz=UTC).isoformat(),
                        error_code=health.get("last_error_code")
                        or health.get("error_code"),
                        retryable=retryable,
                        health=health,
                        fallback_snapshot=self._last_success_snapshot(connector),
                        extra={
                            "sync": {
                                "retry_after_at": (
                                    health.get("circuit_open_until")
                                    if retryable
                                    else None
                                )
                            }
                        },
                    )
            except Exception as exc:
                health_status, error_code = classify_health_status(exception=exc)
                self._update_sync_checkpoint(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="sync_preflight",
                    status="failed",
                    error_code=error_code,
                    error_message=str(exc),
                    retryable=self._is_retryable_connector_error(error_code),
                    attempt=attempt,
                    retry_after_at=(
                        self._compute_retry_after_at(attempt=1)
                        if self._is_retryable_connector_error(error_code)
                        else None
                    ),
                    extra={
                        "health_status": health_status,
                        "started_at": sync_started_at.isoformat(),
                        "duration_ms": sync_elapsed_ms(),
                    },
                )
                connector.status = ConnectorStatus.ERROR
                connector.last_error = str(exc)
                self.session.commit()
                self._write_sync_audit_event(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="sync_preflight",
                    status="error",
                    attempt=attempt,
                    error_code=error_code,
                    retryable=self._is_retryable_connector_error(error_code),
                    retry_after_at=(
                        self._compute_retry_after_at(attempt=1)
                        if self._is_retryable_connector_error(error_code)
                        else None
                    ),
                    duration_ms=sync_elapsed_ms(),
                    extra={"health_status": health_status},
                )
                self._emit_progress(
                    progress_callback,
                    phase="error",
                    message=f"Validation failed for {connector.name}.",
                    connector_id=str(connector.id),
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                )
                snapshot = self._last_success_snapshot(connector)
                return self._build_sync_response(
                    status="stale" if snapshot else "error",
                    message=f"Validation failed for {connector.name}",
                    run_id=sync_run_id,
                    phase="sync_preflight",
                    duration_ms=sync_elapsed_ms(),
                    started_at=sync_started_at.isoformat(),
                    completed_at=datetime.now(tz=UTC).isoformat(),
                    error_code=error_code,
                    retryable=self._is_retryable_connector_error(error_code),
                    health=connector.health_contract(),
                    fallback_snapshot=snapshot,
                    extra={
                        "sync": {
                            "retry_after_at": (
                                self._compute_retry_after_at(attempt=1)
                                if self._is_retryable_connector_error(error_code)
                                else None
                            )
                        }
                    },
                )

            # Update status to syncing
            connector.status = ConnectorStatus.SYNCING
            self.session.flush()

            try:
                logger.info(
                    f"📡 [{connector.name}] Phase 1: Fetching intelligence from source..."
                )
                self._emit_progress(
                    progress_callback,
                    phase="fetch",
                    message=f"Fetching source data from {integration.slug}.",
                    connector_id=str(connector.id),
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                )
                self._update_sync_checkpoint(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="fetch",
                    status="running",
                    attempt=attempt,
                    extra={"started_at": sync_started_at.isoformat()},
                )
                result: dict[str, Any] | None = None
                max_attempts = 2
                for attempt in range(1, max_attempts + 1):
                    try:
                        self._update_sync_checkpoint(
                            connector=connector,
                            integration_slug=integration.slug,
                            run_id=sync_run_id,
                            phase="fetch",
                            status="running",
                            attempt=attempt,
                        )
                        result = service.sync()
                        break
                    except Exception as sync_exc:
                        failure_status, failure_code = classify_health_status(
                            exception=sync_exc, message=str(sync_exc)
                        )
                        retryable = self._is_retryable_connector_error(failure_code)
                        retry_after_at = (
                            self._compute_retry_after_at(attempt=attempt + 1)
                            if retryable and attempt < max_attempts
                            else None
                        )
                        self._update_sync_checkpoint(
                            connector=connector,
                            integration_slug=integration.slug,
                            run_id=sync_run_id,
                            phase="fetch",
                            status=(
                                "retrying"
                                if retryable and attempt < max_attempts
                                else "failed"
                            ),
                            attempt=attempt,
                            error_code=failure_code,
                            error_message=str(sync_exc),
                            retryable=retryable,
                            retry_after_at=retry_after_at,
                            extra={
                                "health_status": failure_status,
                                "started_at": sync_started_at.isoformat(),
                                "duration_ms": sync_elapsed_ms(),
                            },
                        )
                        if not retryable or attempt >= max_attempts:
                            raise
                if result is None:
                    raise RuntimeError("connector sync did not return a result")

                if result.get("status") == "error":
                    raise ValueError(result.get("message", "Source fetch failed"))

                if result.get("status") == "skipped":
                    logger.info(
                        f"✅ [{connector.name}] Sync skipped: No new content found."
                    )
                    self._emit_progress(
                        progress_callback,
                        phase="skipped",
                        message=f"No new content found for {connector.name}.",
                        connector_id=str(connector.id),
                        run_id=sync_run_id,
                        attempt=attempt,
                    )
                    self._log_activity(
                        tenant_id=connector.tenant_id,
                        activity_type="sync",
                        description=f"Sync skipped for {connector.name}.",
                        source=integration.slug,
                        metadata={
                            "phase": "skipped",
                            "connector_id": str(connector.id),
                            "integration_slug": integration.slug,
                            "connector_name": connector.name,
                        },
                    )
                    connector.status = ConnectorStatus.ACTIVE
                    connector.last_sync_at = datetime.now(tz=UTC)
                    self._update_sync_checkpoint(
                        connector=connector,
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                        phase="skipped",
                        status="completed",
                        attempt=attempt,
                        extra={
                            "started_at": sync_started_at.isoformat(),
                            "duration_ms": sync_elapsed_ms(),
                        },
                    )
                    self._write_sync_audit_event(
                        connector=connector,
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                        phase="skipped",
                        status="success",
                        attempt=attempt,
                        duration_ms=sync_elapsed_ms(),
                    )
                    self.session.commit()
                    return self._build_sync_response(
                        status="skipped",
                        message=str(result.get("message") or "No new content found."),
                        run_id=sync_run_id,
                        phase="skipped",
                        attempt=attempt,
                        duration_ms=sync_elapsed_ms(),
                        started_at=sync_started_at.isoformat(),
                        completed_at=datetime.now(tz=UTC).isoformat(),
                        health=connector.health_contract(),
                        extra=dict(result),
                    )

                # Trigger ingestion if sync was successful and returned content
                if result.get("status") == "success" and result.get("payload"):
                    logger.info(
                        f"🧠 [{connector.name}] Phase 2: Embedding & Ingesting into DeepSpace..."
                    )
                    self._update_sync_checkpoint(
                        connector=connector,
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                        phase="ingest",
                        status="running",
                        extra={"started_at": sync_started_at.isoformat()},
                    )
                    self._emit_progress(
                        progress_callback,
                        phase="ingest",
                        message=f"Ingesting synced content from {connector.name} into DeepSpace.",
                        connector_id=str(connector.id),
                        run_id=sync_run_id,
                        attempt=attempt,
                    )
                    ingestion = IngestionService(self.session, self.settings)
                    payload = result.get("payload")
                    if isinstance(payload, str):
                        payload = payload.encode("utf-8")
                    if not isinstance(payload, bytes):
                        raise TypeError("connector sync payload must be bytes")

                    # Create auth context for ingestion as the connector owner
                    auth = AuthContext(
                        tenant_id=connector.tenant_id,
                        user_id=connector.user_id,
                        roles=frozenset(["user"]),
                        token_id=f"sync-{connector.id}-{datetime.now(tz=UTC).timestamp()}",
                    )

                    upload_res = ingestion.upload_document(
                        auth=auth,
                        idempotency_key=f"sync-{connector.id}-{result.get('hash', 'unhashed')}",
                        filename=result.get("filename", "sync_document.md"),
                        content_type="text/markdown",
                        payload=payload,
                        connector_id=connector.id,
                    )

                    logger.info(f"✨ [{connector.name}] Phase 3: Finalizing index...")
                    self._emit_progress(
                        progress_callback,
                        phase="finalize",
                        message=f"Finalizing index updates for {connector.name}.",
                        connector_id=str(connector.id),
                        document_id=str(upload_res.document_id),
                        run_id=sync_run_id,
                        attempt=attempt,
                    )
                    connector.status = ConnectorStatus.ACTIVE
                    connector.last_sync_at = datetime.now(tz=UTC)
                    connector.config["last_content_hash"] = result.get("hash")
                    self._persist_success_snapshot(
                        connector=connector,
                        integration_slug=integration.slug,
                        result=result,
                        document_id=upload_res.document_id,
                    )
                    self.session.commit()

                    draft_title = str(result.get("title") or connector.name).strip()
                    draft_summary = str(
                        result.get("summary") or result.get("description") or ""
                    ).strip()
                    draft_body = draft_summary or (
                        f"{connector.name} completed a new sync from {integration.slug}."
                    )
                    self._log_activity(
                        tenant_id=connector.tenant_id,
                        activity_type="draft",
                        description=f"Draft prepared from {connector.name}.",
                        source=integration.slug,
                        metadata={
                            "phase": "draft",
                            "connector_id": str(connector.id),
                            "integration_slug": integration.slug,
                            "connector_name": connector.name,
                            "document_id": str(upload_res.document_id),
                            "draft_title": draft_title,
                            "draft_body": draft_body,
                            "draft_html": f"<p>{draft_body}</p>",
                            "insert_mode": "note",
                        },
                    )
                    todo_service.upsert_task(
                        tenant_id=str(connector.tenant_id),
                        user_id=str(connector.user_id),
                        content=f"Review {connector.name} sync: {draft_title}",
                        active_form=f"Review {connector.name} sync: {draft_title}",
                        status="pending",
                        priority=(
                            60
                            if integration.slug in {"gmail", "google-calendar"}
                            else 40
                        ),
                        metadata_json={
                            "source": integration.slug,
                            "connector_id": str(connector.id),
                            "connector_name": connector.name,
                            "phase": "review",
                            "document_id": str(upload_res.document_id),
                            "draft_title": draft_title,
                        },
                    )
                    _notify_user(
                        session=self.session,
                        recipient_user_id=connector.user_id,
                        message=f"New draft ready from {connector.name}: {draft_title}",
                        idempotency_key=hashlib.sha256(
                            f"{connector.id}|{sync_run_id}|draft_ready|{upload_res.document_id}".encode()
                        ).hexdigest(),
                    )
                    self._write_sync_audit_event(
                        connector=connector,
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                        phase="complete",
                        status="success",
                        attempt=attempt,
                        duration_ms=sync_elapsed_ms(),
                        extra={
                            "document_id": str(upload_res.document_id),
                            "draft_title": draft_title,
                        },
                    )
                    self.session.commit()

                    logger.info(
                        f"🎉 [{connector.name}] Sync Success! {result.get('title') or connector.name}"
                    )
                    self._emit_progress(
                        progress_callback,
                        phase="complete",
                        message=f"Sync completed for {connector.name}.",
                        connector_id=str(connector.id),
                        document_id=str(upload_res.document_id),
                        run_id=sync_run_id,
                        attempt=attempt,
                    )
                    self._update_sync_checkpoint(
                        connector=connector,
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                        phase="complete",
                        status="completed",
                        attempt=attempt,
                        extra={
                            "document_id": str(upload_res.document_id),
                            "started_at": sync_started_at.isoformat(),
                            "duration_ms": sync_elapsed_ms(),
                        },
                    )
                    self.session.commit()
                    return self._build_sync_response(
                        status="success",
                        message=f"Sync completed for {connector.name}.",
                        run_id=sync_run_id,
                        phase="complete",
                        attempt=attempt,
                        duration_ms=sync_elapsed_ms(),
                        started_at=sync_started_at.isoformat(),
                        completed_at=datetime.now(tz=UTC).isoformat(),
                        health=connector.health_contract(),
                        document_id=upload_res.document_id,
                        extra=dict(result),
                    )

                # Fallback for success without payload
                connector.status = ConnectorStatus.ACTIVE
                self._update_sync_checkpoint(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="complete",
                    status="completed",
                    attempt=attempt,
                    extra={
                        "started_at": sync_started_at.isoformat(),
                        "duration_ms": sync_elapsed_ms(),
                    },
                )
                self._write_sync_audit_event(
                    connector=connector,
                    integration_slug=integration.slug,
                    run_id=sync_run_id,
                    phase="complete",
                    status="success",
                    attempt=attempt,
                    duration_ms=sync_elapsed_ms(),
                )
                self.session.commit()
                self._emit_progress(
                    progress_callback,
                    phase="complete",
                    message=f"Sync completed for {connector.name}.",
                    connector_id=str(connector.id),
                    run_id=sync_run_id,
                    attempt=attempt,
                )
                return self._build_sync_response(
                    status=str(result.get("status") or "success"),
                    message=str(
                        result.get("message") or f"Sync completed for {connector.name}."
                    ),
                    run_id=sync_run_id,
                    phase="complete",
                    attempt=attempt,
                    duration_ms=sync_elapsed_ms(),
                    started_at=sync_started_at.isoformat(),
                    completed_at=datetime.now(tz=UTC).isoformat(),
                    health=connector.health_contract(),
                    extra=dict(result),
                )

            except Exception as e:
                logger.error(f"❌ [{connector.name}] Sync FAILED: {str(e)}")
                failure_status, failure_code = classify_health_status(
                    exception=e, message=str(e)
                )
                failure_report = build_health_report(
                    status=failure_status,
                    healthy=False,
                    message=str(e),
                    error_code=failure_code,
                    metadata={
                        "integration_slug": integration.slug,
                        "phase": "sync_error",
                        "connector_id": str(connector.id),
                        "connector_name": connector.name,
                        "exception_type": type(e).__name__,
                    },
                )
                failure_report = self._decorate_with_cached_snapshot(
                    connector=connector,
                    report=failure_report,
                )
                failure_code = failure_report.get("error_code") or failure_code
                retryable = self._is_retryable_connector_error(str(failure_code))
                self._emit_progress(
                    progress_callback,
                    phase="error",
                    message=f"Sync failed for {connector.name}: {str(e)}",
                    connector_id=str(connector.id),
                    run_id=sync_run_id,
                    retryable=retryable,
                    error_code=str(failure_code),
                )
                # Refresh to avoid stale state and update error
                self.session.rollback()
                with get_session_factory()() as err_session:
                    conn = err_session.get(Connector, connector_id)
                    if conn:
                        orchestrator = ConnectorOrchestrator(err_session)
                        orchestrator._apply_health_report(
                            connector=conn,
                            integration_slug=integration.slug,
                            report=failure_report,
                            phase="sync_error",
                        )
                        orchestrator._update_sync_checkpoint(
                            connector=conn,
                            integration_slug=integration.slug,
                            run_id=sync_run_id,
                            phase="sync_error",
                            status="failed",
                            error_code=str(failure_code),
                            error_message=str(e),
                            retryable=retryable,
                            attempt=attempt,
                            retry_after_at=(
                                orchestrator._compute_retry_after_at(attempt=1)
                                if retryable
                                else None
                            ),
                            extra={
                                "health": failure_report,
                                "started_at": sync_started_at.isoformat(),
                                "duration_ms": sync_elapsed_ms(),
                            },
                        )
                        conn.last_error = str(e)
                    orchestrator._write_sync_audit_event(
                        connector=conn or connector,
                        integration_slug=integration.slug,
                        run_id=sync_run_id,
                        phase="sync_error",
                        status="error",
                        attempt=attempt,
                        error_code=str(failure_code),
                        retryable=retryable,
                        retry_after_at=(
                            orchestrator._compute_retry_after_at(attempt=1)
                            if retryable
                            else None
                        ),
                        duration_ms=sync_elapsed_ms(),
                    )
                    err_session.add(
                        AgentActivity(
                            tenant_id=connector.tenant_id,
                            activity_type="error",
                            description=f"Sync failed for {connector.name}.",
                            source=integration.slug,
                            metadata_json={
                                "phase": "error",
                                "connector_id": str(connector_id),
                                "integration_slug": integration.slug,
                                "connector_name": connector.name,
                                "message": str(e),
                                "health": failure_report,
                                "run_id": sync_run_id,
                                "retryable": retryable,
                                "error_code": str(failure_code),
                            },
                        )
                    )
                    _notify_user(
                        session=err_session,
                        recipient_user_id=connector.user_id,
                        message=f"Connector sync failed for {connector.name}: {str(e)}",
                        idempotency_key=hashlib.sha256(
                            f"{connector.id}|{sync_run_id}|sync_failed|{str(failure_code)}".encode()
                        ).hexdigest(),
                    )
                    TodoService(err_session).upsert_task(
                        tenant_id=str(connector.tenant_id),
                        user_id=str(connector.user_id),
                        content=f"Investigate {connector.name} sync failure",
                        active_form=f"Investigate {connector.name} sync failure",
                        status="pending",
                        priority=90,
                        metadata_json={
                            "source": integration.slug,
                            "connector_id": str(connector.id),
                            "connector_name": connector.name,
                            "phase": "error",
                            "message": str(e),
                            "health": failure_report,
                        },
                    )
                    err_session.commit()
                return {
                    **self._build_sync_response(
                        status=(
                            failure_report["status"]
                            if failure_report["status"] == "stale"
                            else "error"
                        ),
                        message=str(e),
                        run_id=sync_run_id,
                        phase="sync_error",
                        duration_ms=sync_elapsed_ms(),
                        started_at=sync_started_at.isoformat(),
                        completed_at=datetime.now(tz=UTC).isoformat(),
                        error_code=str(failure_code),
                        retryable=retryable,
                        health=failure_report,
                        fallback_snapshot=self._last_success_snapshot(connector),
                        extra={
                            "sync": {
                                "retry_after_at": (
                                    orchestrator._compute_retry_after_at(attempt=1)
                                    if retryable
                                    else None
                                )
                            }
                        },
                    ),
                    "health": failure_report,
                }

    def validate_connector_health(
        self,
        connector_id: uuid.UUID,
        tenant_id: uuid.UUID,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        """
        Validate connector credentials and live auth without ingesting data.
        """

        with get_session_factory()() as session:
            self.session = session
            self.audit = AuditService(session)
            session.execute(text("SET ROLE aks_app"))
            self._apply_tenant_context(session, tenant_id)

            connector = self.session.get(Connector, connector_id)
            if not connector:
                return {"error": "Connector not found"}

            integration = self.session.get(Integration, connector.integration_id)
            if not integration:
                return {"error": "Integration not found"}

            service_cls = self._REGISTRY.get(integration.slug)
            if not service_cls:
                return {
                    "error": f"No service implementation for integration: {integration.slug}"
                }

            try:
                stmt = select(ConnectorSecret).where(
                    ConnectorSecret.connector_id == connector_id
                )
                secrets = self.session.execute(stmt).scalars().all()
                runtime_secret_values: dict[str, str] = {}
                if secrets:
                    crypto = ConnectorSecretCrypto()
                    for secret in secrets:
                        decrypted = crypto.decrypt(
                            ciphertext=secret.secret_ciphertext,
                            nonce=secret.secret_nonce,
                            kid=secret.secret_kid,
                            aad=str(connector.tenant_id).encode(),
                        )
                        runtime_secret_values[secret.secret_type] = decrypted.decode()
                runtime_connector = self._runtime_connector_with_secrets(
                    connector=connector,
                    runtime_secret_values=runtime_secret_values,
                )
            except Exception as secret_err:
                connector.status = ConnectorStatus.ERROR
                connector.last_error = f"Decryption failure: {secret_err}"
                self.session.commit()
                self._emit_progress(
                    progress_callback,
                    phase="error",
                    message=f"Failed to validate credentials for {connector.name}.",
                    connector_id=str(connector.id),
                    integration_slug=integration.slug,
                )
                snapshot = self._last_success_snapshot(connector)
                return {
                    "status": "stale" if snapshot else "error",
                    "message": "Failed to validate credentials",
                    "fallback_snapshot": snapshot,
                }

            service = service_cls(runtime_connector, self.session)

            try:
                health = self._run_health_check(
                    connector=connector,
                    integration_slug=integration.slug,
                    service=service,
                    phase="validation",
                )
            except Exception as exc:  # noqa: BLE001
                health_status, error_code = classify_health_status(exception=exc)
                health = build_health_report(
                    status=health_status,
                    healthy=False,
                    message=str(exc),
                    error_code=error_code,
                    metadata={
                        "integration_slug": integration.slug,
                        "phase": "validation",
                        "connector_id": str(connector.id),
                        "connector_name": connector.name,
                        "exception_type": type(exc).__name__,
                    },
                )
                self._apply_health_report(
                    connector=connector,
                    integration_slug=integration.slug,
                    report=health,
                    phase="validation",
                )
                health = self._decorate_with_cached_snapshot(
                    connector=connector,
                    report=health,
                )
                config = dict(connector.config or {})
                config[Connector.HEALTH_CONFIG_KEY] = health
                connector.config = config
                self.session.commit()

            if health["healthy"]:
                self._log_activity(
                    tenant_id=connector.tenant_id,
                    activity_type="heartbeat",
                    description=f"Validated connector health for {connector.name}.",
                    source=integration.slug,
                    metadata={
                        "phase": "validation",
                        "connector_id": str(connector.id),
                        "integration_slug": integration.slug,
                        "connector_name": connector.name,
                        "status": connector.status.value,
                        "health": health,
                    },
                )
                self._emit_progress(
                    progress_callback,
                    phase="complete",
                    message=f"Validation completed for {connector.name}.",
                    connector_id=str(connector.id),
                    integration_slug=integration.slug,
                )
                return {
                    "status": "healthy",
                    "healthy": True,
                    "message": f"{connector.name} validated successfully.",
                    "health": health,
                    "fallback_snapshot": self._last_success_snapshot(connector),
                }

            connector.status = (
                ConnectorStatus.ERROR
                if health["status"] == "auth_expired"
                else ConnectorStatus.PAUSED
            )
            connector.error_count = int(health.get("consecutive_failures") or 0)
            connector.last_error = (
                health.get("last_error_message")
                or health.get("error_message")
                or connector.last_error
            )
            self.session.commit()
            self._log_activity(
                tenant_id=connector.tenant_id,
                activity_type="error",
                description=f"Connector validation failed for {connector.name}.",
                source=integration.slug,
                metadata={
                    "phase": "validation",
                    "connector_id": str(connector.id),
                    "integration_slug": integration.slug,
                    "connector_name": connector.name,
                    "status": connector.status.value,
                    "error": connector.last_error,
                    "health": health,
                },
            )
            self._emit_progress(
                progress_callback,
                phase="error",
                message=f"Validation failed for {connector.name}.",
                connector_id=str(connector.id),
                integration_slug=integration.slug,
            )
            return {
                "status": health["status"],
                "healthy": False,
                "message": health.get("last_error_message")
                or health.get("error_message")
                or connector.last_error
                or f"{connector.name} validation failed",
                "health": health,
                "fallback_snapshot": self._last_success_snapshot(connector),
            }

    def _log_activity(
        self,
        *,
        tenant_id: uuid.UUID,
        activity_type: str,
        description: str,
        source: str,
        metadata: dict[str, Any] | None = None,
        commit: bool = False,
    ) -> None:
        self.session.add(
            AgentActivity(
                tenant_id=tenant_id,
                activity_type=activity_type,
                description=description,
                source=source,
                metadata_json=metadata or {},
            )
        )
        if commit:
            self.session.commit()
        else:
            self.session.flush()
