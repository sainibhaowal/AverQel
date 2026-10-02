from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.conversation_retrieval_chunk import DeepSpaceConversationRetrievalChunk
from app.deepspace.models.message import Message
from app.documents.repositories.chunks import RetrievedChunkRow
from app.ingestion.services.embedding_service import EmbeddingService
from app.query.services.reranker_service import RerankerService

logger = logging.getLogger(__name__)

MAX_CHAT_RETRIEVAL_CANDIDATES = 40
MAX_CHAT_RETRIEVAL_RESULTS = 5
MAX_INDEXED_MESSAGE_CHARS = 12_000
CHAT_CHUNK_CHARS = 1_600
CHAT_CHUNK_OVERLAP = 160


class ConversationRetrievalService:
    """Selective, bounded retrieval over visible DeepSpace chat content.

    The normal chat path never calls this service. It is used by explicit
    history/retrospective requests and by the low-priority indexing worker.
    Retrieved content is reference material only and is always scoped to the
    authenticated tenant, user, and conversation.
    """

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    @staticmethod
    def _hash(role: str, content: str, version_id: uuid.UUID | None, chunk_index: int) -> str:
        payload = f"{role}\n{version_id or ''}\n{chunk_index}\n{content}".encode()
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _chunks(content: str) -> list[str]:
        normalized = " ".join(content.split())
        if not normalized:
            return []
        if len(normalized) <= CHAT_CHUNK_CHARS:
            return [normalized]
        result: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(len(normalized), start + CHAT_CHUNK_CHARS)
            result.append(normalized[start:end])
            if end >= len(normalized):
                break
            start = max(start + 1, end - CHAT_CHUNK_OVERLAP)
        return result

    def index_conversation(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> dict[str, int]:
        messages = (
            self.db.execute(
                select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.user_id == user_id,
                    Conversation.id == conversation_id,
                    Conversation.kind == "deepspace",
                    Message.role.in_(("user", "assistant")),
                )
                .options(selectinload(Message.active_version))
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
            .scalars()
            .unique()
            .all()
        )
        active_keys: set[tuple[uuid.UUID, uuid.UUID | None, int]] = set()
        existing = (
            self.db.execute(
                select(DeepSpaceConversationRetrievalChunk).where(
                    DeepSpaceConversationRetrievalChunk.tenant_id == tenant_id,
                    DeepSpaceConversationRetrievalChunk.user_id == user_id,
                    DeepSpaceConversationRetrievalChunk.conversation_id == conversation_id,
                )
            )
            .scalars()
            .all()
        )
        existing_by_hash = {str(row.content_hash): row for row in existing}
        rows_to_embed: list[tuple[Message, uuid.UUID | None, int, str, str]] = []
        for message in messages:
            version = message.active_version
            content = str(version.content if version is not None else message.content or "")
            if not content.strip():
                continue
            version_id = version.id if version is not None else None
            for chunk_index, chunk in enumerate(self._chunks(content[:MAX_INDEXED_MESSAGE_CHARS])):
                content_hash = self._hash(message.role, chunk, version_id, chunk_index)
                active_keys.add((message.id, version_id, chunk_index))
                if content_hash not in existing_by_hash:
                    rows_to_embed.append((message, version_id, chunk_index, chunk, content_hash))

        removed = 0
        for row in existing:
            key = (row.message_id, row.message_version_id, int(row.chunk_index or 0))
            if key not in active_keys:
                self.db.delete(row)
                removed += 1

        indexed = 0
        if rows_to_embed:
            texts = [f"{item[0].role}: {item[3]}" for item in rows_to_embed]
            try:
                embedding_result = EmbeddingService(
                    self.settings, self.db
                ).embed_many_with_metadata(
                    texts,
                    tenant_id=tenant_id,
                    actor_user_id=user_id,
                )
            except Exception:
                logger.warning(
                    "DeepSpace conversation indexing deferred after embedding failure",
                    exc_info=True,
                )
                embedding_result = None
            if embedding_result is not None:
                for item, vector in zip(rows_to_embed, embedding_result.vectors, strict=True):
                    message, version_id, chunk_index, chunk, content_hash = item
                    row = DeepSpaceConversationRetrievalChunk(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        message_id=message.id,
                        message_version_id=version_id,
                        role=message.role,
                        content=chunk,
                        content_hash=content_hash,
                        chunk_index=chunk_index,
                        metadata_json={"source": "visible_chat", "reference_only": True},
                        embedding_vector=vector,
                        embedding_provider=embedding_result.metadata.provider,
                        embedding_model=embedding_result.metadata.model,
                        embedding_version="deepspace-chat-v1",
                        indexed_at=datetime.now(UTC),
                    )
                    self.db.add(row)
                    indexed += 1
        self.db.flush()
        return {"indexed": indexed, "removed": removed, "messages": len(messages)}

    def search_chat(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        query: str,
        limit: int = MAX_CHAT_RETRIEVAL_RESULTS,
    ) -> list[dict[str, Any]]:
        query = " ".join(str(query or "").split())[:1000]
        if not query:
            return []
        try:
            self.index_conversation(
                tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
            )
        except Exception:
            # During a rolling deployment the additive index migration may
            # not have reached every worker yet. Keep explicit history lookup
            # useful without making normal chat a migration dependency.
            logger.warning(
                "Conversation retrieval index unavailable; using bounded lexical fallback",
                exc_info=True,
            )
            return self._legacy_lexical_search(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                query=query,
                limit=limit,
            )
        query_embedding: list[float] | None = None
        try:
            query_embedding = (
                EmbeddingService(self.settings, self.db)
                .embed_many_with_metadata([query], tenant_id=tenant_id, actor_user_id=user_id)
                .vectors[0]
            )
        except Exception:
            logger.info(
                "Semantic chat retrieval unavailable; using lexical retrieval", exc_info=True
            )

        candidates: dict[uuid.UUID, tuple[DeepSpaceConversationRetrievalChunk, float, float]] = {}
        if query_embedding:
            distance = DeepSpaceConversationRetrievalChunk.embedding_vector.l2_distance(
                query_embedding
            )
            vector_rows = self.db.execute(
                select(DeepSpaceConversationRetrievalChunk, distance.label("distance"))
                .where(
                    DeepSpaceConversationRetrievalChunk.tenant_id == tenant_id,
                    DeepSpaceConversationRetrievalChunk.user_id == user_id,
                    DeepSpaceConversationRetrievalChunk.conversation_id == conversation_id,
                    DeepSpaceConversationRetrievalChunk.embedding_vector.is_not(None),
                )
                .order_by(distance.asc())
                .limit(MAX_CHAT_RETRIEVAL_CANDIDATES)
            ).all()
            for row, distance_value in vector_rows:
                semantic = 1.0 / (1.0 + max(0.0, float(distance_value or 0.0)))
                candidates[row.id] = (row, semantic, 0.0)

        try:
            ts_query = func.plainto_tsquery("simple", query)
            lexical_rows = self.db.execute(
                select(
                    DeepSpaceConversationRetrievalChunk,
                    func.ts_rank_cd(
                        DeepSpaceConversationRetrievalChunk.search_vector, ts_query
                    ).label("rank"),
                )
                .where(
                    DeepSpaceConversationRetrievalChunk.tenant_id == tenant_id,
                    DeepSpaceConversationRetrievalChunk.user_id == user_id,
                    DeepSpaceConversationRetrievalChunk.conversation_id == conversation_id,
                    DeepSpaceConversationRetrievalChunk.search_vector.op("@@")(ts_query),
                )
                .order_by(
                    func.ts_rank_cd(
                        DeepSpaceConversationRetrievalChunk.search_vector, ts_query
                    ).desc()
                )
                .limit(MAX_CHAT_RETRIEVAL_CANDIDATES)
            ).all()
            max_rank = max((float(rank or 0.0) for _row, rank in lexical_rows), default=1.0)
            for row, rank in lexical_rows:
                current = candidates.get(row.id)
                lexical = float(rank or 0.0) / max_rank if max_rank else 0.0
                candidates[row.id] = (row, current[1] if current else 0.0, lexical)
        except Exception:
            logger.info(
                "Lexical chat retrieval unavailable; using semantic candidates", exc_info=True
            )

        scored: list[tuple[float, DeepSpaceConversationRetrievalChunk]] = []
        for row, semantic, lexical in candidates.values():
            score = semantic * 0.68 + lexical * 0.32
            if score >= 0.08:
                scored.append((score, row))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        answer_limit = max(1, min(int(limit or 1), MAX_CHAT_RETRIEVAL_RESULTS))
        candidate_rows = [
            RetrievedChunkRow(
                document_id=conversation_id,
                chunk_id=row.id,
                filename="DeepSpace conversation",
                content=row.content,
                similarity_score=score,
                source_type="deepspace_chat",
                chunk_index=int(row.chunk_index or 0),
            )
            for score, row in scored[:MAX_CHAT_RETRIEVAL_CANDIDATES]
        ]
        indexed_rows = {row.id: row for _score, row in scored[:MAX_CHAT_RETRIEVAL_CANDIDATES]}
        retrieval_method = "hybrid_vector_lexical"
        if candidate_rows:
            try:
                reranked = RerankerService(self.db, self.settings).rerank_chunks(
                    tenant_id=tenant_id,
                    workspace_id=None,
                    actor_user_id=user_id,
                    query=query,
                    chunks=candidate_rows,
                    top_n=answer_limit,
                )
                if reranked.metadata.applied:
                    candidate_rows = reranked.chunks
                    retrieval_method = "hybrid_vector_lexical_reranked"
                else:
                    candidate_rows = candidate_rows[:answer_limit]
            except Exception:
                logger.info("Chat reranking unavailable; preserving hybrid order", exc_info=True)
                candidate_rows = candidate_rows[:answer_limit]
        selected = [
            (row.similarity_score, indexed_rows[row.chunk_id], row)
            for row in candidate_rows[:answer_limit]
            if row.chunk_id in indexed_rows
        ]
        return [
            {
                "message_id": str(index_row.message_id),
                "conversation_id": str(conversation_id),
                "role": index_row.role,
                "content": index_row.content[:900],
                "created_at": index_row.created_at.isoformat() if index_row.created_at else None,
                "relevance_score": round(score, 6),
                "retrieval_method": retrieval_method,
                "reference_only": True,
            }
            for score, index_row, _reranked_row in selected
        ]

    def _legacy_lexical_search(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Bounded rollout fallback for workers before the index migration."""
        messages = (
            self.db.execute(
                select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.user_id == user_id,
                    Conversation.id == conversation_id,
                    Conversation.kind == "deepspace",
                    Message.role.in_(("user", "assistant")),
                )
                .options(selectinload(Message.active_version))
                .order_by(Message.created_at.desc(), Message.id.desc())
            )
            .scalars()
            .unique()
            .all()
        )
        needle = query.casefold()
        answer_limit = max(1, min(int(limit or 1), MAX_CHAT_RETRIEVAL_RESULTS))
        results: list[dict[str, Any]] = []
        for message in messages:
            version = message.active_version
            content = str(version.content if version is not None else message.content or "")
            if needle not in content.casefold():
                continue
            results.append(
                {
                    "message_id": str(message.id),
                    "conversation_id": str(conversation_id),
                    "role": message.role,
                    "content": content[:900],
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                    "relevance_score": 1.0,
                    "retrieval_method": "legacy_lexical_fallback",
                    "reference_only": True,
                }
            )
            if len(results) >= answer_limit:
                break
        return results
