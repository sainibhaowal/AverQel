from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.core.context import get_tenant_id, get_trace_id, get_user_id
from app.system.schemas.errors import is_known_error_code
from app.system.services.metrics_service import API_ERRORS_TOTAL
from app.system.services.storage_quota import StorageQuotaExceededError

logger = logging.getLogger(__name__)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017

HTTP_ERROR_CODE_MAP: Final[dict[int, str]] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


async def _record_application_error_notification(request: Request, event_code: str) -> None:
    """Best-effort content-free notification for authenticated server errors."""
    tenant_raw, user_raw = get_tenant_id(), get_user_id()
    if not tenant_raw or not user_raw:
        return
    try:
        import uuid

        from starlette.concurrency import run_in_threadpool

        from app.platform.database.session import managed_db_session, set_db_tenant_context
        from app.system.services.user_notifications import add_user_notification

        tenant_id, user_id = uuid.UUID(tenant_raw), uuid.UUID(user_raw)
        trace_id = get_trace_id() or str(uuid.uuid4())

        def persist() -> None:
            with managed_db_session() as db:
                set_db_tenant_context(db, tenant_id)
                add_user_notification(
                    db,
                    tenant_id=tenant_id,
                    recipient_user_id=user_id,
                    event_domain="system",
                    event_type="application_error",
                    title="A request encountered an application error",
                    message=f"A request could not be completed. Reference: {trace_id}",
                    href="/dashboard/notifications",
                    resource_id=trace_id,
                    idempotency_key=f"system:error:{trace_id}:{event_code}",
                )
                db.commit()

        await run_in_threadpool(persist)
        request.state.notification_recorded = True
    except Exception:  # noqa: BLE001
        logger.warning("Unable to persist application error notification", exc_info=True)


async def _record_storage_quota_notification(request: Request) -> None:
    """Persist a quota alert outside the rejected write transaction."""
    tenant_raw, user_raw = get_tenant_id(), get_user_id()
    if not tenant_raw or not user_raw:
        return
    try:
        import uuid

        from starlette.concurrency import run_in_threadpool

        from app.platform.database.session import managed_db_session, set_db_tenant_context
        from app.system.services.user_notifications import add_user_notification

        tenant_id, user_id = uuid.UUID(tenant_raw), uuid.UUID(user_raw)
        month = datetime.now(UTC).strftime("%Y-%m")

        def persist() -> None:
            with managed_db_session() as db:
                set_db_tenant_context(db, tenant_id)
                add_user_notification(
                    db,
                    tenant_id=tenant_id,
                    recipient_user_id=user_id,
                    event_domain="storage",
                    event_type="quota_threshold",
                    title="Storage usage reached 100%",
                    message="Your workspace has reached its storage limit. Free space or change the workspace plan before retrying this upload.",
                    href="/dashboard/settings/storage",
                    resource_id=f"{tenant_id}:{month}:100",
                    idempotency_key=f"storage:quota:{tenant_id}:{month}:100",
                )
                db.commit()

        await run_in_threadpool(persist)
        request.state.notification_recorded = True
    except Exception:  # noqa: BLE001
        logger.warning("Unable to persist storage quota notification", exc_info=True)


class ApiError(Exception):
    """Application-level API error with stable code and HTTP status."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not is_known_error_code(code):
            raise ValueError(f"Unknown API error code: {code}")

        if not 400 <= status_code <= 599:
            raise ValueError("status_code must be between 400 and 599")

        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def utc_timestamp() -> str:
    """Return current UTC timestamp in ISO-8601 Zulu format."""
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def sanitize_for_json(obj: Any) -> Any:
    """Convert nested objects into JSON-safe values."""
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, tuple):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, set):
        return [sanitize_for_json(v) for v in sorted(obj, key=str)]
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, str | int | float | bool) or obj is None:
        return obj
    return str(obj)


def _increment_error_metric(code: str) -> None:
    """Increment error metric without breaking error delivery."""
    try:
        API_ERRORS_TOTAL.labels(code=code).inc()
    except Exception:
        logger.warning(
            "Failed to increment API error metric.",
            extra={"error_code": code},
            exc_info=True,
        )


def build_error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the standardized API error response payload."""
    _increment_error_metric(code)

    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": sanitize_for_json(details or {}),
        },
        "trace_id": get_trace_id(),
        "timestamp": utc_timestamp(),
    }
    headers: dict[str, str] = {}
    retry_after = (details or {}).get("retry_after_seconds")
    if status_code in {429, 502, 503, 504} and isinstance(retry_after, int | float):
        headers["Retry-After"] = str(max(1, int(retry_after)))
    return JSONResponse(status_code=status_code, content=payload, headers=headers)


def _map_http_exception_code(status_code: int) -> str:
    """Map generic HTTP status codes to stable API error codes."""
    mapped = HTTP_ERROR_CODE_MAP.get(status_code, "HTTP_ERROR")
    if is_known_error_code(mapped):
        return mapped
    return "HTTP_ERROR"


def register_exception_handlers(app: FastAPI) -> None:
    """Register all application exception handlers."""

    @app.exception_handler(SQLAlchemyTimeoutError)
    async def database_pool_timeout_handler(
        _: Request, exc: SQLAlchemyTimeoutError
    ) -> JSONResponse:
        logger.warning("Database connection pool wait exceeded its budget.", exc_info=exc)
        return build_error_response(
            code="SERVICE_OVERLOAD",
            message="The database is briefly busy. Your request was not changed; retry now.",
            status_code=503,
            details={"retry_after_seconds": 1},
        )

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        logger.info(
            "Handled ApiError.",
            extra={
                "error_code": exc.code,
                "status_code": exc.status_code,
            },
        )
        if exc.status_code >= 500 and not getattr(request.state, "notification_recorded", False):
            await _record_application_error_notification(request, exc.code)
        return build_error_response(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(StorageQuotaExceededError)
    async def storage_quota_handler(
        request: Request, exc: StorageQuotaExceededError
    ) -> JSONResponse:
        await _record_storage_quota_notification(request)
        return build_error_response(
            code="STORAGE_QUOTA_EXCEEDED",
            message="Your workspace storage limit has been reached.",
            status_code=413,
            details={
                "plan": exc.plan.id,
                "storage_limit_bytes": exc.plan.storage_limit_bytes,
                "usage_bytes": exc.usage_bytes,
                "requested_bytes": exc.requested_bytes,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning(
            "Request validation failed.",
            extra={
                "error_code": "VALIDATION_ERROR",
                "status_code": 422,
                "validation_error_count": len(exc.errors()),
            },
        )
        return build_error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            status_code=422,
            details={"errors": sanitize_for_json(exc.errors())},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code = _map_http_exception_code(exc.status_code)
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail.strip() else "HTTP error."

        logger.info(
            "Handled HTTPException.",
            extra={
                "error_code": code,
                "status_code": exc.status_code,
            },
        )
        if exc.status_code >= 500 and not getattr(request.state, "notification_recorded", False):
            await _record_application_error_notification(request, code)
        return build_error_response(
            code=code,
            message=detail,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled server exception.",
            extra={
                "error_code": "INTERNAL_SERVER_ERROR",
                "status_code": 500,
            },
        )
        if not getattr(request.state, "notification_recorded", False):
            await _record_application_error_notification(request, "INTERNAL_SERVER_ERROR")
        return build_error_response(
            code="INTERNAL_SERVER_ERROR",
            message="Internal server error.",
            status_code=500,
        )
