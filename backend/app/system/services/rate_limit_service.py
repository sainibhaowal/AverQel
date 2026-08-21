from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import cast

import redis
from fastapi import Request

from app.core.config import Settings, get_settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)
EMAIL_KEY_SAFE_PATTERN = re.compile(r"[^a-z0-9_.@-]+")
_REDIS_CONNECT_TIMEOUT_SECONDS = 2.0
_REDIS_SOCKET_TIMEOUT_SECONDS = 2.0


@dataclass
class AdaptiveSystemMetrics:
    cpu_load_ratio: float
    memory_usage_pct: float
    multiplier: float
    status: str  # "NORMAL", "CONGESTED", "CRITICAL"


class SystemHealthMonitor:
    @staticmethod
    def get_metrics() -> AdaptiveSystemMetrics:
        try:
            load1 = os.getloadavg()[0]
            cpus = os.cpu_count() or 1
            cpu_ratio = load1 / cpus
        except Exception:
            cpu_ratio = 0.0

        mem_pct = 0.0
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            mem_total = 0
            mem_free = 0
            mem_buffers = 0
            mem_cached = 0
            for line in lines:
                parts = line.split()
                if parts:
                    key = parts[0]
                    val = int(parts[1])
                    if key == "MemTotal:":
                        mem_total = val
                    elif key == "MemFree:":
                        mem_free = val
                    elif key == "Buffers:":
                        mem_buffers = val
                    elif key == "Cached:":
                        mem_cached = val
            if mem_total > 0:
                usable_free = mem_free + mem_buffers + mem_cached
                mem_pct = 100.0 * (1.0 - (usable_free / mem_total))
        except Exception:
            logger.debug("Unable to read host memory metrics", exc_info=True)

        if cpu_ratio > 1.5 or mem_pct > 90.0:
            status = "CRITICAL"
            multiplier = 0.2
        elif cpu_ratio > 0.85 or mem_pct > 78.0:
            status = "CONGESTED"
            multiplier = 0.6
        else:
            status = "NORMAL"
            multiplier = 1.0

        return AdaptiveSystemMetrics(
            cpu_load_ratio=cpu_ratio,
            memory_usage_pct=mem_pct,
            multiplier=multiplier,
            status=status,
        )


def resolve_request_priority(path: str) -> str:
    path = path.lower()
    if "/auth/" in path or "/login" in path or "/verify" in path:
        return "CRITICAL"
    if "/chats" in path and "/chats/" not in path:
        return "BACKGROUND"
    if "/documents" in path and ("/documents/" not in path or "/documents/events" in path):
        return "BACKGROUND"
    # These routes are visible, user-triggered UI reads.  Resource protection
    # may slow background jobs, but must not reject the dashboard or alerts.
    if "/overview" in path or "/notifications" in path:
        return "INTERACTIVE"
    if "/metrics" in path:
        return "BACKGROUND"
    return "INTERACTIVE"


@dataclass(slots=True)
class RateLimitDecision:
    limit: int
    remaining: int
    reset_unix: int
    scope: str


class _InMemoryRateStore:
    def __init__(self) -> None:
        self._values: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def increment(self, *, key: str, window_seconds: int) -> tuple[int, int]:
        now = time.time()
        expires_at = now + window_seconds
        with self._lock:
            current = self._values.get(key)
            if current is None or current[1] <= now:
                count = 1
                self._values[key] = (count, expires_at)
                return count, window_seconds

            count = current[0] + 1
            self._values[key] = (count, current[1])
            ttl = max(int(current[1] - now), 0)
            return count, ttl


@lru_cache(maxsize=1)
def _get_redis_client() -> redis.Redis:
    settings = get_settings()
    # Rate limiting is a guardrail and must never hold an authentication
    # request open indefinitely when Redis is unhealthy.  The increment path
    # already falls back to the in-memory store on errors, so bound both the
    # connection and command waits to make that fallback reachable.
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=_REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
        retry_on_timeout=False,
    )


def _safe_key(value: str | None) -> str:
    if value is None:
        return "unknown"
    normalized = value.strip()
    return normalized or "unknown"


def _get_client_ip(request: Request) -> str:
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host.strip() or "unknown"


class RateLimitService:
    _memory_store = _InMemoryRateStore()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enforce(
        self,
        *,
        request: Request,
        key: str,
        limit: int,
        window_seconds: int,
        scope: str,
    ) -> None:
        safe_key = _safe_key(key)
        safe_scope = _safe_key(scope)
        safe_limit = max(int(limit), 1)
        safe_window_seconds = max(int(window_seconds), 1)

        count, ttl = self._increment_counter(
            key=safe_key,
            window_seconds=safe_window_seconds,
        )
        remaining = max(safe_limit - count, 0)
        reset_unix = int(time.time()) + max(ttl, 0)

        decision = RateLimitDecision(
            limit=safe_limit,
            remaining=remaining,
            reset_unix=reset_unix,
            scope=safe_scope,
        )
        request.state.rate_limit = decision

        if count > safe_limit:
            raise ApiError(
                code="RATE_LIMIT_EXCEEDED",
                message="Rate limit exceeded for this operation.",
                status_code=429,
                details={
                    "scope": safe_scope,
                    "limit": safe_limit,
                    "window_seconds": safe_window_seconds,
                    "retry_after_seconds": max(ttl, 1),
                },
            )

    def enforce_global_ip_limit(self, *, request: Request) -> None:
        client_ip = _get_client_ip(request)
        priority = resolve_request_priority(request.url.path)
        health = SystemHealthMonitor.get_metrics()

        request.state.system_health_status = health.status
        request.state.system_cpu_ratio = health.cpu_load_ratio
        request.state.system_memory_pct = health.memory_usage_pct

        base_limit = self.settings.rate_limit_global_per_ip_per_5_minutes

        if health.status == "CRITICAL":
            if priority == "BACKGROUND":
                raise ApiError(
                    code="SERVICE_OVERLOAD",
                    message="System is under critical resource pressure. Background sync suspended.",
                    status_code=503,
                    details={"retry_after_seconds": 30},
                )
            elif priority == "INTERACTIVE":
                limit = int(base_limit * 0.3)
            else:
                limit = int(base_limit * 0.7)
        elif health.status == "CONGESTED":
            if priority == "BACKGROUND":
                limit = int(base_limit * 0.2)
            elif priority == "INTERACTIVE":
                limit = int(base_limit * 0.6)
            else:
                limit = base_limit
        else:
            limit = base_limit

        self.enforce(
            request=request,
            key=f"rate_limit:global_ip:{client_ip}",
            limit=limit,
            window_seconds=300,
            scope="global_ip",
        )

    def enforce_query_user_limit(self, *, request: Request, user_id: str) -> None:
        self.enforce(
            request=request,
            key=f"rate_limit:queries_user:{_safe_key(user_id)}",
            limit=self.settings.rate_limit_queries_per_user_per_minute,
            window_seconds=60,
            scope="queries_user",
        )

    def enforce_deepspace_user_limit(self, *, request: Request, user_id: str) -> None:
        """Apply the independent DeepSpace chat budget."""
        self.enforce(
            request=request,
            key=f"rate_limit:deepspace_user:{_safe_key(user_id)}",
            limit=self.settings.rate_limit_queries_per_user_per_minute,
            window_seconds=60,
            scope="deepspace_user",
        )

    def enforce_upload_user_limit(self, *, request: Request, user_id: str) -> None:
        self.enforce(
            request=request,
            key=f"rate_limit:upload_user:{_safe_key(user_id)}",
            limit=self.settings.rate_limit_upload_per_user_per_5_minutes,
            window_seconds=300,
            scope="upload_user",
        )

    def enforce_auth_login_limit(
        self,
        *,
        request: Request,
        tenant_id: str | None,
        email: str,
    ) -> None:
        normalized_email = EMAIL_KEY_SAFE_PATTERN.sub("_", email.strip().lower())
        normalized_email = normalized_email or "unknown"
        self.enforce(
            request=request,
            key=f"rate_limit:auth_login:{_safe_key(tenant_id)}:{normalized_email}",
            limit=self.settings.rate_limit_auth_login_per_tenant_email_per_5_minutes,
            window_seconds=300,
            scope="auth_login",
        )

    def enforce_auth_refresh_limit(self, *, request: Request) -> None:
        client_ip = _get_client_ip(request)
        self.enforce(
            request=request,
            key=f"rate_limit:auth_refresh_ip:{client_ip}",
            limit=self.settings.rate_limit_auth_refresh_per_ip_per_5_minutes,
            window_seconds=300,
            scope="auth_refresh",
        )

    def enforce_auth_logout_limit(self, *, request: Request, user_id: str) -> None:
        self.enforce(
            request=request,
            key=f"rate_limit:auth_logout_user:{_safe_key(user_id)}",
            limit=self.settings.rate_limit_auth_logout_per_user_per_5_minutes,
            window_seconds=300,
            scope="auth_logout",
        )

    def _increment_counter(self, *, key: str, window_seconds: int) -> tuple[int, int]:
        try:
            client = _get_redis_client()
            with client.pipeline() as pipe:
                pipe.incr(key)
                pipe.expire(key, window_seconds, nx=True)
                pipe.ttl(key)
                result = pipe.execute()  # type: ignore[no-untyped-call]

            count = int(cast(int, result[0]))
            ttl = int(cast(int, result[2]))
            return count, max(ttl, 0)

        except Exception:  # noqa: BLE001
            logger.warning(
                "Rate limit Redis backend unavailable; using in-memory fallback.",
                exc_info=True,
            )
            return self._memory_store.increment(key=key, window_seconds=window_seconds)
