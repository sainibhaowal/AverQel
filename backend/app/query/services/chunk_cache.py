from __future__ import annotations

import json
import logging
from typing import Any, cast
from uuid import UUID

logger = logging.getLogger(__name__)


class ChunkMetadataCache:
    """
    Redis-backed cache for enriched chunk metadata.

    Stores small JSON-serializable metadata payloads keyed by chunk_id so
    repeated retrieval/enrichment can skip redundant work.
    """

    KEY_PREFIX = "chunk_meta:"
    DEFAULT_TTL = 3600  # 1 hour

    def __init__(self, ttl: int = DEFAULT_TTL) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be a positive integer")
        self.ttl = ttl
        self._redis: Any | None = None

    def _get_redis(self) -> Any | None:
        """Lazily resolve Redis client to avoid import-time failures."""
        if self._redis is None:
            try:
                from app.system.services.cache_service import get_redis_client

                self._redis = get_redis_client()
            except Exception:  # noqa: BLE001
                logger.debug("Redis client unavailable for chunk metadata cache.", exc_info=True)
                return None
        return self._redis

    def _make_key(self, chunk_id: UUID) -> str:
        """Build cache key for a chunk id."""
        return f"{self.KEY_PREFIX}{chunk_id}"

    @staticmethod
    def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        """Return a JSON-safe shallow metadata copy."""
        return cast(dict[str, Any], json.loads(json.dumps(metadata, default=str)))

    def get(self, chunk_id: UUID) -> dict[str, Any] | None:
        """Return cached metadata for a chunk, or None on miss/error."""
        redis = self._get_redis()
        if redis is None:
            return None

        try:
            raw = redis.get(self._make_key(chunk_id))
            if raw is None:
                return None

            decoded = json.loads(raw)
            return cast(dict[str, Any], decoded) if isinstance(decoded, dict) else None
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to read chunk metadata cache entry.",
                extra={"chunk_id": str(chunk_id)},
                exc_info=True,
            )
            return None

    def set(self, chunk_id: UUID, metadata: dict[str, Any]) -> None:
        """Cache metadata for a chunk."""
        redis = self._get_redis()
        if redis is None:
            return

        try:
            redis.setex(
                self._make_key(chunk_id),
                self.ttl,
                json.dumps(self._normalize_metadata(metadata), separators=(",", ":")),
            )
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to cache chunk metadata.",
                extra={"chunk_id": str(chunk_id)},
                exc_info=True,
            )

    def delete(self, chunk_id: UUID) -> None:
        """Delete a cached metadata entry if present."""
        redis = self._get_redis()
        if redis is None:
            return

        try:
            redis.delete(self._make_key(chunk_id))
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to delete chunk metadata cache entry.",
                extra={"chunk_id": str(chunk_id)},
                exc_info=True,
            )

    def get_many(self, chunk_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        """Batch get cached metadata. Returns chunk_id -> metadata for hits only."""
        redis = self._get_redis()
        if redis is None or not chunk_ids:
            return {}

        result: dict[UUID, dict[str, Any]] = {}
        try:
            keys = [self._make_key(chunk_id) for chunk_id in chunk_ids]
            values = redis.mget(keys)

            for chunk_id, raw in zip(chunk_ids, values, strict=False):
                if raw is None:
                    continue
                try:
                    decoded = json.loads(raw)
                    if isinstance(decoded, dict):
                        result[chunk_id] = cast(dict[str, Any], decoded)
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Failed to decode cached chunk metadata entry.",
                        extra={"chunk_id": str(chunk_id)},
                        exc_info=True,
                    )
        except Exception:  # noqa: BLE001
            logger.debug("Batch read from chunk metadata cache failed.", exc_info=True)

        return result

    def set_many(self, items: dict[UUID, dict[str, Any]]) -> None:
        """Batch cache metadata entries."""
        redis = self._get_redis()
        if redis is None or not items:
            return

        try:
            with redis.pipeline() as pipe:
                for chunk_id, metadata in items.items():
                    pipe.setex(
                        self._make_key(chunk_id),
                        self.ttl,
                        json.dumps(self._normalize_metadata(metadata), separators=(",", ":")),
                    )
                pipe.execute()
        except Exception:  # noqa: BLE001
            logger.debug("Batch write to chunk metadata cache failed.", exc_info=True)
