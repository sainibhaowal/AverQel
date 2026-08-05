from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.core.context import get_trace_id
from app.system.schemas.errors import is_known_error_code
from app.system.services.metrics_service import API_ERRORS_TOTAL

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
    return JSONResponse(status_code=status_code, content=payload)


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
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        logger.info(
            "Handled ApiError.",
            extra={
                "error_code": exc.code,
                "status_code": exc.status_code,
            },
        )
        return build_error_response(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
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
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        code = _map_http_exception_code(exc.status_code)
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail.strip() else "HTTP error."

        logger.info(
            "Handled HTTPException.",
            extra={
                "error_code": code,
                "status_code": exc.status_code,
            },
        )
        return build_error_response(
            code=code,
            message=detail,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled server exception.",
            extra={
                "error_code": "INTERNAL_SERVER_ERROR",
                "status_code": 500,
            },
        )
        return build_error_response(
            code="INTERNAL_SERVER_ERROR",
            message="Internal server error.",
            status_code=500,
        )
