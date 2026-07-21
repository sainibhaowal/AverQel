from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.core.config import Settings, get_settings
from app.core.context import bind_request_context, clear_request_context
from app.core.errors import ApiError, build_error_response
from app.system.services.metrics_service import (
    API_REQUEST_LATENCY_SECONDS,
    API_REQUESTS_TOTAL,
)
from app.system.services.rate_limit_service import RateLimitDecision, RateLimitService

logger = logging.getLogger(__name__)

UUID_SEGMENT_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

EXCLUDED_RATE_LIMIT_PATHS = frozenset(
    {
        "/health/live",
        "/health/ready",
        "/metrics",
    }
)


def _normalized_request_path(path: str) -> str:
    """Normalize request path for low-cardinality metrics labels."""
    return UUID_SEGMENT_PATTERN.sub("{id}", path)


def _resolve_trace_id(request: Request) -> str:
    """Resolve a request trace id, generating one if absent or blank."""
    provided = request.headers.get("X-Trace-Id", "").strip()
    return provided or str(uuid4())


def _apply_rate_limit_headers(
    response: Response, decision: RateLimitDecision | None
) -> None:
    """Attach rate-limit headers when a decision is present."""
    if decision is None:
        return
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    response.headers["X-RateLimit-Reset"] = str(decision.reset_unix)


def _record_request_metrics(
    method: str, path: str, status: str, duration_seconds: float
) -> None:
    """Record request count and latency metrics safely."""
    try:
        API_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
        API_REQUEST_LATENCY_SECONDS.labels(method=method, path=path).observe(
            duration_seconds
        )
    except Exception:  # noqa: BLE001
        # Metrics must never break request delivery.
        logger.debug("Failed to record request metrics.", exc_info=True)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind request-scoped context, enforce global rate limits, and emit metrics."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.settings: Settings = get_settings()
        self.limiter = RateLimitService(self.settings)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        trace_id = _resolve_trace_id(request)
        method = request.method.upper()
        path = _normalized_request_path(request.url.path)
        start = time.perf_counter()

        # Principal identity must come from verified auth claims, never raw request headers.
        tokens = bind_request_context(trace_id=trace_id, tenant_id=None, user_id=None)

        response: Response | None = None
        try:
            if request.url.path not in EXCLUDED_RATE_LIMIT_PATHS:
                try:
                    self.limiter.enforce_global_ip_limit(request=request)
                except ApiError as exc:
                    limited_response = build_error_response(
                        code=exc.code,
                        message=exc.message,
                        status_code=exc.status_code,
                        details=exc.details,
                    )

                    decision = getattr(request.state, "rate_limit", None)
                    if isinstance(decision, RateLimitDecision):
                        _apply_rate_limit_headers(limited_response, decision)

                    # Attach system metrics health headers
                    health_status = getattr(request.state, "system_health_status", None)
                    if health_status:
                        limited_response.headers["X-System-Health"] = str(health_status)
                        limited_response.headers["X-System-CPU-Ratio"] = f"{getattr(request.state, 'system_cpu_ratio', 0.0):.2f}"
                        limited_response.headers["X-System-Memory-Pct"] = f"{getattr(request.state, 'system_memory_pct', 0.0):.1f}%"

                    limited_response.headers["X-Trace-Id"] = trace_id
                    _record_request_metrics(
                        method=method,
                        path=path,
                        status=str(exc.status_code),
                        duration_seconds=time.perf_counter() - start,
                    )
                    return limited_response

            response = await call_next(request)

            decision = getattr(request.state, "rate_limit", None)
            if isinstance(decision, RateLimitDecision):
                _apply_rate_limit_headers(response, decision)

            # Attach system metrics health headers
            health_status = getattr(request.state, "system_health_status", None)
            if health_status:
                response.headers["X-System-Health"] = str(health_status)
                response.headers["X-System-CPU-Ratio"] = f"{getattr(request.state, 'system_cpu_ratio', 0.0):.2f}"
                response.headers["X-System-Memory-Pct"] = f"{getattr(request.state, 'system_memory_pct', 0.0):.1f}%"

            response.headers["X-Trace-Id"] = trace_id
            _record_request_metrics(
                method=method,
                path=path,
                status=str(response.status_code),
                duration_seconds=time.perf_counter() - start,
            )
            return response

        finally:
            clear_request_context(tokens)
