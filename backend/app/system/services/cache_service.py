from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


class QueryCacheService:
    def __init__(self) -> None:
        self.redis = get_redis_client()

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            payload = self.redis.get(key)
        except Exception:  # noqa: BLE001
            logger.warning("query cache read failed", exc_info=True)
            return None

        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        if not isinstance(payload, str):
            return None

        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("query cache payload decode failed")
            return None

        if not isinstance(value, dict):
            return None
        return value

    def set(self, *, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        safe_ttl = max(1, ttl_seconds)
        try:
            payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
            self.redis.setex(key, safe_ttl, payload)
        except (TypeError, ValueError):
            logger.warning("query cache payload serialization failed", exc_info=True)
        except Exception:  # noqa: BLE001
            logger.warning("query cache write failed", exc_info=True)
