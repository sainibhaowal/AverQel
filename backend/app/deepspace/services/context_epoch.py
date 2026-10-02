"""Explicit, tenant-scoped DeepSpace context epochs."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from app.system.services.cache_service import get_redis_client


class DeepSpaceContextEpochStore:
    TTL_SECONDS = 24 * 60 * 60

    @staticmethod
    def _key(
        tenant_id: object, user_id: object, conversation_id: object, provider: str, model: str
    ) -> str:
        return (
            f"deepspace:context-epoch:v1:{tenant_id}:{user_id}:{conversation_id}:{provider}:{model}"
        )

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    def reconcile(
        self,
        *,
        tenant_id: object,
        user_id: object,
        conversation_id: object,
        provider: str,
        model: str,
        sources: dict[str, object],
        baseline: object,
    ) -> dict[str, Any]:
        key = self._key(tenant_id, user_id, conversation_id, provider, model)
        source_digests = {name: self._digest(value) for name, value in sorted(sources.items())}
        baseline_digest = self._digest(baseline)
        try:
            raw = get_redis_client().get(key)
            previous = json.loads(cast(str | bytes | bytearray, raw)) if raw else {}
            if not isinstance(previous, dict):
                previous = {}
            changed = (
                previous.get("baseline_digest") != baseline_digest
                or previous.get("source_digests") != source_digests
            )
            epoch = int(previous.get("epoch") or 0) + (1 if changed else 0)
            if epoch <= 0:
                epoch = 1
            state = {
                "epoch": epoch,
                "baseline_digest": baseline_digest,
                "source_digests": source_digests,
                "updated_reason": "source_update" if changed else "unchanged",
            }
            get_redis_client().setex(
                key, self.TTL_SECONDS, json.dumps(state, separators=(",", ":"))
            )
            return {
                **state,
                "changed": changed,
                "source_updates": [name for name in source_digests if changed],
            }
        except Exception:  # noqa: BLE001
            # Provider requests remain correct if Redis is unavailable; the
            # epoch becomes request-local rather than blocking chat.
            return {
                "epoch": 1,
                "baseline_digest": baseline_digest,
                "source_digests": source_digests,
                "changed": False,
                "source_updates": [],
                "cache_available": False,
            }

    def advance_for_compaction(self, state: dict[str, Any]) -> dict[str, Any]:
        return {**state, "epoch": int(state.get("epoch") or 1) + 1, "updated_reason": "compaction"}
