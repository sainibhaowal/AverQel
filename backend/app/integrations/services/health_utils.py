from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

ConnectorHealthStatus = Literal["healthy", "degraded", "auth_expired", "offline", "stale"]


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def backoff_seconds(
    consecutive_failures: int, *, base_seconds: int = 300, max_seconds: int = 3600
) -> int:
    failures = max(1, int(consecutive_failures))
    delay: int = base_seconds * (2 ** max(0, failures - 1))
    result: int = min(max_seconds, max(base_seconds, delay))
    return result


def future_iso(seconds: int) -> str:
    return (
        (datetime.now(tz=UTC) + timedelta(seconds=max(0, int(seconds))))
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def classify_health_status(
    *,
    message: str | None = None,
    http_status: int | None = None,
    exception: Exception | None = None,
) -> tuple[ConnectorHealthStatus, str | None]:
    text = " ".join(
        part
        for part in (
            str(message or ""),
            str(http_status or ""),
            type(exception).__name__ if exception is not None else "",
            str(exception or ""),
        )
        if part
    ).lower()
    if any(
        marker in text
        for marker in (
            "invalid_grant",
            "invalid auth",
            "invalid_auth",
            "auth error",
            "unauthorized",
            "forbidden",
            "token expired",
            "expired token",
            "refresh token",
            "credential",
        )
    ):
        return "auth_expired", "auth_expired"
    if any(
        marker in text
        for marker in (
            "timeout",
            "timed out",
            "connection",
            "connect",
            "network",
            "dns",
            "unreachable",
            "offline",
            "503",
            "504",
            "502",
            "429",
        )
    ):
        return "offline", "connectivity_failure"
    return "degraded", "validation_failed"


def build_health_report(
    *,
    status: ConnectorHealthStatus,
    healthy: bool,
    message: str | None = None,
    error_code: str | None = None,
    http_status: int | None = None,
    metadata: dict[str, Any] | None = None,
    last_good_at: str | None = None,
    circuit_open_until: str | None = None,
    consecutive_failures: int = 0,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "healthy": healthy,
        "status": status,
        "error_code": error_code,
        "error_message": message,
        "http_status": http_status,
        "metadata": metadata or {},
        "checked_at": now_iso(),
        "last_good_at": last_good_at,
        "circuit_open_until": circuit_open_until,
        "consecutive_failures": max(0, int(consecutive_failures)),
    }
    return report
