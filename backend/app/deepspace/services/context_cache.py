from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Iterable
from typing import Any, cast

from app.system.services.cache_service import get_redis_client

logger = logging.getLogger(__name__)


class DeepSpaceContextCache:
    """Small, tenant/user isolated cache for persisted chat history.

    It intentionally caches only persisted chat messages.  Memory, Library
    retrieval, tools, provider credentials, and model responses remain outside
    this cache and retain their existing authorization paths.
    """

    TTL_SECONDS = 60
    POLICY_VERSION = "history-v2"

    def _key(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        roles: Iterable[object],
        permissions: Iterable[object],
    ) -> str:
        scope = json.dumps(
            {"roles": sorted(map(str, roles)), "permissions": sorted(map(str, permissions))},
            separators=(",", ":"),
        )
        digest = hashlib.sha256(scope.encode()).hexdigest()[:16]
        return f"deepspace:history:{self.POLICY_VERSION}:{tenant_id}:{user_id}:{conversation_id}:{digest}"

    def get(self, **scope: Any) -> list[dict[str, Any]] | None:
        try:
            raw = cast(Any, get_redis_client().get(self._key(**scope)))
            value = json.loads(raw) if raw else None
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                return None
            messages: list[dict[str, Any]] = []
            for item in value:
                message: dict[str, Any] = {
                    "role": str(item.get("role", "")),
                    "content": str(item.get("content", "")),
                }
                # The only provider-private history cache field is an
                # encrypted continuation reference. Keep its envelope intact
                # for authenticated server-side restoration; never cache
                # plaintext reasoning or arbitrary message metadata.
                reference = item.get("__deepspace_provider_continuation_ref")
                if isinstance(reference, dict):
                    message["__deepspace_provider_continuation_ref"] = {
                        "message_id": str(reference.get("message_id", ""))[:64],
                        "turn_index": reference.get("turn_index"),
                        "envelope": (
                            dict(reference["envelope"])
                            if isinstance(reference.get("envelope"), dict)
                            else None
                        ),
                    }
                messages.append(message)
            return messages
        except Exception:  # noqa: BLE001
            logger.debug("DeepSpace context cache unavailable", exc_info=True)
            return None

    def set(self, messages: list[dict[str, Any]], **scope: Any) -> None:
        try:
            get_redis_client().setex(
                self._key(**scope), self.TTL_SECONDS, json.dumps(messages, separators=(",", ":"))
            )
        except Exception:  # noqa: BLE001
            logger.debug("DeepSpace context cache write failed", exc_info=True)

    def invalidate(self, **scope: Any) -> None:
        try:
            get_redis_client().delete(self._key(**scope))
        except Exception:  # noqa: BLE001
            logger.debug("DeepSpace context cache invalidation failed", exc_info=True)

    def invalidate_conversation(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> None:
        """Purge all cached history variants for a specific conversation."""
        try:
            client = get_redis_client()
            pattern = (
                f"deepspace:history:{self.POLICY_VERSION}:{tenant_id}:{user_id}:{conversation_id}:*"
            )
            keys = list(client.scan_iter(match=pattern, count=100))
            if keys:
                client.delete(*keys)
        except Exception:  # noqa: BLE001
            logger.debug("DeepSpace context cache conversation invalidation failed", exc_info=True)

    def invalidate_conversations(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_ids: list[uuid.UUID]
    ) -> None:
        """Purge all cached history variants for multiple conversations."""
        for cid in conversation_ids:
            self.invalidate_conversation(tenant_id=tenant_id, user_id=user_id, conversation_id=cid)
