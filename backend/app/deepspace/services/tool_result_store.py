"""Scoped, short-lived references for oversized model-visible tool results."""

from __future__ import annotations

import json
import secrets
from typing import Any, cast

from app.system.services.cache_service import get_redis_client


class ToolResultStore:
    """Store only post-policy payloads under an opaque tenant-scoped reference."""

    TTL_SECONDS = 900

    @classmethod
    def _key(cls, tenant_id: object, user_id: object, conversation_id: object, ref: str) -> str:
        return f"deepspace:tool-result:v1:{tenant_id}:{user_id}:{conversation_id}:{ref}"

    def put(
        self, *, tenant_id: object, user_id: object, conversation_id: object, value: Any
    ) -> str:
        ref = secrets.token_urlsafe(18)
        get_redis_client().setex(
            self._key(tenant_id, user_id, conversation_id, ref),
            self.TTL_SECONDS,
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str),
        )
        return ref

    def get(
        self, *, tenant_id: object, user_id: object, conversation_id: object, ref: str
    ) -> Any | None:
        if not ref or len(ref) > 128:
            return None
        raw = get_redis_client().get(self._key(tenant_id, user_id, conversation_id, ref))
        if not raw:
            return None
        try:
            return json.loads(cast(str | bytes | bytearray, raw))
        except (TypeError, ValueError):
            return None
