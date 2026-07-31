from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, delete, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.deepspace.models.agent_memory import AgentMemory
from app.deepspace.models.agent_memory_preferences import AgentMemoryPreferences
from app.deepspace.models.agent_todo import AgentTodo
from app.ingestion.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

MEMORY_EMBEDDING_VERSION = "deepspace-memory-v1"
SESSION_MEMORY_RETENTION_DAYS = 7
MEMORY_DECAY_HALF_LIFE_DAYS = 120.0
MAX_MEMORY_RETRIEVAL_ITEMS = 8
MEMORY_STATUS_ACTIVE = "active"
MEMORY_STATUS_PENDING = "pending"
MEMORY_STATUS_ARCHIVED = "archived"


class MemoryService:
    def __init__(self, db: Session, settings: Any | None = None):
        self.db = db
        self.settings = settings

    @staticmethod
    def _normalize_owner_id(value: Any) -> str:
        return str(value)

    @staticmethod
    def _memory_to_dict(memory: AgentMemory) -> dict[str, Any]:
        return {
            "id": str(memory.id),
            "key": memory.key,
            "value": memory.value,
            "scope": memory.scope,
            "tags": list(memory.tags or []),
            "importance_score": float(memory.importance_score or 0.0),
            "confidence_score": float(memory.confidence_score or 0.0),
            "status": str(memory.status or MEMORY_STATUS_ACTIVE),
            "source": memory.source,
            "conversation_id": memory.conversation_id,
            "expires_at": memory.expires_at.isoformat() if memory.expires_at else None,
            "access_count": int(memory.access_count or 0),
            "last_accessed_at": (
                memory.last_accessed_at.isoformat() if memory.last_accessed_at else None
            ),
            "metadata": dict(memory.metadata_json or {}),
            "embedding_provider": memory.embedding_provider,
            "embedding_model": memory.embedding_model,
            "embedding_version": memory.embedding_version,
            "pgvector_ready": memory.embedding_vector is not None,
            "decay_score": None,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
        }

    @staticmethod
    def _active_memory_clause(*, now: datetime | None = None):
        now = now or datetime.now(UTC)
        return and_(
            AgentMemory.status == MEMORY_STATUS_ACTIVE,
            or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
        )

    @staticmethod
    def _accessible_memory_clause(*, user_id: str, conversation_id: str | None = None):
        user_scopes = AgentMemory.scope.in_(("user", "session"))
        user_owned = and_(AgentMemory.user_id == user_id, user_scopes)
        if conversation_id is not None:
            user_owned = and_(
                user_owned,
                or_(
                    AgentMemory.scope != "session",
                    AgentMemory.conversation_id == str(conversation_id),
                ),
            )
        return or_(user_owned, AgentMemory.scope == "global")

    @staticmethod
    def _preferences_to_dict(preferences: AgentMemoryPreferences) -> dict[str, bool]:
        return {
            "automatic_capture_enabled": bool(preferences.automatic_capture_enabled),
            "review_inferred_memories": bool(preferences.review_inferred_memories),
            "memory_retrieval_enabled": bool(preferences.memory_retrieval_enabled),
        }

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9][a-z0-9_\-]{1,}", value.lower())
            if token
        }

    @staticmethod
    def _normalize_scope(scope: str | None) -> str:
        normalized = str(scope or "user").strip().lower()
        if normalized in {"global", "shared"}:
            return "global"
        if normalized in {"session", "temporary"}:
            return "session"
        if normalized in {"persistent", "user", ""}:
            return "user"
        return "user"

    @staticmethod
    def _scope_priority_clause():
        return case(
            (AgentMemory.scope == "session", 0),
            (AgentMemory.scope == "user", 1),
            (AgentMemory.scope == "global", 2),
            else_=3,
        ).asc()

    @staticmethod
    def _scope_priority_value(scope: str | None) -> int:
        return {
            "session": 0,
            "user": 1,
            "global": 2,
        }.get(str(scope or "user"), 3)

    @staticmethod
    def _content_hash(*, key: str, value: str, scope: str) -> str:
        normalized = "\n".join(
            [key.strip().lower(), value.strip(), scope.strip().lower()]
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _cosine_similarity(
        left: list[float] | None, right: list[float] | None
    ) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=False))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (left_norm * right_norm)))

    @staticmethod
    def _freshness_score(memory: AgentMemory, *, now: datetime) -> float:
        timestamp = memory.updated_at or memory.created_at
        if timestamp is None:
            return 0.5
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        age_days = max(0.0, (now - timestamp).total_seconds() / 86400)
        return math.exp(-math.log(2) * age_days / MEMORY_DECAY_HALF_LIFE_DAYS)

    @staticmethod
    def _decay_score(memory: AgentMemory, *, now: datetime) -> float:
        freshness = MemoryService._freshness_score(memory, now=now)
        return max(0.0, min(1.0, 1.0 - freshness))

    @staticmethod
    def _activity_timestamp(memory: AgentMemory) -> datetime | None:
        timestamp = memory.last_accessed_at or memory.updated_at or memory.created_at
        if timestamp is None:
            return None
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=UTC)
        return timestamp

    @staticmethod
    def _age_days(memory: AgentMemory, *, now: datetime) -> float:
        timestamp = MemoryService._activity_timestamp(memory)
        if timestamp is None:
            return 0.0
        return max(0.0, (now - timestamp).total_seconds() / 86400)

    @staticmethod
    def _retention_window_days(memory: AgentMemory) -> int | None:
        metadata = dict(memory.metadata_json or {})
        explicit = metadata.get("retention_days")
        if isinstance(explicit, int) and explicit > 0:
            return explicit
        if str(memory.scope or "user") == "session":
            return SESSION_MEMORY_RETENTION_DAYS
        return None

    @staticmethod
    def _memory_retention_state(memory: AgentMemory, *, now: datetime) -> str:
        retention_days = MemoryService._retention_window_days(memory)
        if retention_days is None:
            return "persistent"
        return (
            "stale"
            if MemoryService._age_days(memory, now=now) > retention_days
            else "active"
        )

    @staticmethod
    def _importance_from_inputs(
        *, key: str, value: str, tags: list[str] | None, explicit: float | None
    ) -> float:
        if explicit is not None:
            return max(0.0, min(1.0, float(explicit)))
        text = f"{key} {value}".lower()
        score = 0.45
        if any(term in text for term in ("always", "never", "prefer", "important")):
            score += 0.2
        if tags and any(tag in {"preference", "identity", "workflow"} for tag in tags):
            score += 0.2
        if len(value) > 240:
            score += 0.05
        return max(0.1, min(1.0, score))

    @staticmethod
    def _dedupe_key(memory: AgentMemory) -> str:
        if memory.content_hash:
            return str(memory.content_hash)
        scope = str(memory.scope or "user")
        return hashlib.sha256(
            "\n".join([memory.key.strip().lower(), memory.value.strip(), scope]).encode(
                "utf-8"
            )
        ).hexdigest()

    def _embed_text(
        self, text: str, *, tenant_id: str, user_id: str
    ) -> tuple[list[float], dict[str, Any]]:
        settings = self.settings or get_settings()
        service = EmbeddingService(settings, self.db)
        result = service.embed_many_with_metadata(
            [text],
            tenant_id=self._uuid_or_none(tenant_id),
            actor_user_id=self._uuid_or_none(user_id),
        )
        vector = result.vectors[0]
        metadata = result.metadata
        return vector, {
            "provider": metadata.provider,
            "model": metadata.model,
            "fallback_used": metadata.fallback_used,
            "failure_code": metadata.failure_code,
        }

    @staticmethod
    def _uuid_or_none(value: str) -> Any | None:
        import uuid

        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None

    async def get_preferences(self, *, tenant_id: str, user_id: str) -> dict[str, bool]:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        preferences = self.db.execute(
            select(AgentMemoryPreferences).where(
                AgentMemoryPreferences.tenant_id == tenant_id,
                AgentMemoryPreferences.user_id == user_id,
            )
        ).scalar_one_or_none()
        if preferences is None:
            preferences = AgentMemoryPreferences(tenant_id=tenant_id, user_id=user_id)
            self.db.add(preferences)
            self.db.commit()
        return self._preferences_to_dict(preferences)

    async def update_preferences(
        self,
        *,
        tenant_id: str,
        user_id: str,
        automatic_capture_enabled: bool | None = None,
        review_inferred_memories: bool | None = None,
        memory_retrieval_enabled: bool | None = None,
    ) -> dict[str, bool]:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        preferences = self.db.execute(
            select(AgentMemoryPreferences).where(
                AgentMemoryPreferences.tenant_id == tenant_id,
                AgentMemoryPreferences.user_id == user_id,
            )
        ).scalar_one_or_none()
        if preferences is None:
            preferences = AgentMemoryPreferences(tenant_id=tenant_id, user_id=user_id)
            self.db.add(preferences)
        if automatic_capture_enabled is not None:
            preferences.automatic_capture_enabled = bool(automatic_capture_enabled)
        if review_inferred_memories is not None:
            preferences.review_inferred_memories = bool(review_inferred_memories)
        if memory_retrieval_enabled is not None:
            preferences.memory_retrieval_enabled = bool(memory_retrieval_enabled)
        preferences.updated_at = datetime.now(UTC)
        self.db.commit()
        return self._preferences_to_dict(preferences)

    @staticmethod
    def _is_sensitive_candidate(value: str) -> bool:
        lowered = value.lower()
        blocked_terms = (
            "password",
            "api key",
            "access token",
            "refresh token",
            "secret key",
            "private key",
            "credential",
            "credit card",
            "social security",
            "medical",
            "diagnosis",
            "health condition",
        )
        return any(term in lowered for term in blocked_terms)

    @staticmethod
    def _candidate_from_prompt(prompt: str) -> tuple[str, str, list[str], float] | None:
        """Extract only a clear, durable preference/fact without an extra LLM call.

        This deliberately ignores ordinary questions and full chat transcripts. It is a
        bounded convenience feature, not self-training or hidden profile building.
        """
        normalized = " ".join(str(prompt or "").strip().split())
        if len(normalized) < 12 or len(normalized) > 600:
            return None
        patterns = (
            (r"\b(?:i|we)\s+prefer\s+(.+)", "preference", 0.9),
            (r"\b(?:i|we)\s+(?:always|never)\s+(.+)", "workflow", 0.82),
            (r"\bmy\s+([a-z][a-z0-9 _-]{1,50})\s+is\s+(.+)", "project_fact", 0.8),
        )
        for pattern, tag, confidence in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match is None:
                continue
            if tag == "project_fact":
                key = re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")
                value = f"My {match.group(1).strip()} is {match.group(2).strip()}"
            else:
                key = f"{tag}_{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:12]}"
                value = normalized
            return key[:120], value[:1000], [tag, "inferred"], confidence
        return None

    async def consolidate_turn(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        prompt: str,
    ) -> dict[str, Any] | None:
        """Create at most one reviewable durable-memory candidate after a successful turn."""
        preferences = await self.get_preferences(tenant_id=tenant_id, user_id=user_id)
        if not preferences["automatic_capture_enabled"]:
            return None
        candidate = self._candidate_from_prompt(prompt)
        if candidate is None:
            return None
        key, value, tags, confidence = candidate
        if self._is_sensitive_candidate(value):
            return {"status": "blocked_sensitive", "reason": "sensitive_content"}
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        existing = self.db.execute(
            select(AgentMemory).where(
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.user_id == user_id,
                AgentMemory.content_hash == self._content_hash(key=key, value=value, scope="user"),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return {"status": "duplicate", "memory_id": str(existing.id)}
        memory_id = await self.store_fact(
            tenant_id=tenant_id,
            user_id=user_id,
            key=key,
            value=value,
            scope="user",
            tags=tags,
            importance_score=0.65,
            confidence_score=confidence,
            source="conversation_consolidation",
            conversation_id=conversation_id,
            status=(MEMORY_STATUS_PENDING if preferences["review_inferred_memories"] else MEMORY_STATUS_ACTIVE),
            metadata_json={"inferred": True, "source_message": "latest_user_turn"},
        )
        return {
            "status": "pending" if preferences["review_inferred_memories"] else "saved",
            "memory_id": memory_id,
        }

    async def store_fact(
        self,
        *,
        tenant_id: str,
        user_id: str,
        key: str,
        value: str,
        scope: str = "user",
        tags: list[str] | None = None,
        importance_score: float | None = None,
        confidence_score: float | None = None,
        source: str | None = None,
        conversation_id: str | None = None,
        status: str = MEMORY_STATUS_ACTIVE,
        expires_at: datetime | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> str:
        """Store a deduplicated, embedding-backed memory fact."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)

        from app.deepspace.integrations.client_proxy import client_proxy_registry
        channel = "storage"
        if client_proxy_registry.is_storage_connected(str(tenant_id), str(user_id)):
            return await client_proxy_registry.db_proxy_call(
                str(tenant_id), str(user_id),
                "db.memories.store_fact",
                {
                    "key": key,
                    "value": value,
                    "scope": scope,
                    "tags": tags,
                    "importance_score": importance_score,
                    "confidence_score": confidence_score,
                    "source": source,
                    "conversation_id": conversation_id,
                    "status": status,
                    "metadata_json": metadata_json,
                },
                channel=channel,
            )

        normalized_key = key.strip()
        normalized_value = value.strip()
        normalized_scope = self._normalize_scope(scope)
        normalized_status = (
            status if status in {MEMORY_STATUS_ACTIVE, MEMORY_STATUS_PENDING} else MEMORY_STATUS_ACTIVE
        )
        if normalized_scope == "session" and expires_at is None:
            expires_at = datetime.now(UTC) + timedelta(days=SESSION_MEMORY_RETENTION_DAYS)
        if not normalized_key:
            raise ValueError("key is required")
        if not normalized_value:
            raise ValueError("value is required")

        content_hash = self._content_hash(
            key=normalized_key, value=normalized_value, scope=normalized_scope
        )
        scope_filter = (
            AgentMemory.scope == "global"
            if normalized_scope == "global"
            else AgentMemory.user_id == user_id
        )

        duplicate_stmt = select(AgentMemory).where(
            AgentMemory.tenant_id == tenant_id,
            scope_filter,
            AgentMemory.content_hash == content_hash,
        )
        existing = self.db.execute(duplicate_stmt).scalars().first()

        if existing:
            importance = self._importance_from_inputs(
                key=normalized_key,
                value=normalized_value,
                tags=tags,
                explicit=importance_score,
            )
            existing.key = normalized_key
            existing.value = normalized_value
            existing.scope = normalized_scope
            existing.status = normalized_status
            existing.source = source or existing.source
            existing.conversation_id = conversation_id or existing.conversation_id
            existing.expires_at = expires_at or existing.expires_at
            existing.confidence_score = max(
                float(existing.confidence_score or 0.0),
                max(0.0, min(1.0, float(confidence_score if confidence_score is not None else 1.0))),
            )
            existing.content_hash = content_hash
            existing.importance_score = max(
                float(existing.importance_score or 0.0), importance
            )
            existing.metadata_json = {
                **dict(existing.metadata_json or {}),
                **dict(metadata_json or {}),
                "embedding_reused": True,
            }
            if tags:
                existing.tags = sorted(set((existing.tags or []) + tags))
            mem_id = existing.id
        else:
            if normalized_status == MEMORY_STATUS_ACTIVE and normalized_scope == "user" and source in {
                "manual_memory",
                "deepspace_memory_tool",
                "user_edit",
            }:
                conflicting_memories = self.db.execute(
                    select(AgentMemory).where(
                        AgentMemory.tenant_id == tenant_id,
                        AgentMemory.user_id == user_id,
                        AgentMemory.scope == "user",
                        AgentMemory.status == MEMORY_STATUS_ACTIVE,
                        AgentMemory.key == normalized_key,
                    )
                ).scalars().all()
                for conflicting in conflicting_memories:
                    conflicting.status = MEMORY_STATUS_ARCHIVED
                    conflicting.metadata_json = {
                        **dict(conflicting.metadata_json or {}),
                        "superseded_at": datetime.now(UTC).isoformat(),
                        "superseded_by_key": normalized_key,
                    }
            importance = self._importance_from_inputs(
                key=normalized_key,
                value=normalized_value,
                tags=tags,
                explicit=importance_score,
            )
            embedding_text = f"{normalized_key}\n{normalized_value}"
            embedding, embedding_metadata = self._embed_text(
                embedding_text, tenant_id=tenant_id, user_id=user_id
            )
            mem_id = str(generate_uuid7_with_fallback())
            memory = AgentMemory(
                id=mem_id,
                tenant_id=tenant_id,
                user_id=user_id,
                key=normalized_key,
                value=normalized_value,
                embedding=embedding,
                embedding_vector=embedding,
                embedding_provider=embedding_metadata.get("provider"),
                embedding_model=embedding_metadata.get("model"),
                embedding_version=MEMORY_EMBEDDING_VERSION,
                content_hash=content_hash,
                importance_score=importance,
                confidence_score=max(0.0, min(1.0, float(confidence_score if confidence_score is not None else 1.0))),
                status=normalized_status,
                source=(str(source).strip()[:120] if source else None),
                conversation_id=(str(conversation_id).strip()[:120] if conversation_id else None),
                expires_at=expires_at,
                access_count=0,
                metadata_json={
                    **dict(metadata_json or {}),
                    "embedding_fallback_used": bool(
                        embedding_metadata.get("fallback_used")
                    ),
                    "embedding_failure_code": embedding_metadata.get("failure_code"),
                },
                scope=normalized_scope,
                tags=sorted(set(tags or [])),
            )
            self.db.add(memory)

        self.db.commit()
        return mem_id

    async def search_memories(
        self,
        *,
        tenant_id: str,
        user_id: str,
        query: str,
        limit: int = 5,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return semantically ranked memories scoped to the current tenant/user."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)

        from app.deepspace.integrations.client_proxy import client_proxy_registry
        channel = "storage"
        if client_proxy_registry.is_storage_connected(str(tenant_id), str(user_id)):
            return await client_proxy_registry.db_proxy_call(
                str(tenant_id), str(user_id),
                "db.memories.search_memories",
                {"query": query, "limit": limit, "conversation_id": conversation_id},
                channel=channel,
            )

        normalized_query = query.strip()
        if not normalized_query:
            return []

        query_embedding, _metadata = self._embed_text(
            normalized_query, tenant_id=tenant_id, user_id=user_id
        )
        candidates_with_distance = self._search_candidates_with_pgvector(
            tenant_id=tenant_id,
            user_id=user_id,
            query_embedding=query_embedding,
            limit=max(min(limit, MAX_MEMORY_RETRIEVAL_ITEMS) * 12, 50),
            conversation_id=conversation_id,
        )
        if candidates_with_distance is None:
            stmt = (
                select(AgentMemory)
                .where(
                    AgentMemory.tenant_id == tenant_id,
                    self._accessible_memory_clause(
                        user_id=user_id, conversation_id=conversation_id
                    ),
                    self._active_memory_clause(),
                )
                .order_by(
                    self._scope_priority_clause(),
                    AgentMemory.updated_at.desc(),
                    AgentMemory.created_at.desc(),
                )
                .limit(max(limit * 12, 50))
            )
            candidates_with_distance = [
                (memory, None) for memory in self.db.execute(stmt).scalars().all()
            ]
        query_tokens = self._tokenize(normalized_query)
        now = datetime.now(UTC)
        scored: list[tuple[float, float, float, float, AgentMemory]] = []
        for memory, distance in candidates_with_distance:
            semantic = (
                max(0.0, 1.0 / (1.0 + float(distance)))
                if distance is not None
                else self._cosine_similarity(
                    query_embedding,
                    (
                        memory.embedding_vector
                        if memory.embedding_vector is not None
                        else memory.embedding
                    ),
                )
            )
            memory_tokens = self._tokenize(f"{memory.key} {memory.value}")
            lexical = (
                len(query_tokens & memory_tokens) / len(query_tokens)
                if query_tokens
                else 0.0
            )
            freshness = self._freshness_score(memory, now=now)
            importance = max(0.0, min(1.0, float(memory.importance_score or 0.0)))
            confidence = max(0.0, min(1.0, float(memory.confidence_score or 0.0)))
            scope_bonus = {
                "session": 0.1,
                "user": 0.06,
                "global": 0.03,
            }.get(str(memory.scope or "user"), 0.0)
            score = (
                semantic * 0.52
                + lexical * 0.2
                + importance * 0.1
                + confidence * 0.1
                + freshness * 0.04
                + scope_bonus
            )
            if score > 0:
                scored.append((score, semantic, lexical, freshness, memory))

        scored.sort(key=lambda item: item[0], reverse=True)
        deduped: list[tuple[float, float, float, float, AgentMemory]] = []
        seen_dedupe_keys: set[str] = set()
        for scored_item in scored:
            dedupe_key = self._dedupe_key(scored_item[4])
            if dedupe_key in seen_dedupe_keys:
                continue
            seen_dedupe_keys.add(dedupe_key)
            deduped.append(scored_item)
        selected = deduped[: min(MAX_MEMORY_RETRIEVAL_ITEMS, max(1, limit))]
        for _score, _semantic, _lexical, _freshness, memory in selected:
            memory.access_count = int(memory.access_count or 0) + 1
            memory.last_accessed_at = now
        if selected:
            self.db.commit()

        return [
            {
                **self._memory_to_dict(memory),
                "relevance_score": round(score, 6),
                "semantic_score": round(semantic, 6),
                "lexical_score": round(lexical, 6),
                "freshness_score": round(freshness, 6),
                "decay_score": round(self._decay_score(memory, now=now), 6),
            }
            for score, semantic, lexical, freshness, memory in selected
        ]

    def _search_candidates_with_pgvector(
        self,
        *,
        tenant_id: str,
        user_id: str,
        query_embedding: list[float],
        limit: int,
        conversation_id: str | None = None,
    ) -> list[tuple[AgentMemory, float | None]] | None:
        """Use native pgvector ranking when the database supports it."""
        try:
            distance = AgentMemory.embedding_vector.l2_distance(query_embedding)
            rows = self.db.execute(
                select(AgentMemory, distance.label("distance"))
                .where(
                    AgentMemory.tenant_id == tenant_id,
                    self._accessible_memory_clause(
                        user_id=user_id, conversation_id=conversation_id
                    ),
                    self._active_memory_clause(),
                    AgentMemory.embedding_vector.is_not(None),
                )
                .order_by(distance.asc())
                .limit(limit)
            ).all()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Falling back to in-memory memory vector ranking: %s",
                exc,
                exc_info=True,
            )
            self.db.rollback()
            return None
        return [
            (memory, float(distance) if distance is not None else None)
            for memory, distance in rows
        ]

    async def retrieve_fact(
        self,
        *,
        tenant_id: str,
        user_id: str,
        key: str | None,
        conversation_id: str | None = None,
    ) -> str | None:
        """Return the latest fact stored under the provided key."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return None

        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.tenant_id == tenant_id,
                self._accessible_memory_clause(
                    user_id=user_id, conversation_id=conversation_id
                ),
                self._active_memory_clause(),
                AgentMemory.key == normalized_key,
            )
            .order_by(
                self._scope_priority_clause(),
                AgentMemory.updated_at.desc(),
                AgentMemory.created_at.desc(),
            )
        )
        memory = self.db.execute(stmt).scalars().first()
        if memory:
            memory.access_count = int(memory.access_count or 0) + 1
            memory.last_accessed_at = datetime.now(UTC)
            self.db.commit()
        return memory.value if memory else None

    async def list_all_memories(
        self, *, tenant_id: str, user_id: str, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """List all persisted memories accessible to the current tenant/user."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        filters = [
            AgentMemory.tenant_id == tenant_id,
            self._accessible_memory_clause(user_id=user_id),
        ]
        if not include_archived:
            filters.append(AgentMemory.status != MEMORY_STATUS_ARCHIVED)
        stmt = (
            select(AgentMemory)
            .where(*filters)
            .order_by(
                self._scope_priority_clause(),
                AgentMemory.updated_at.desc(),
                AgentMemory.created_at.desc(),
            )
        )
        memories = self.db.execute(stmt).scalars().all()
        return [self._memory_to_dict(memory) for memory in memories]

    async def get_memory(
        self, *, tenant_id: str, user_id: str, memory_id: str
    ) -> dict[str, Any] | None:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        memory = self.db.execute(
            select(AgentMemory).where(
                AgentMemory.id == str(memory_id),
                AgentMemory.tenant_id == tenant_id,
                self._accessible_memory_clause(user_id=user_id),
            )
        ).scalar_one_or_none()
        return self._memory_to_dict(memory) if memory is not None else None

    async def update_memory(
        self,
        *,
        tenant_id: str,
        user_id: str,
        memory_id: str,
        value: str,
        scope: str = "user",
        tags: list[str] | None = None,
        importance_score: float | None = None,
        confidence_score: float | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Update an owned memory and regenerate its embedding safely."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        memory = self.db.execute(
            select(AgentMemory).where(
                AgentMemory.id == str(memory_id),
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.user_id == user_id,
                AgentMemory.status != MEMORY_STATUS_ARCHIVED,
            )
        ).scalar_one_or_none()
        if memory is None:
            return None
        normalized_value = value.strip()
        normalized_scope = self._normalize_scope(scope)
        if not normalized_value:
            raise ValueError("value is required")
        if normalized_scope == "global":
            raise ValueError("Only explicitly shared memory may use global scope.")
        normalized_tags = sorted(set(str(tag).strip() for tag in (tags or []) if str(tag).strip()))
        content_hash = self._content_hash(
            key=memory.key, value=normalized_value, scope=normalized_scope
        )
        duplicate = self.db.execute(
            select(AgentMemory).where(
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.content_hash == content_hash,
                AgentMemory.id != str(memory_id),
                AgentMemory.user_id == user_id,
                AgentMemory.status == MEMORY_STATUS_ACTIVE,
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise ValueError("An equivalent memory already exists.")
        embedding, embedding_metadata = self._embed_text(
            f"{memory.key}\n{normalized_value}", tenant_id=tenant_id, user_id=user_id
        )
        memory.value = normalized_value
        memory.scope = normalized_scope
        memory.tags = normalized_tags
        memory.importance_score = self._importance_from_inputs(
            key=memory.key,
            value=normalized_value,
            tags=normalized_tags,
            explicit=importance_score,
        )
        memory.confidence_score = max(
            0.0,
            min(
                1.0,
                float(
                    confidence_score
                    if confidence_score is not None
                    else memory.confidence_score or 1.0
                ),
            ),
        )
        memory.status = MEMORY_STATUS_ACTIVE
        memory.source = "user_edit"
        memory.metadata_json = dict(metadata_json or {})
        memory.embedding = embedding
        memory.embedding_vector = embedding
        memory.embedding_provider = embedding_metadata.get("provider")
        memory.embedding_model = embedding_metadata.get("model")
        memory.embedding_version = MEMORY_EMBEDDING_VERSION
        memory.content_hash = content_hash
        memory.updated_at = datetime.now(UTC)
        self.db.commit()
        return self._memory_to_dict(memory)

    async def approve_memory_candidate(
        self, *, tenant_id: str, user_id: str, memory_id: str
    ) -> dict[str, Any] | None:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        memory = self.db.execute(
            select(AgentMemory).where(
                AgentMemory.id == str(memory_id),
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.user_id == user_id,
                AgentMemory.status == MEMORY_STATUS_PENDING,
            )
        ).scalar_one_or_none()
        if memory is None:
            return None
        memory.status = MEMORY_STATUS_ACTIVE
        memory.source = "user_approved_consolidation"
        memory.updated_at = datetime.now(UTC)
        self.db.commit()
        return self._memory_to_dict(memory)

    async def reject_memory_candidate(
        self, *, tenant_id: str, user_id: str, memory_id: str
    ) -> bool:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        result = self.db.execute(
            delete(AgentMemory).where(
                AgentMemory.id == str(memory_id),
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.user_id == user_id,
                AgentMemory.status == MEMORY_STATUS_PENDING,
            )
        )
        self.db.commit()
        return bool(result.rowcount)

    async def clear_personal_memories(self, *, tenant_id: str, user_id: str) -> int:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        result = self.db.execute(
            delete(AgentMemory).where(
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.user_id == user_id,
                AgentMemory.scope.in_(("user", "session")),
            )
        )
        self.db.commit()
        return int(result.rowcount or 0)

    async def forget_memory(self, *, tenant_id: str, user_id: str, key: str) -> bool:
        """User can explicitly delete memories by key."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        normalized_key = key.strip()
        stmt = delete(AgentMemory).where(
            AgentMemory.tenant_id == tenant_id,
            AgentMemory.user_id == user_id,
            AgentMemory.scope.in_(("user", "session")),
            AgentMemory.key == normalized_key,
        )
        res = self.db.execute(stmt)
        self.db.commit()
        return res.rowcount > 0

    async def summarize_memories(self, *, tenant_id: str, user_id: str) -> str:
        """Create a deterministic synthesis fact from the highest-value memories."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        mems = await self.list_all_memories(tenant_id=tenant_id, user_id=user_id)
        if not mems:
            return "No memories to summarize."
        ranked = sorted(
            mems,
            key=lambda item: (
                float(item.get("importance_score") or 0.0),
                int(item.get("access_count") or 0),
            ),
            reverse=True,
        )[:10]
        bullet_text = "; ".join(
            f"{item['key']}: {str(item['value'])[:180]}" for item in ranked
        )
        summary = f"Synthesized {len(ranked)} high-value memories: {bullet_text}"
        await self.store_fact(
            tenant_id=tenant_id,
            user_id=user_id,
            key="historical_synthesis",
            value=summary,
            scope="user",
            tags=["summary", "memory"],
            importance_score=0.75,
            metadata_json={"source": "memory_summarizer", "input_count": len(mems)},
        )
        return summary

    async def evaluate_memory_quality(
        self, *, tenant_id: str, user_id: str, sample_queries: list[str] | None = None
    ) -> dict[str, Any]:
        """Return a lightweight retrieval-health report for memory regression checks."""
        memories = await self.list_all_memories(tenant_id=tenant_id, user_id=user_id)
        total = len(memories)
        embedded = sum(1 for item in memories if item.get("embedding_provider"))
        scope_breakdown: dict[str, int] = {}
        retention_breakdown: dict[str, int] = {}
        duplicate_hashes: set[str] = set()
        seen_hashes: set[str] = set()
        now = datetime.now(UTC)
        stale_count = 0
        stale_session_count = 0
        decay_scores: list[float] = []
        for item in memories:
            scope = str(item.get("scope") or "user")
            scope_breakdown[scope] = scope_breakdown.get(scope, 0) + 1
            memory = self.db.get(AgentMemory, item.get("id"))
            if memory is not None:
                retention_state = self._memory_retention_state(memory, now=now)
                retention_breakdown[retention_state] = (
                    retention_breakdown.get(retention_state, 0) + 1
                )
                if retention_state == "stale":
                    stale_count += 1
                    if scope == "session":
                        stale_session_count += 1
                decay_scores.append(self._decay_score(memory, now=now))
            digest = self._content_hash(
                key=str(item.get("key") or ""),
                value=str(item.get("value") or ""),
                scope=scope,
            )
            if digest in seen_hashes:
                duplicate_hashes.add(digest)
            seen_hashes.add(digest)
        duplicate_count = len(duplicate_hashes)
        retention_risk_count = stale_count + duplicate_count
        stale_ratio = (stale_count / total) if total else 0.0
        duplicate_ratio = (duplicate_count / total) if total else 0.0
        memory_health_score = max(
            0.0,
            min(
                100.0,
                (embedded / total if total else 1.0) * 40.0
                + max(0.0, 40.0 - stale_ratio * 40.0)
                + max(0.0, 20.0 - duplicate_ratio * 20.0),
            ),
        )
        query_reports = []
        for query in sample_queries or []:
            results = await self.search_memories(
                tenant_id=tenant_id, user_id=user_id, query=query, limit=3
            )
            query_reports.append(
                {
                    "query": query,
                    "matches": len(results),
                    "top_score": results[0]["relevance_score"] if results else 0.0,
                }
            )
        return {
            "memory_count": total,
            "embedded_count": embedded,
            "pgvector_count": sum(1 for item in memories if item.get("pgvector_ready")),
            "embedding_coverage": round(embedded / total, 4) if total else 1.0,
            "duplicate_count": duplicate_count,
            "scope_breakdown": scope_breakdown,
            "retention_breakdown": retention_breakdown,
            "stale_count": stale_count,
            "stale_session_count": stale_session_count,
            "average_decay_score": (
                round(sum(decay_scores) / len(decay_scores), 4) if decay_scores else 0.0
            ),
            "memory_health_score": round(memory_health_score, 2),
            "retention_risk_count": retention_risk_count,
            "sample_queries": query_reports,
        }

    async def cleanup_duplicate_memories(
        self, *, tenant_id: str, user_id: str
    ) -> dict[str, Any]:
        """Collapse duplicate memory rows so storage stays clean over time."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        memories = await self.list_all_memories(tenant_id=tenant_id, user_id=user_id)
        if not memories:
            return {
                "memory_count": 0,
                "duplicate_groups": 0,
                "removed_count": 0,
                "kept_count": 0,
            }

        rows = (
            self.db.execute(
                select(AgentMemory).where(
                    AgentMemory.tenant_id == tenant_id,
                    or_(
                        AgentMemory.user_id == user_id,
                        AgentMemory.scope.in_(("session", "global")),
                    ),
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[str, list[AgentMemory]] = {}
        for memory in rows:
            grouped.setdefault(self._dedupe_key(memory), []).append(memory)

        removed_count = 0
        duplicate_groups = 0
        kept_count = 0
        now = datetime.now(UTC)
        for group in grouped.values():
            if len(group) < 2:
                kept_count += len(group)
                continue
            duplicate_groups += 1
            group.sort(
                key=lambda memory: (
                    self._scope_priority_value(memory.scope),
                    float(memory.importance_score or 0.0),
                    int(memory.access_count or 0),
                    memory.updated_at or memory.created_at or now,
                    memory.created_at or now,
                ),
                reverse=True,
            )
            keeper = group[0]
            combined_tags: list[str] = []
            combined_metadata: dict[str, Any] = dict(keeper.metadata_json or {})
            max_importance = float(keeper.importance_score or 0.0)
            for duplicate in group[1:]:
                combined_tags.extend(
                    [str(tag) for tag in (duplicate.tags or []) if tag]
                )
                combined_metadata.update(dict(duplicate.metadata_json or {}))
                max_importance = max(
                    max_importance, float(duplicate.importance_score or 0.0)
                )
                self.db.delete(duplicate)
                removed_count += 1
            combined_tags.extend([str(tag) for tag in (keeper.tags or []) if tag])
            keeper.tags = sorted({tag for tag in combined_tags if tag})
            keeper.metadata_json = {
                **combined_metadata,
                "duplicate_group_count": len(group),
                "duplicate_memory_ids": [str(item.id) for item in group[1:]],
                "deduped_at": now.isoformat(),
            }
            keeper.importance_score = max_importance
            keeper.updated_at = now
            kept_count += 1

        if removed_count > 0:
            self.db.commit()

        return {
            "memory_count": len(rows),
            "duplicate_groups": duplicate_groups,
            "removed_count": removed_count,
            "kept_count": kept_count,
        }

    async def cleanup_stale_memories(
        self,
        *,
        tenant_id: str,
        user_id: str,
        retention_days: int = SESSION_MEMORY_RETENTION_DAYS,
    ) -> dict[str, Any]:
        """Remove expired session-scoped memories while leaving persistent facts intact."""
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        retention_days = max(1, int(retention_days or SESSION_MEMORY_RETENTION_DAYS))
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        rows = (
            self.db.execute(
                select(AgentMemory).where(
                    AgentMemory.tenant_id == tenant_id,
                    AgentMemory.user_id == user_id,
                    AgentMemory.scope == "session",
                )
            )
            .scalars()
            .all()
        )
        removed_count = 0
        retained_count = 0
        stale_ids: list[str] = []
        for memory in rows:
            timestamp = self._activity_timestamp(memory)
            if timestamp is not None and timestamp <= cutoff:
                stale_ids.append(str(memory.id))
                self.db.delete(memory)
                removed_count += 1
            else:
                retained_count += 1

        if removed_count > 0:
            self.db.commit()

        return {
            "memory_count": len(rows),
            "removed_count": removed_count,
            "retained_count": retained_count,
            "retention_days": retention_days,
            "stale_memory_ids": stale_ids,
        }

    async def evaluate_memory_retention(
        self,
        *,
        tenant_id: str,
        user_id: str,
        retention_days: int = SESSION_MEMORY_RETENTION_DAYS,
    ) -> dict[str, Any]:
        """Return a retention snapshot for lifecycle monitoring."""
        report = await self.evaluate_memory_quality(
            tenant_id=tenant_id, user_id=user_id
        )
        report["retention_policy"] = {
            "session_retention_days": retention_days,
            "decay_half_life_days": MEMORY_DECAY_HALF_LIFE_DAYS,
        }
        report["session_retention_days"] = retention_days
        return report

    async def preview_memory_lifecycle(
        self,
        *,
        tenant_id: str,
        user_id: str,
        retention_days: int = SESSION_MEMORY_RETENTION_DAYS,
        sample_queries: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a non-destructive lifecycle snapshot for operator visibility."""
        memories = await self.list_all_memories(tenant_id=tenant_id, user_id=user_id)
        now = datetime.now(UTC)
        stale_preview: list[dict[str, Any]] = []
        stale_ids: list[str] = []
        for item in memories:
            memory = self.db.get(AgentMemory, item.get("id"))
            if memory is None:
                continue
            retention_state = self._memory_retention_state(memory, now=now)
            if retention_state != "stale":
                continue
            stale_ids.append(str(memory.id))
            stale_preview.append(
                {
                    **self._memory_to_dict(memory),
                    "retention_state": retention_state,
                }
            )

        report = await self.evaluate_memory_quality(
            tenant_id=tenant_id,
            user_id=user_id,
            sample_queries=sample_queries,
        )
        report["retention_policy"] = {
            "session_retention_days": retention_days,
            "decay_half_life_days": MEMORY_DECAY_HALF_LIFE_DAYS,
        }
        report["session_retention_days"] = retention_days
        report["stale_memory_ids"] = stale_ids
        report["stale_preview_count"] = len(stale_ids)
        report["attention_memories"] = stale_preview[:10]
        return report


class TodoService:
    def __init__(self, db: Session, settings: Any | None = None):
        self.db = db
        self.settings = settings

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        return None

    @staticmethod
    def _normalize_owner_id(value: Any) -> str:
        return str(value)

    def upsert_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        content: str,
        active_form: str | None = None,
        status: str = "pending",
        priority: int = 0,
        thread_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        automation_json: dict[str, Any] | None = None,
        is_recurring: bool = False,
        enabled: bool = True,
        next_run_at: datetime | None = None,
        last_run_at: datetime | None = None,
    ) -> str:
        content = content.strip()
        if not content:
            raise ValueError("content is required")

        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        normalized_status = (
            status if status in {"pending", "in_progress", "completed"} else "pending"
        )
        normalized_active_form = (active_form or content).strip() or content
        normalized_priority = int(priority or 0)
        payload = dict(metadata_json) if isinstance(metadata_json, dict) else None
        automation_payload = (
            dict(automation_json) if isinstance(automation_json, dict) else {}
        )

        stmt = select(AgentTodo).where(
            AgentTodo.tenant_id == tenant_id,
            AgentTodo.user_id == user_id,
            AgentTodo.content == content,
        )
        if thread_id:
            stmt = stmt.where(AgentTodo.thread_id == thread_id)

        existing = self.db.execute(stmt).scalars().first()

        if existing:
            existing.active_form = normalized_active_form
            existing.status = normalized_status
            existing.priority = normalized_priority
            existing.thread_id = thread_id or existing.thread_id
            existing.metadata_json = (
                payload if payload is not None else dict(existing.metadata_json or {})
            )
            existing.automation_json = (
                automation_payload
                if automation_payload
                else dict(existing.automation_json or {})
            )
            existing.is_recurring = (
                1 if is_recurring else int(existing.is_recurring or 0)
            )
            existing.enabled = 1 if enabled else 0
            existing.next_run_at = next_run_at or existing.next_run_at
            existing.last_run_at = last_run_at or existing.last_run_at
            todo_id = str(existing.id)
        else:
            todo_id = str(generate_uuid7_with_fallback())
            todo = AgentTodo(
                id=todo_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=thread_id,
                content=content,
                active_form=normalized_active_form,
                status=normalized_status,
                priority=normalized_priority,
                metadata_json=payload or {},
                automation_json=automation_payload,
                is_recurring=1 if is_recurring else 0,
                enabled=1 if enabled else 0,
                next_run_at=next_run_at,
                last_run_at=last_run_at,
            )
            self.db.add(todo)

        self.db.commit()
        return todo_id

    def create_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        content: str,
        active_form: str,
        status: str = "pending",
        priority: int = 0,
        thread_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        automation_json: dict[str, Any] | None = None,
        is_recurring: bool = False,
        enabled: bool = True,
        next_run_at: datetime | None = None,
        last_run_at: datetime | None = None,
    ) -> dict[str, Any]:
        content = content.strip()
        active_form = active_form.strip()
        if not content:
            raise ValueError("content is required")
        if not active_form:
            active_form = content

        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        todo = AgentTodo(
            id=str(generate_uuid7_with_fallback()),
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=thread_id,
            content=content,
            active_form=active_form,
            status=(
                status
                if status in {"pending", "in_progress", "completed"}
                else "pending"
            ),
            priority=int(priority or 0),
            metadata_json=dict(metadata_json or {}),
            automation_json=dict(automation_json or {}),
            is_recurring=1 if is_recurring else 0,
            enabled=1 if enabled else 0,
            next_run_at=next_run_at,
            last_run_at=last_run_at,
        )
        self.db.add(todo)
        self.db.commit()
        self.db.refresh(todo)
        return self._task_to_dict(todo)

    def _task_to_dict(self, task: AgentTodo) -> dict[str, Any]:
        return {
            "id": str(task.id),
            "content": task.content,
            "status": task.status,
            "activeForm": task.active_form,
            "priority": task.priority or 0,
            "thread_id": task.thread_id,
            "metadata_json": dict(task.metadata_json or {}),
            "automation_json": dict(task.automation_json or {}),
            "is_recurring": bool(task.is_recurring),
            "enabled": bool(task.enabled),
            "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
            "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    async def update_todos(
        self, *, tenant_id: str, user_id: str, todos: list[dict[str, Any]]
    ) -> list[str]:
        results = []
        for todo_data in todos:
            todo_id = self.upsert_task(
                tenant_id=tenant_id,
                user_id=user_id,
                content=str(todo_data.get("content") or ""),
                active_form=str(
                    todo_data.get("activeForm")
                    or todo_data.get("active_form")
                    or todo_data.get("content")
                    or ""
                ),
                status=str(todo_data.get("status") or "pending"),
                priority=int(todo_data.get("priority") or 0),
                thread_id=(
                    str(todo_data.get("thread_id") or todo_data.get("threadId") or "")
                    or None
                ),
                metadata_json=todo_data.get("metadata_json")
                or todo_data.get("metadata")
                or {},
                automation_json=todo_data.get("automation_json")
                or todo_data.get("automation"),
                is_recurring=bool(
                    todo_data.get("is_recurring") or todo_data.get("recurring")
                ),
                enabled=bool(todo_data.get("enabled", True)),
                next_run_at=self._parse_datetime(todo_data.get("next_run_at")),
                last_run_at=self._parse_datetime(todo_data.get("last_run_at")),
            )
            results.append(todo_id)
        return results

    async def list_todos(self, *, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        stmt = (
            select(AgentTodo)
            .where(
                AgentTodo.tenant_id == tenant_id,
                AgentTodo.user_id == user_id,
                AgentTodo.status != "deleted",
            )
            .order_by(AgentTodo.priority.desc(), AgentTodo.created_at.asc())
        )
        todos = self.db.execute(stmt).scalars().all()
        return [self._task_to_dict(t) for t in todos]

    def get_task(
        self, *, tenant_id: str, user_id: str, task_id: str
    ) -> AgentTodo | None:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        stmt = select(AgentTodo).where(
            AgentTodo.id == task_id,
            AgentTodo.tenant_id == tenant_id,
            AgentTodo.user_id == user_id,
            AgentTodo.status != "deleted",
        )
        return self.db.execute(stmt).scalars().first()

    def update_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        task_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        task = self.get_task(tenant_id=tenant_id, user_id=user_id, task_id=task_id)
        if task is None:
            raise ValueError("task not found")

        if "content" in updates and updates["content"] is not None:
            content = str(updates["content"]).strip()
            if content:
                task.content = content
        active_form_value = updates.get("activeForm")
        if active_form_value is None:
            active_form_value = updates.get("active_form")
        if active_form_value is not None:
            active_form = str(active_form_value).strip()
            if active_form:
                task.active_form = active_form
        if "status" in updates and updates["status"] is not None:
            status = str(updates["status"])
            task.status = (
                status
                if status in {"pending", "in_progress", "completed"}
                else task.status
            )
        if "priority" in updates and updates["priority"] is not None:
            task.priority = int(updates["priority"])
        if "thread_id" in updates:
            thread_id = updates["thread_id"]
            task.thread_id = str(thread_id) if thread_id else None
        if "metadata_json" in updates and updates["metadata_json"] is not None:
            metadata_json = updates["metadata_json"]
            task.metadata_json = (
                dict(metadata_json) if isinstance(metadata_json, dict) else {}
            )
        if "automation_json" in updates and updates["automation_json"] is not None:
            automation_json = updates["automation_json"]
            task.automation_json = (
                dict(automation_json) if isinstance(automation_json, dict) else {}
            )
        if "is_recurring" in updates and updates["is_recurring"] is not None:
            task.is_recurring = 1 if bool(updates["is_recurring"]) else 0
        if "enabled" in updates and updates["enabled"] is not None:
            task.enabled = 1 if bool(updates["enabled"]) else 0
        if "next_run_at" in updates:
            task.next_run_at = self._parse_datetime(updates["next_run_at"])
        if "last_run_at" in updates:
            task.last_run_at = self._parse_datetime(updates["last_run_at"])

        self.db.commit()
        self.db.refresh(task)
        return self._task_to_dict(task)

    def delete_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        task_id: str,
    ) -> None:
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        task = (
            self.db.execute(
                select(AgentTodo).where(
                    AgentTodo.id == task_id,
                    AgentTodo.tenant_id == tenant_id,
                    AgentTodo.user_id == user_id,
                )
            )
            .scalars()
            .first()
        )
        if task is None:
            raise ValueError("task not found")
        task.status = "deleted"
        self.db.commit()

    def list_due_recurring_tasks(
        self, *, tenant_id: str, user_id: str
    ) -> list[AgentTodo]:
        now = datetime.now(UTC)
        tenant_id = self._normalize_owner_id(tenant_id)
        user_id = self._normalize_owner_id(user_id)
        stmt = (
            select(AgentTodo)
            .where(
                AgentTodo.tenant_id == tenant_id,
                AgentTodo.user_id == user_id,
                AgentTodo.enabled == 1,
                AgentTodo.is_recurring == 1,
                AgentTodo.next_run_at.is_not(None),
                AgentTodo.next_run_at <= now,
            )
            .order_by(AgentTodo.next_run_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def mark_task_run(
        self,
        *,
        task: AgentTodo,
        next_run_at: datetime | None,
        last_run_at: datetime | None = None,
        status: str | None = None,
    ) -> None:
        task.last_run_at = last_run_at or datetime.now(UTC)
        task.next_run_at = next_run_at
        if status is not None:
            task.status = status
        self.db.commit()
