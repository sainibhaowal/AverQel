from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.core.config import Settings
from app.core.context import get_trace_id
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.models.query.query_citation import QueryCitation
from app.documents.repositories.chunks import ChunksRepository
from app.documents.repositories.collections import CollectionsRepository
from app.documents.repositories.documents import DocumentsRepository
from app.ingestion.repositories.ingestion_jobs import IngestionJobsRepository
from app.repositories.query.chat import ChatRepository
from app.repositories.query.queries import QueriesRepository
from app.schemas.query.structured_response import (
    ReasoningTraceModel,
    StructuredAnswerResponse,
)
from app.providers.services.selection_service import ProviderSelectionService
from app.providers.services.types import ProviderSelectionCandidate
from app.services.query.answer_service import AnswerService, StreamEvent
from app.services.query.followup_service import FollowupService
from app.services.query.query_classifier import QueryClassifier
from app.services.query.retrieval_service import RetrievalService, RetrievedChunk
from app.services.query.snippet_service import SnippetService
from app.services.query.trace_service import TraceCollector
from app.services.system.billing_service import BillingService
from app.services.system.cache_service import QueryCacheService
from app.services.system.metrics_service import (
    QUERY_CACHE_EVENTS_TOTAL,
    QUERY_PIPELINE_DURATION_SECONDS,
)

logger = logging.getLogger(__name__)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017

_DOCUMENT_COUNT_QUERY_RE = re.compile(
    r"(?i)(?:\bhow many\b|\bnumber of\b|\bcount\b).*\b(?:documents?|files?|pdfs?)\b|"
    r"\b(?:documents?|files?|pdfs?)\b.*\b(?:count|total|number)\b"
)
_DOCUMENT_LIST_QUERY_RE = re.compile(
    r"(?i)\b(?:which|what|list|show)\b.*\b(?:documents?|files?|pdfs?)\b|"
    r"\bwhat documents do you have\b|"
    r"\bwhich documents do you have\b"
)
_DOCUMENT_METADATA_QUERY_RE = re.compile(
    r"(?i)\b(latest|last uploaded|recent|indexed|failed|queued|embedding model|embedder|storage|size|sizes|total storage|uploaded today|uploaded yesterday|this week|this month|named|name contains|filename)\b"
)
_DOC_STATUS_RE = re.compile(
    r"(?i)\b(indexed|failed|dead[_ -]?lettered|queued|embedding|chunking|parsing|downloading)\b"
)
_NAMED_FILTER_RE = re.compile(
    r'(?i)\b(?:named|filename|name contains)\s+"([^"]+)"|\b(?:named|filename|name contains)\s+([^\n]+)$'
)
_COLLECTION_QUERY_RE = re.compile(r"(?i)\bcollection[s]?\b")
_QUALITY_QUERY_RE = re.compile(
    r"(?i)\b(low quality|quality|confidence|yield|quarantined)\b"
)
_OCR_VISION_QUERY_RE = re.compile(r"(?i)\b(ocr|vision)\b")
_FAILURE_DIAG_QUERY_RE = re.compile(
    r"(?i)\b(why did .* fail|failed ingestion|failure reason|last error|dead letter)\b"
)
_CONTENT_FILTER_QUERY_RE = re.compile(
    r"(?i)\b(mention|mentions|contains|contain|talk about|discuss|about)\b"
)
_QUOTED_TERM_RE = re.compile(r'"([^"]+)"')
_COMPARISON_QUERY_RE = re.compile(
    r"(?i)\b(compare|comparison|differences?|versus|vs\.?|side[- ]by[- ]side)\b"
)
_DOCUMENT_CONTENT_OVERRIDE_RE = re.compile(
    r"(?i)\b(?:inside|within|from|in)\s+(?:the\s+)?(?:pdf|document|file|paper)\b|"
    r"\b(?:title|topic|summary|abstract|introduction|section)\b.*\b(?:inside|within|from|in)\b|"
    r"\bwhat is the title of\b.*\b(?:pdf|document|paper|content)\b|"
    r"\btext inside\b|\bcontent inside\b|"
    r"\b(?:heading|headings|subheading|subheadings|outline|section headings?)\b"
)
_DOCUMENT_CONTENT_INTENT_RE = re.compile(
    r"(?i)\b("
    r"explain|summari[sz]e|describe|tell me about|walk me through|interpret|analy[sz]e|"
    r"what does|why does|how does|compare|contrast|outline|headings?|subheadings?|"
    r"sections?|table\b|figure\b|diagram\b|chart\b|line\b|paragraph\b|quote\b|passage\b|"
    r"topic\b|abstract\b|introduction\b|conclusion\b|method(?:s)?\b|results?\b|discussion\b"
    r")\b"
)
_DOCUMENT_OPERATIONAL_METADATA_RE = re.compile(
    r"(?i)\b("
    r"how many|number of|count|which documents do you have|what documents do you have|"
    r"list all uploaded|uploaded|latest|last uploaded|recent|indexed|failed|queued|"
    r"storage|size|sizes|total storage|collection|collections|embedding model|embedder|"
    r"provider|runtime|filename|named|name contains|status"
    r")\b"
)
_DOCUMENT_OUTLINE_QUERY_RE = re.compile(
    r"(?i)\b(?:show|list|give|extract|what are)\b.*\b(?:heading|headings|subheading|subheadings|outline|sections?)\b|"
    r"\b(?:heading|headings|subheading|subheadings|outline|table of contents)\b"
)
_SECTION_HEADING_LINE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\s+)?(?:abstract|introduction|background|preliminar(?:y|ies)|related work|method(?:s)?|approach|architecture|experiments?|results?|discussion|conclusion|references|appendix\b.*)$",
    re.IGNORECASE,
)
_TITLE_CANDIDATE_RE = re.compile(r"^[A-Z][A-Za-z0-9,:;()'\"/+& -]{12,140}$")
_COLLECTION_ANALYSIS_QUERY_RE = re.compile(
    r"(?i)\b(best collection|strongest collection|collection summary|summari[sz]e .*collection|"
    r"strongest coverage|best collection for|best collection to|which collection .*coverage)\b"
)
_COLLECTION_FILTER_RE = re.compile(
    r'(?i)\b(?:in|from|inside)\s+collection\s+"([^"]+)"|'
    r"\bcollection\s+named\s+\"([^\"]+)\"|"
    r"\bcollection\s+([a-z0-9][a-z0-9 _/\-]{1,80})"
)
_EMBEDDING_MODEL_FILTER_RE = re.compile(
    r'(?i)\b(?:using|use|with)\s+(?:embedding model|embedder)\s+"([^"]+)"|'
    r"\b(?:using|use|with)\s+(?:embedding model|embedder)\s+([a-z0-9._:/\-]+)|"
    r"\b(?:embedding model|embedder)\s+\"([^\"]+)\""
)
_BATCH_QUESTION_SPLIT_RE = re.compile(r"\n+")
_FALLBACK_LIST_RE = re.compile(r"(?i)\b(if not|otherwise|else|if none|if no match)\b")
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


@dataclass(slots=True)
class DocumentWorkspaceRecord:
    document: Any
    embedding_provider: str | None
    embedding_model: str | None
    embedded_chunk_count: int
    chunk_count: int
    avg_chunk_quality: float | None
    ingestion_job: Any | None
    collections: list[str]


@dataclass(slots=True)
class QueryExecutionResult:
    answer: str | StructuredAnswerResponse
    confidence: float
    citations: list[dict[str, Any]]
    trace_id: str
    cached: bool
    conversation_id: uuid.UUID
    reasoning_trace: ReasoningTraceModel | None = None


class QueryService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.documents = DocumentsRepository(db)
        self.chunks = ChunksRepository(db)
        self.collections = CollectionsRepository(db)
        self.jobs = IngestionJobsRepository(db)
        self.retrieval = RetrievalService(db, settings)
        self.answer = AnswerService(settings.query_no_result_answer_text, settings)
        self.followups = FollowupService(self.answer)
        self.provider_selection = ProviderSelectionService(db, settings)
        self.cache = QueryCacheService()
        self.queries = QueriesRepository(db)
        self.chat = ChatRepository(db)
        self.billing = BillingService(db)

    # ------------------------------------------------------------------
    # Public streaming API
    # ------------------------------------------------------------------

    async def stream_execute(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        top_k: int,
        filters: dict[str, Any],
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
        source_types: list[str] | None,
        min_extraction_coverage: float | None,
        max_extraction_coverage: float | None,
        conversation_id: uuid.UUID | None = None,
        conversation_kind: str = "query",
        search_mode: str = "hybrid",
        thinking_enabled: bool = False,
    ) -> AsyncIterator[str]:
        self._enforce_quota(auth)
        self._validate_top_k(top_k)

        normalized_query = self.normalize_query(query_text)
        self.normalize_filters(filters)
        conversation = self._resolve_or_create_conversation(
            auth=auth,
            query_text=query_text,
            conversation_id=conversation_id,
            conversation_kind=conversation_kind,
        )
        resolved_conversation_id = conversation.id

        self.chat.add_message(
            tenant_id=auth.tenant_id,
            conversation_id=resolved_conversation_id,
            kind=conversation_kind,
            role="user",
            content=query_text,
        )
        self._maybe_commit()

        provider_candidates = self.provider_selection.resolve_chat(
            tenant_id=auth.tenant_id,
            workspace_id=None,
            actor_user_id=auth.user_id,
        ).candidates

        outline_grounding = self._maybe_build_document_outline_grounding(
            auth=auth,
            query_text=query_text,
            document_ids=document_ids,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )
        if outline_grounding is not None:
            start_event = StreamEvent(
                event="start",
                data={
                    "message_id": str(generate_uuid7_with_fallback()),
                    "conversation_id": str(resolved_conversation_id),
                    "started_at": datetime.now(tz=UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "operation": "new_turn",
                },
            )
            yield AnswerService.encode_sse_event(start_event)
            previous_messages = self._build_previous_messages(
                tenant_id=auth.tenant_id,
                conversation_id=resolved_conversation_id,
            )
            trace_id = self._resolve_trace_id()
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="meta",
                    data={
                        "conversation_id": str(resolved_conversation_id),
                        "message_id": None,
                        "trace_id": trace_id,
                        "confidence": 1.0,
                        "cached": False,
                        "query_type": "document_outline",
                        "source_count": 0,
                    },
                )
            )
            full_answer_parts: list[str] = []
            latest_replace_content: str | None = None
            outline_thinking_parts: list[str] = []
            async for event in self.answer.stream_synthesize_events_async(
                retrieved_chunks=self._build_outline_grounding_chunks(
                    query_text=query_text,
                    grounding_text=outline_grounding,
                ),
                query_text=self._build_outline_llm_query(query_text),
                tenant_id=auth.tenant_id,
                previous_messages=previous_messages,
                query_type=QueryClassifier.classify(query_text),
                provider_candidates=provider_candidates,
                thinking_enabled=thinking_enabled,
            ):
                if event.event == "delta":
                    text = str(event.data.get("text", ""))
                    if text:
                        full_answer_parts.append(text)
                elif event.event == "thinking":
                    text = str(event.data.get("text", ""))
                    if text:
                        outline_thinking_parts.append(text)
                elif event.event == "replace":
                    replace_content = str(event.data.get("content", "")).strip()
                    if replace_content:
                        latest_replace_content = replace_content
                yield AnswerService.encode_sse_event(event)

            final_text = latest_replace_content or "".join(full_answer_parts).strip()
            followup_items = self._generate_followups(
                query_text=query_text,
                answer_text=final_text,
                tenant_id=auth.tenant_id,
                previous_messages=previous_messages,
                provider_candidates=provider_candidates,
            )
            followup_status_history = self._followup_status_history(followup_items)
            for event in self._build_followup_events(followup_items):
                yield AnswerService.encode_sse_event(event)

            if not final_text:
                yield AnswerService.encode_sse_event(
                    StreamEvent(
                        event="error",
                        data={
                            "code": "STREAM_EMPTY_PROVIDER_RESPONSE",
                            "message": "The chat model did not return an answer.",
                        },
                    )
                )
                return

            try:
                self.chat.add_message(
                    tenant_id=auth.tenant_id,
                    conversation_id=resolved_conversation_id,
                    kind=conversation_kind,
                    role="assistant",
                    content=final_text,
                    metadata_json={
                        "trace_id": trace_id,
                        "confidence": 1.0,
                        "citations": [],
                        "search_mode": search_mode,
                        "provider": {
                            "type": "llm_grounded",
                            "model": "document_outline",
                        },
                        "reasoning_trace": None,
                        "status_history": followup_status_history,
                        "files": [],
                        "output": [],
                        "thinking": (
                            {
                                "content": "".join(outline_thinking_parts).strip(),
                                "enabled": thinking_enabled,
                            }
                            if outline_thinking_parts
                            else None
                        ),
                        "follow_up_suggestions": followup_items,
                    },
                )
                self._maybe_commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to persist grounded outline assistant response."
                )
            yield AnswerService.encode_sse_event(
                StreamEvent(event="done", data={"completed": True})
            )
            return

        inventory_answer = self._maybe_build_document_inventory_answer(
            auth=auth,
            query_text=query_text,
            document_ids=document_ids,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )
        if inventory_answer is not None:
            previous_messages = self._build_previous_messages(
                tenant_id=auth.tenant_id,
                conversation_id=resolved_conversation_id,
            )
            start_event = StreamEvent(
                event="start",
                data={
                    "message_id": str(generate_uuid7_with_fallback()),
                    "conversation_id": str(resolved_conversation_id),
                    "started_at": datetime.now(tz=UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "operation": "new_turn",
                },
            )
            yield AnswerService.encode_sse_event(start_event)
            trace_id = self._resolve_trace_id()
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="meta",
                    data={
                        "conversation_id": str(resolved_conversation_id),
                        "message_id": None,
                        "trace_id": trace_id,
                        "confidence": 1.0,
                        "cached": False,
                        "query_type": "document_inventory",
                        "source_count": 0,
                    },
                )
            )
            if not provider_candidates:
                yield AnswerService.encode_sse_event(
                    StreamEvent(
                        event="replace",
                        data={
                            "content": inventory_answer,
                            "format": "markdown",
                            "structured": None,
                        },
                    )
                )
                followup_items = self._generate_followups(
                    query_text=query_text,
                    answer_text=inventory_answer,
                    tenant_id=auth.tenant_id,
                    previous_messages=previous_messages,
                    provider_candidates=[],
                )
                for event in self._build_followup_events(followup_items):
                    yield AnswerService.encode_sse_event(event)
                yield AnswerService.encode_sse_event(
                    StreamEvent(event="done", data={"completed": True})
                )
                followup_status_history = self._followup_status_history(followup_items)
                try:
                    self.chat.add_message(
                        tenant_id=auth.tenant_id,
                        conversation_id=resolved_conversation_id,
                        kind=conversation_kind,
                        role="assistant",
                        content=inventory_answer,
                        metadata_json={
                            "trace_id": trace_id,
                            "confidence": 1.0,
                            "citations": [],
                            "search_mode": search_mode,
                            "provider": {
                                "type": "system",
                                "model": "document_inventory_fallback",
                            },
                            "reasoning_trace": None,
                            "status_history": followup_status_history,
                            "files": [],
                            "output": [],
                            "thinking": None,
                            "follow_up_suggestions": followup_items,
                        },
                    )
                    self._maybe_commit()
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to persist fallback inventory assistant response."
                    )
                return
            inventory_chunks = self._build_inventory_grounding_chunks(
                query_text=query_text,
                grounding_text=inventory_answer,
            )
            full_answer_parts = []
            latest_replace_content = None
            inventory_thinking_parts: list[str] = []
            async for event in self.answer.stream_synthesize_events_async(
                retrieved_chunks=inventory_chunks,
                query_text=self._build_inventory_llm_query(query_text),
                tenant_id=auth.tenant_id,
                previous_messages=previous_messages,
                query_type=QueryClassifier.classify(query_text),
                provider_candidates=provider_candidates,
                thinking_enabled=thinking_enabled,
            ):
                if event.event == "delta":
                    text = str(event.data.get("text", ""))
                    if text:
                        full_answer_parts.append(text)
                elif event.event == "thinking":
                    text = str(event.data.get("text", ""))
                    if text:
                        inventory_thinking_parts.append(text)
                elif event.event == "replace":
                    replace_content = str(event.data.get("content", "")).strip()
                    if replace_content:
                        latest_replace_content = replace_content
                yield AnswerService.encode_sse_event(event)

            final_text = latest_replace_content or "".join(full_answer_parts).strip()
            followup_items = self._generate_followups(
                query_text=query_text,
                answer_text=final_text,
                tenant_id=auth.tenant_id,
                previous_messages=previous_messages,
                provider_candidates=provider_candidates,
            )
            followup_status_history = self._followup_status_history(followup_items)
            for event in self._build_followup_events(followup_items):
                yield AnswerService.encode_sse_event(event)

            if not final_text:
                yield AnswerService.encode_sse_event(
                    StreamEvent(
                        event="error",
                        data={
                            "code": "STREAM_EMPTY_PROVIDER_RESPONSE",
                            "message": "The chat model did not return an answer.",
                        },
                    )
                )
                return

            try:
                self.chat.add_message(
                    tenant_id=auth.tenant_id,
                    conversation_id=resolved_conversation_id,
                    kind=conversation_kind,
                    role="assistant",
                    content=final_text,
                    metadata_json={
                        "trace_id": trace_id,
                        "confidence": 1.0,
                        "citations": [],
                        "search_mode": search_mode,
                        "provider": {
                            "type": "llm_grounded",
                            "model": "document_inventory",
                        },
                        "reasoning_trace": None,
                        "status_history": followup_status_history,
                        "files": [],
                        "output": [],
                        "thinking": (
                            {
                                "content": "".join(inventory_thinking_parts).strip(),
                                "enabled": thinking_enabled,
                            }
                            if inventory_thinking_parts
                            else None
                        ),
                        "follow_up_suggestions": followup_items,
                    },
                )
                self._maybe_commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to persist grounded inventory assistant response."
                )
            yield AnswerService.encode_sse_event(
                StreamEvent(event="done", data={"completed": True})
            )
            return

        start_event = StreamEvent(
            event="start",
            data={
                "message_id": str(generate_uuid7_with_fallback()),
                "conversation_id": str(resolved_conversation_id),
                "started_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                "operation": "new_turn",
            },
        )
        yield AnswerService.encode_sse_event(start_event)

        previous_messages = self._build_previous_messages(
            tenant_id=auth.tenant_id,
            conversation_id=resolved_conversation_id,
            conversation_kind=conversation_kind,
        )
        pre_stream_status_history: list[dict[str, Any]] = []
        context_status = self._status_event(
            code="context",
            label="Loading Conversation Context",
            state="completed",
            detail=(
                f"Loaded {len(previous_messages)} prior messages"
                if previous_messages
                else "No prior messages in this conversation"
            ),
        )
        pre_stream_status_history = self._append_status_history_entry(
            pre_stream_status_history, context_status.data
        )
        yield AnswerService.encode_sse_event(context_status)
        query_type = QueryClassifier.classify(query_text)
        provider_candidates = self.provider_selection.resolve_chat(
            tenant_id=auth.tenant_id,
            workspace_id=None,
            actor_user_id=auth.user_id,
        ).candidates
        retrieval_running_status = self._status_event(
            code="retrieval",
            label="Retrieving Evidence",
            state="running",
            detail=f"{search_mode} search in progress (top_k {top_k})",
        )
        pre_stream_status_history = self._append_status_history_entry(
            pre_stream_status_history, retrieval_running_status.data
        )
        yield AnswerService.encode_sse_event(retrieval_running_status)
        retrieval_phase_start = time.perf_counter()
        retrieval_result = self._retrieve_with_trace(
            auth=auth,
            normalized_query=normalized_query,
            top_k=top_k,
            document_ids=document_ids,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            source_types=source_types,
            min_extraction_coverage=min_extraction_coverage,
            max_extraction_coverage=max_extraction_coverage,
            search_mode=search_mode,
        )
        retrieved_chunks = retrieval_result["retrieved_chunks"]
        trace = cast(TraceCollector, retrieval_result["trace"])
        retrieval_duration_ms = (time.perf_counter() - retrieval_phase_start) * 1000
        retrieval_completed_status = self._status_event(
            code="retrieval",
            label="Retrieving Evidence",
            state="completed",
            detail=(
                f"Retrieved {len(retrieved_chunks)} chunks from "
                f"{self._distinct_document_count(retrieved_chunks)} documents"
            ),
            duration_ms=retrieval_duration_ms,
        )
        pre_stream_status_history = self._append_status_history_entry(
            pre_stream_status_history, retrieval_completed_status.data
        )
        yield AnswerService.encode_sse_event(retrieval_completed_status)

        confidence = self.answer._calculate_confidence(retrieved_chunks)
        citations = self._build_citation_dicts(retrieved_chunks)
        trace_id = self._resolve_trace_id()
        reasoning_trace_data = trace.to_dict()
        grounding_status = self._status_event(
            code="grounding",
            label="Grounding Answer",
            state="completed",
            detail=(
                f"Prepared {len(citations)} citations from {len(retrieved_chunks)} retrieved chunks"
            ),
        )
        pre_stream_status_history = self._append_status_history_entry(
            pre_stream_status_history, grounding_status.data
        )
        yield AnswerService.encode_sse_event(grounding_status)
        trace_status = self._status_event(
            code="trace",
            label="Analytic Reasoning Trace",
            state="completed",
            detail=(
                f"Searched {reasoning_trace_data['chunks_searched']} chunks, "
                f"evaluated {reasoning_trace_data['chunks_evaluated']}, "
                f"selected {reasoning_trace_data['chunks_selected']}"
                + (
                    f" · reranked with {trace.metadata['reranker_model']}"
                    if trace.metadata.get("reranking_applied")
                    and isinstance(trace.metadata.get("reranker_model"), str)
                    else ""
                )
            ),
        )
        pre_stream_status_history = self._append_status_history_entry(
            pre_stream_status_history, trace_status.data
        )
        yield AnswerService.encode_sse_event(trace_status)

        # Extract provider info for meta event
        selected_candidate = (
            provider_candidates[0]
            if provider_candidates
            else self.answer._env_provider_candidate()
        )

        metadata_event = StreamEvent(
            event="meta",
            data={
                "conversation_id": str(resolved_conversation_id),
                "message_id": None,
                "trace_id": trace_id,
                "confidence": round(confidence, 6),
                "cached": False,
                "query_type": (
                    query_type.value
                    if hasattr(query_type, "value")
                    else str(query_type)
                ),
                "source_count": len(citations),
                "reasoning_trace": reasoning_trace_data,
                "model_name": selected_candidate.model_name
                or selected_candidate.provider_type
                or "DeepSpace AI",
                "provider_type": selected_candidate.provider_type,
            },
        )
        yield AnswerService.encode_sse_event(metadata_event)

        if reasoning_trace_data is not None:
            trace_event = StreamEvent(
                event="trace",
                data={
                    "trace": {
                        **reasoning_trace_data,
                        "trace_id": trace_id,
                    }
                },
            )
            yield AnswerService.encode_sse_event(trace_event)

        full_answer_parts = []
        latest_replace_content = None
        latest_replace_structured: dict[str, Any] | None = None
        streamed_blocks: list[dict[str, Any]] = []
        streamed_thinking_parts: list[str] = []
        streamed_status_history: list[dict[str, Any]] = [*pre_stream_status_history]
        streamed_files: list[dict[str, Any]] = []
        streamed_output: list[dict[str, Any]] = []
        synthesis_running_status = self._status_event(
            code="synthesis",
            label="Synthesizing Answer",
            state="running",
            detail=(
                f"Generating a {query_type.value if hasattr(query_type, 'value') else str(query_type)} answer"
            ),
        )
        streamed_status_history = self._append_status_history_entry(
            streamed_status_history, synthesis_running_status.data
        )
        yield AnswerService.encode_sse_event(synthesis_running_status)
        synthesis_phase_start = time.perf_counter()

        async for event_str in self._stream_answer_events(
            auth=auth,
            query_text=query_text,
            query_type=query_type,
            retrieved_chunks=retrieved_chunks,
            previous_messages=previous_messages,
            citations=citations,
            provider_candidates=provider_candidates,
            thinking_enabled=thinking_enabled,
        ):
            if event_str.startswith("event: delta"):
                # Extract text payload for persistence accumulation.
                try:
                    data_line = next(
                        line
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    )
                    payload = json.loads(data_line[5:].strip())
                    text = str(payload.get("text", ""))
                    if text:
                        full_answer_parts.append(text)
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Failed to parse streamed delta payload.", exc_info=True
                    )
            elif event_str.startswith("event: replace"):
                try:
                    data_line = next(
                        line
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    )
                    payload = json.loads(data_line[5:].strip())
                    replace_content = str(payload.get("content", "")).strip()
                    if replace_content:
                        latest_replace_content = replace_content
                    structured_payload = payload.get("structured")
                    if isinstance(structured_payload, dict):
                        latest_replace_structured = structured_payload
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Failed to parse streamed replace payload.", exc_info=True
                    )
            elif any(
                event_str.startswith(f"event: {name}")
                for name in ("table", "chart", "card", "diagram")
            ):
                try:
                    event_name = next(
                        line[6:].strip()
                        for line in event_str.splitlines()
                        if line.startswith("event:")
                    )
                    data_line = next(
                        line
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    )
                    payload = json.loads(data_line[5:].strip())
                    if isinstance(payload, dict):
                        streamed_blocks = self._merge_unique_structured_blocks(
                            streamed_blocks,
                            {
                                **payload,
                                "type": event_name,
                            },
                        )
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Failed to parse streamed block payload.", exc_info=True
                    )
            elif event_str.startswith("event: thinking"):
                try:
                    data_line = next(
                        line
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    )
                    payload = json.loads(data_line[5:].strip())
                    text = str(payload.get("text", ""))
                    if text:
                        streamed_thinking_parts.append(text)
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Failed to parse streamed thinking payload.", exc_info=True
                    )
            elif event_str.startswith("event: status"):
                payload = self._extract_stream_payload(event_str)
                if payload is not None:
                    streamed_status_history = self._append_status_history_entry(
                        streamed_status_history, payload
                    )
            elif event_str.startswith("event: files"):
                payload = self._extract_stream_payload(event_str)
                items = payload.get("items") if payload is not None else None
                if isinstance(items, list):
                    streamed_files = [item for item in items if isinstance(item, dict)]
            elif event_str.startswith("event: output"):
                payload = self._extract_stream_payload(event_str)
                items = payload.get("items") if payload is not None else None
                if isinstance(items, list):
                    streamed_output = [item for item in items if isinstance(item, dict)]

            yield event_str

        final_text = latest_replace_content or "".join(full_answer_parts).strip()
        streamed_status_history = self._append_status_history_entry(
            streamed_status_history,
            self._status_event(
                code="synthesis",
                label="Synthesizing Answer",
                state="completed",
                detail=f"Generated {len(final_text)} characters of answer content",
                duration_ms=(time.perf_counter() - synthesis_phase_start) * 1000,
            ).data,
        )
        if streamed_blocks:
            streamed_status_history = self._append_status_history_entry(
                streamed_status_history,
                self._status_event(
                    code="outputs",
                    label="Rendering Structured Outputs",
                    state="completed",
                    detail=f"Prepared {len(streamed_blocks)} structured output blocks",
                ).data,
            )
        if (
            not streamed_status_history
            or streamed_status_history[-1].get("code") != "trace"
        ):
            streamed_status_history = self._append_status_history_entry(
                streamed_status_history,
                self._status_event(
                    code="trace",
                    label="Analytic Reasoning Trace",
                    state="completed",
                    detail=(
                        f"Searched {reasoning_trace_data['chunks_searched']} chunks, "
                        f"evaluated {reasoning_trace_data['chunks_evaluated']}, "
                        f"selected {reasoning_trace_data['chunks_selected']}"
                    ),
                ).data,
            )
        followup_items = self._generate_followups(
            query_text=query_text,
            answer_text=final_text,
            tenant_id=auth.tenant_id,
            previous_messages=previous_messages,
            provider_candidates=provider_candidates,
        )
        for event in self._build_followup_events(followup_items):
            if event.event == "status":
                streamed_status_history = self._append_status_history_entry(
                    streamed_status_history, event.data
                )
            yield AnswerService.encode_sse_event(event)

        if not final_text:
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="error",
                    data={
                        "code": "STREAM_EMPTY_PROVIDER_RESPONSE",
                        "message": "The chat model did not return an answer.",
                    },
                )
            )
            return

        terminal_status = self._status_event(
            code="complete",
            label="Completed",
            state="completed",
            detail="Stream finished successfully",
        )
        streamed_status_history = self._append_status_history_entry(
            streamed_status_history, terminal_status.data
        )

        try:
            persisted_structured = (
                latest_replace_structured
                if isinstance(latest_replace_structured, dict)
                else None
            )
            self.chat.add_message(
                tenant_id=auth.tenant_id,
                conversation_id=resolved_conversation_id,
                kind=conversation_kind,
                role="assistant",
                content=final_text,
                metadata_json={
                    "trace_id": trace_id,
                    "confidence": round(confidence, 6),
                    "citations": citations,
                    "search_mode": search_mode,
                    "reasoning_trace": reasoning_trace_data,
                    "thinking": (
                        {
                            "content": "".join(streamed_thinking_parts).strip(),
                            "enabled": thinking_enabled,
                        }
                        if streamed_thinking_parts
                        else None
                    ),
                    "structured_answer": persisted_structured,
                    "blocks": streamed_blocks,
                    "status_history": streamed_status_history,
                    "files": streamed_files,
                    "output": (
                        streamed_output
                        if streamed_output
                        else self._build_output_summary_from_blocks(streamed_blocks)
                    ),
                    "follow_up_suggestions": followup_items,
                },
            )
            self._maybe_commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist streamed assistant response.")
        yield AnswerService.encode_sse_event(
            StreamEvent(event="done", data={"completed": True})
        )
        yield AnswerService.encode_sse_event(terminal_status)

    async def regenerate_message_stream(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        conversation_kind: str = "query",
        top_k: int,
        search_mode: str,
        document_id: uuid.UUID | None = None,
        thinking_enabled: bool = False,
    ) -> AsyncIterator[str]:
        user_message, assistant_message = self.chat.get_latest_turn_pair(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=conversation_kind,
        )
        if user_message is None or assistant_message is None:
            raise ApiError(
                code="TURN_NOT_FOUND",
                message="Latest conversation turn was not found.",
                status_code=404,
            )
        if assistant_message.id != assistant_message_id:
            raise ApiError(
                code="MESSAGE_REGENERATE_NOT_ALLOWED",
                message="Only the latest assistant message can be regenerated.",
                status_code=409,
            )
        async for chunk in self._stream_existing_turn_response(
            auth=auth,
            conversation_id=conversation_id,
            conversation_kind=conversation_kind,
            user_message=user_message,
            assistant_message=assistant_message,
            query_text=self._message_display_content(user_message),
            top_k=top_k,
            search_mode=search_mode,
            document_id=document_id,
            operation="regenerate",
            thinking_enabled=thinking_enabled,
        ):
            yield chunk

    async def edit_and_regenerate_message_stream(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        user_message_id: uuid.UUID,
        conversation_kind: str = "query",
        updated_content: str,
        top_k: int,
        search_mode: str,
        document_id: uuid.UUID | None = None,
        thinking_enabled: bool = False,
    ) -> AsyncIterator[str]:
        user_message, assistant_message = self.chat.get_latest_turn_pair(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=conversation_kind,
        )
        if user_message is None or assistant_message is None:
            raise ApiError(
                code="TURN_NOT_FOUND",
                message="Latest conversation turn was not found.",
                status_code=404,
            )
        if user_message.id != user_message_id:
            raise ApiError(
                code="MESSAGE_EDIT_NOT_ALLOWED",
                message="Only the latest user message can be edited.",
                status_code=409,
            )

        self.chat.create_message_version(
            tenant_id=auth.tenant_id,
            message_id=user_message.id,
            content=updated_content,
            metadata_json=self._message_active_metadata(user_message),
            source_type="user_edit",
            activate=True,
        )
        self._maybe_commit()
        refreshed_user = self.chat.get_message(
            tenant_id=auth.tenant_id,
            message_id=user_message.id,
            user_id=auth.user_id,
        )
        if refreshed_user is None:
            raise ApiError(
                code="MESSAGE_NOT_FOUND",
                message="Edited user message could not be reloaded.",
                status_code=404,
            )
        async for chunk in self._stream_existing_turn_response(
            auth=auth,
            conversation_id=conversation_id,
            conversation_kind=conversation_kind,
            user_message=refreshed_user,
            assistant_message=assistant_message,
            query_text=updated_content,
            top_k=top_k,
            search_mode=search_mode,
            document_id=document_id,
            operation="edit_regenerate",
            thinking_enabled=thinking_enabled,
        ):
            yield chunk

    async def _stream_existing_turn_response(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        conversation_kind: str,
        user_message: Any,
        assistant_message: Any,
        query_text: str,
        top_k: int,
        search_mode: str,
        document_id: uuid.UUID | None,
        operation: str,
        thinking_enabled: bool,
    ) -> AsyncIterator[str]:
        self._enforce_quota(auth)
        self._validate_top_k(top_k)
        normalized_query = self.normalize_query(query_text)

        start_event = StreamEvent(
            event="start",
            data={
                "message_id": str(assistant_message.id),
                "conversation_id": str(conversation_id),
                "started_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                "operation": operation,
            },
        )
        yield AnswerService.encode_sse_event(start_event)

        previous_messages = self._build_previous_messages_until(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            conversation_kind=conversation_kind,
            through_message_id=user_message.id,
        )
        query_type = QueryClassifier.classify(query_text)
        response_directive = self._build_regeneration_directive(
            operation=operation,
            assistant_message=assistant_message,
        )
        temperature_override = (
            max(float(self.settings.llm_temperature), 0.2)
            if operation in {"regenerate", "edit_regenerate"}
            else None
        )
        provider_candidates = self.provider_selection.resolve_chat(
            tenant_id=auth.tenant_id,
            workspace_id=None,
            actor_user_id=auth.user_id,
        ).candidates
        status_history: list[dict[str, Any]] = []
        context_status = self._status_event(
            code="context",
            label="Loading Conversation Context",
            state="completed",
            detail=(
                f"Loaded {len(previous_messages)} prior messages"
                if previous_messages
                else "No prior messages in this conversation"
            ),
        )
        status_history = self._append_status_history_entry(
            status_history, context_status.data
        )
        yield AnswerService.encode_sse_event(context_status)
        retrieval_running_status = self._status_event(
            code="retrieval",
            label="Retrieving Evidence",
            state="running",
            detail=f"{search_mode} search in progress (top_k {top_k})",
        )
        status_history = self._append_status_history_entry(
            status_history, retrieval_running_status.data
        )
        yield AnswerService.encode_sse_event(retrieval_running_status)
        retrieval_phase_start = time.perf_counter()
        retrieval_result = self._retrieve_with_trace(
            auth=auth,
            normalized_query=normalized_query,
            top_k=top_k,
            document_ids=[document_id] if document_id is not None else None,
            created_at_from=None,
            created_at_to=None,
            source_types=None,
            min_extraction_coverage=None,
            max_extraction_coverage=None,
            search_mode=search_mode,
        )
        retrieved_chunks = retrieval_result["retrieved_chunks"]
        trace = cast(TraceCollector, retrieval_result["trace"])
        retrieval_duration_ms = (time.perf_counter() - retrieval_phase_start) * 1000
        retrieval_completed_status = self._status_event(
            code="retrieval",
            label="Retrieving Evidence",
            state="completed",
            detail=(
                f"Retrieved {len(retrieved_chunks)} chunks from "
                f"{self._distinct_document_count(retrieved_chunks)} documents"
            ),
            duration_ms=retrieval_duration_ms,
        )
        status_history = self._append_status_history_entry(
            status_history, retrieval_completed_status.data
        )
        yield AnswerService.encode_sse_event(retrieval_completed_status)
        confidence = self.answer._calculate_confidence(retrieved_chunks)
        citations = self._build_citation_dicts(retrieved_chunks)
        trace_id = self._resolve_trace_id()
        reasoning_trace_data = trace.to_dict()
        grounding_status = self._status_event(
            code="grounding",
            label="Grounding Answer",
            state="completed",
            detail=(
                f"Prepared {len(citations)} citations from {len(retrieved_chunks)} retrieved chunks"
            ),
        )
        status_history = self._append_status_history_entry(
            status_history, grounding_status.data
        )
        yield AnswerService.encode_sse_event(grounding_status)
        trace_status = self._status_event(
            code="trace",
            label="Analytic Reasoning Trace",
            state="completed",
            detail=(
                f"Searched {reasoning_trace_data['chunks_searched']} chunks, "
                f"evaluated {reasoning_trace_data['chunks_evaluated']}, "
                f"selected {reasoning_trace_data['chunks_selected']}"
            ),
        )
        status_history = self._append_status_history_entry(
            status_history, trace_status.data
        )
        yield AnswerService.encode_sse_event(trace_status)

        yield AnswerService.encode_sse_event(
            StreamEvent(
                event="meta",
                data={
                    "conversation_id": str(conversation_id),
                    "message_id": str(assistant_message.id),
                    "trace_id": trace_id,
                    "confidence": round(confidence, 6),
                    "cached": False,
                    "query_type": (
                        query_type.value
                        if hasattr(query_type, "value")
                        else str(query_type)
                    ),
                    "source_count": len(citations),
                    "reasoning_trace": reasoning_trace_data,
                },
            )
        )
        if reasoning_trace_data is not None:
            yield AnswerService.encode_sse_event(
                StreamEvent(
                    event="trace",
                    data={"trace": {**reasoning_trace_data, "trace_id": trace_id}},
                )
            )

        full_answer_parts: list[str] = []
        latest_replace_content: str | None = None
        thinking_parts: list[str] = []
        files: list[dict[str, Any]] = []
        output_items: list[dict[str, Any]] = []
        synthesis_running_status = self._status_event(
            code="synthesis",
            label="Synthesizing Answer",
            state="running",
            detail="Generating a regenerated answer",
        )
        status_history = self._append_status_history_entry(
            status_history, synthesis_running_status.data
        )
        yield AnswerService.encode_sse_event(synthesis_running_status)
        synthesis_phase_start = time.perf_counter()
        async for event_str in self._stream_answer_events(
            auth=auth,
            query_text=query_text,
            query_type=query_type,
            retrieved_chunks=retrieved_chunks,
            previous_messages=previous_messages,
            citations=citations,
            provider_candidates=provider_candidates,
            response_directive=response_directive,
            temperature_override=temperature_override,
            thinking_enabled=thinking_enabled,
        ):
            if event_str.startswith("event: delta"):
                try:
                    data_line = next(
                        line
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    )
                    payload = json.loads(data_line[5:].strip())
                    text = str(payload.get("text", ""))
                    if text:
                        full_answer_parts.append(text)
                except Exception:
                    logger.debug(
                        "Failed to parse streamed delta payload.", exc_info=True
                    )
            elif event_str.startswith("event: replace"):
                try:
                    data_line = next(
                        line
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    )
                    payload = json.loads(data_line[5:].strip())
                    replace_content = str(payload.get("content", "")).strip()
                    if replace_content:
                        latest_replace_content = replace_content
                except Exception:
                    logger.debug(
                        "Failed to parse streamed replace payload.", exc_info=True
                    )
            elif event_str.startswith("event: thinking"):
                try:
                    data_line = next(
                        line
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    )
                    payload = json.loads(data_line[5:].strip())
                    text = str(payload.get("text", ""))
                    if text:
                        thinking_parts.append(text)
                except Exception:
                    logger.debug(
                        "Failed to parse streamed thinking payload.", exc_info=True
                    )
            elif event_str.startswith("event: status"):
                payload = self._extract_stream_payload(event_str)
                if payload is not None:
                    status_history = self._append_status_history_entry(
                        status_history, payload
                    )
            elif event_str.startswith("event: files"):
                payload = self._extract_stream_payload(event_str)
                items = payload.get("items") if payload is not None else None
                if isinstance(items, list):
                    files = [item for item in items if isinstance(item, dict)]
            elif event_str.startswith("event: output"):
                payload = self._extract_stream_payload(event_str)
                items = payload.get("items") if payload is not None else None
                if isinstance(items, list):
                    output_items = [item for item in items if isinstance(item, dict)]
            yield event_str

        final_text = latest_replace_content or "".join(full_answer_parts).strip()
        status_history = self._append_status_history_entry(
            status_history,
            self._status_event(
                code="synthesis",
                label="Synthesizing Answer",
                state="completed",
                detail=f"Generated {len(final_text)} characters of answer content",
                duration_ms=(time.perf_counter() - synthesis_phase_start) * 1000,
            ).data,
        )
        followup_items = self._generate_followups(
            query_text=query_text,
            answer_text=final_text,
            tenant_id=auth.tenant_id,
            previous_messages=previous_messages,
            provider_candidates=provider_candidates,
        )
        for event in self._build_followup_events(followup_items):
            if event.event == "status":
                status_history = self._append_status_history_entry(
                    status_history, event.data
                )
            yield AnswerService.encode_sse_event(event)

        if final_text:
            try:
                self.chat.create_message_version(
                    tenant_id=auth.tenant_id,
                    message_id=assistant_message.id,
                    content=final_text,
                    metadata_json={
                        "trace_id": trace_id,
                        "confidence": round(confidence, 6),
                        "citations": citations,
                        "search_mode": search_mode,
                        "reasoning_trace": reasoning_trace_data,
                        "thinking": (
                            {
                                "content": "".join(thinking_parts).strip(),
                                "enabled": thinking_enabled,
                            }
                            if thinking_parts
                            else None
                        ),
                        "status_history": status_history,
                        "files": files,
                        "output": output_items,
                        "follow_up_suggestions": followup_items,
                    },
                    source_type="regenerate",
                    activate=True,
                )
                self._maybe_commit()
            except Exception:
                logger.exception("Failed to persist regenerated assistant response.")

    def _message_display_content(self, message: Any) -> str:
        active_version = getattr(message, "active_version", None)
        if active_version is not None and isinstance(active_version.content, str):
            return active_version.content
        return str(getattr(message, "content", ""))

    def _message_active_metadata(self, message: Any) -> dict[str, Any]:
        active_version = getattr(message, "active_version", None)
        if active_version is not None and isinstance(
            active_version.metadata_json, dict
        ):
            return dict(active_version.metadata_json)
        return dict(getattr(message, "metadata_json", {}) or {})

    def _build_previous_messages_until(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        conversation_kind: str = "query",
        through_message_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        history = self.chat.get_messages(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            kind=conversation_kind,
            limit=100,
        )
        previous_messages: list[dict[str, str]] = []
        for message in history:
            previous_messages.append(
                {
                    "role": message.role,
                    "content": self._message_content_to_text(
                        self._message_display_content(message)
                    ),
                }
            )
            if message.id == through_message_id:
                break
        return previous_messages[-10:]

    async def _stream_answer_events(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        query_type: Any,
        retrieved_chunks: list[RetrievedChunk],
        previous_messages: list[dict[str, str]],
        citations: list[dict[str, Any]],
        provider_candidates: list[ProviderSelectionCandidate],
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> AsyncIterator[str]:
        for citation in citations:
            yield AnswerService.encode_sse_event(
                StreamEvent(event="citation", data={"item": citation})
            )

        async for event in self.answer.stream_synthesize_events_async(
            retrieved_chunks=retrieved_chunks,
            query_text=query_text,
            tenant_id=auth.tenant_id,
            previous_messages=previous_messages,
            query_type=query_type,
            provider_candidates=provider_candidates,
            response_directive=response_directive,
            temperature_override=temperature_override,
            thinking_enabled=thinking_enabled,
        ):
            yield AnswerService.encode_sse_event(event)

    def _build_regeneration_directive(
        self,
        *,
        operation: str,
        assistant_message: Any,
    ) -> str | None:
        if operation not in {"regenerate", "edit_regenerate"}:
            return None
        previous_answer = self._message_content_to_text(
            self._message_display_content(assistant_message)
        ).strip()
        directive = (
            "This is a regenerated answer for the same conversation turn. "
            "Stay grounded in the retrieved evidence, but produce a meaningfully different response shape, wording, and emphasis. "
            "Do not repeat the previous answer verbatim."
        )
        if previous_answer:
            snippet = previous_answer[:1500]
            directive += f"\nAvoid repeating this earlier answer verbatim:\n{snippet}"
        return directive

    # ------------------------------------------------------------------
    # Public sync API
    # ------------------------------------------------------------------

    def execute(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        top_k: int,
        filters: dict[str, Any],
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
        source_types: list[str] | None,
        min_extraction_coverage: float | None,
        max_extraction_coverage: float | None,
        conversation_id: uuid.UUID | None = None,
        conversation_kind: str = "query",
        search_mode: str = "hybrid",
        thinking_enabled: bool = False,
    ) -> QueryExecutionResult:
        self._enforce_quota(auth)
        self._validate_top_k(top_k)

        normalized_query = self.normalize_query(query_text)
        normalized_filters = self.normalize_filters(filters)
        embedding_selection = self.provider_selection.resolve_embeddings(
            tenant_id=auth.tenant_id,
            workspace_id=None,
            actor_user_id=auth.user_id,
        )
        embedding_candidate = (
            embedding_selection.candidates[0]
            if embedding_selection.candidates
            else None
        )

        cache_key = self.build_cache_key(
            tenant_id=auth.tenant_id,
            normalized_query=normalized_query,
            normalized_filters=normalized_filters,
            top_k=top_k,
            embedding_provider=(
                embedding_candidate.provider_type
                if embedding_candidate is not None
                else self.settings.embedding_provider
            ),
            embedding_model=(
                embedding_candidate.model_name
                if embedding_candidate is not None
                else self.settings.embedding_model
            ),
            search_mode=search_mode,
        )

        conversation = self._resolve_or_create_conversation(
            auth=auth,
            query_text=query_text,
            conversation_id=conversation_id,
            conversation_kind=conversation_kind,
        )
        resolved_conversation_id = conversation.id

        previous_messages = self._build_previous_messages(
            tenant_id=auth.tenant_id,
            conversation_id=resolved_conversation_id,
            conversation_kind=conversation_kind,
        )
        self.chat.add_message(
            tenant_id=auth.tenant_id,
            conversation_id=resolved_conversation_id,
            kind=conversation_kind,
            role="user",
            content=query_text,
        )

        outline_grounding = self._maybe_build_document_outline_grounding(
            auth=auth,
            query_text=query_text,
            document_ids=document_ids,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )
        if outline_grounding is not None:
            provider_candidates = self.provider_selection.resolve_chat(
                tenant_id=auth.tenant_id,
                workspace_id=None,
                actor_user_id=auth.user_id,
            ).candidates
            if not provider_candidates:
                raise ApiError(
                    code="LLM_UNAVAILABLE",
                    message="A chat model is required for document outline answers.",
                    status_code=503,
                )
            outline_chunks = self._build_outline_grounding_chunks(
                query_text=query_text,
                grounding_text=outline_grounding,
            )
            answer_result = self.answer.synthesize(
                retrieved_chunks=outline_chunks,
                query_text=self._build_outline_llm_query(query_text),
                tenant_id=auth.tenant_id,
                previous_messages=previous_messages,
                query_type=QueryClassifier.classify(query_text),
                provider_candidates=provider_candidates,
            )
            return self._persist_inventory_query_result(
                auth=auth,
                query_text=query_text,
                normalized_query=normalized_query,
                normalized_filters=normalized_filters,
                top_k=top_k,
                answer=answer_result.answer,
                conversation_id=resolved_conversation_id,
                conversation_kind=conversation_kind,
                search_mode=search_mode,
                confidence=answer_result.confidence,
                followup_items=self._generate_followups(
                    query_text=query_text,
                    answer_text=self._answer_to_followup_text(answer_result.answer),
                    tenant_id=auth.tenant_id,
                    previous_messages=previous_messages,
                    provider_candidates=provider_candidates,
                ),
                provider_metadata=self._provider_metadata(answer_result)
                or {
                    "type": "llm_grounded",
                    "model": "document_outline",
                },
            )

        inventory_answer = self._maybe_build_document_inventory_answer(
            auth=auth,
            query_text=query_text,
            document_ids=document_ids,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )
        if inventory_answer is not None:
            provider_candidates = self.provider_selection.resolve_chat(
                tenant_id=auth.tenant_id,
                workspace_id=None,
                actor_user_id=auth.user_id,
            ).candidates
            if not provider_candidates:
                return self._persist_inventory_query_result(
                    auth=auth,
                    query_text=query_text,
                    normalized_query=normalized_query,
                    normalized_filters=normalized_filters,
                    top_k=top_k,
                    answer=inventory_answer,
                    conversation_id=resolved_conversation_id,
                    conversation_kind=conversation_kind,
                    search_mode=search_mode,
                    confidence=1.0,
                    followup_items=self._generate_followups(
                        query_text=query_text,
                        answer_text=self._answer_to_followup_text(inventory_answer),
                        tenant_id=auth.tenant_id,
                        previous_messages=previous_messages,
                        provider_candidates=[],
                    ),
                    provider_metadata={
                        "type": "system",
                        "model": "document_inventory_fallback",
                    },
                )
            inventory_chunks = self._build_inventory_grounding_chunks(
                query_text=query_text,
                grounding_text=inventory_answer,
            )
            answer_result = self.answer.synthesize(
                retrieved_chunks=inventory_chunks,
                query_text=self._build_inventory_llm_query(query_text),
                tenant_id=auth.tenant_id,
                previous_messages=previous_messages,
                query_type=QueryClassifier.classify(query_text),
                provider_candidates=provider_candidates,
            )
            return self._persist_inventory_query_result(
                auth=auth,
                query_text=query_text,
                normalized_query=normalized_query,
                normalized_filters=normalized_filters,
                top_k=top_k,
                answer=answer_result.answer,
                conversation_id=resolved_conversation_id,
                conversation_kind=conversation_kind,
                search_mode=search_mode,
                confidence=answer_result.confidence,
                followup_items=self._generate_followups(
                    query_text=query_text,
                    answer_text=self._answer_to_followup_text(answer_result.answer),
                    tenant_id=auth.tenant_id,
                    previous_messages=previous_messages,
                    provider_candidates=provider_candidates,
                ),
                provider_metadata=self._provider_metadata(answer_result)
                or {
                    "type": "llm_grounded",
                    "model": "document_inventory",
                },
            )

        cached_payload = self.cache.get(cache_key)
        cached = cached_payload is not None
        QUERY_CACHE_EVENTS_TOTAL.labels(event="hit" if cached else "miss").inc()

        answer_result = None  # type: ignore[assignment]
        trace = None
        provider_candidates = self.provider_selection.resolve_chat(
            tenant_id=auth.tenant_id,
            workspace_id=None,
            actor_user_id=auth.user_id,
        ).candidates

        if cached_payload is not None:
            answer = cast(
                str | StructuredAnswerResponse,
                cached_payload.get("answer", self.settings.query_no_result_answer_text),
            )
            confidence = float(cached_payload.get("confidence", 0.0))
            citations = cast(
                list[dict[str, Any]], list(cached_payload.get("citations", []))
            )
            retrieval_duration_ms = None
            answer_duration_ms = None
            retrieved_chunks = []
        else:
            retrieval_phase_start = time.perf_counter()
            retrieval_result = self._retrieve_with_trace(
                auth=auth,
                normalized_query=normalized_query,
                top_k=top_k,
                document_ids=document_ids,
                created_at_from=created_at_from,
                created_at_to=created_at_to,
                source_types=source_types,
                min_extraction_coverage=min_extraction_coverage,
                max_extraction_coverage=max_extraction_coverage,
                search_mode=search_mode,
            )
            retrieved_chunks = retrieval_result["retrieved_chunks"]
            trace = cast(TraceCollector, retrieval_result["trace"])
            retrieval_duration_ms = (time.perf_counter() - retrieval_phase_start) * 1000

            answer_start = time.perf_counter()
            answer_result = self.answer.synthesize(
                retrieved_chunks=retrieved_chunks,
                query_text=query_text,
                tenant_id=auth.tenant_id,
                previous_messages=previous_messages,
                query_type=QueryClassifier.classify(query_text),
                provider_candidates=provider_candidates,
            )
            QUERY_PIPELINE_DURATION_SECONDS.labels(segment="answer").observe(
                time.perf_counter() - answer_start
            )
            answer_duration_ms = (time.perf_counter() - answer_start) * 1000

            answer = answer_result.answer
            confidence = answer_result.confidence
            citations = [
                {
                    "document_id": citation.document_id,
                    "chunk_id": citation.chunk_id,
                    "filename": citation.filename,
                    "snippet": citation.snippet,
                    "similarity_score": citation.similarity_score,
                    "source_type": citation.source_type,
                    "section_header": citation.section_header,
                    "page_number": citation.page_number,
                }
                for citation in answer_result.citations
            ]

            self.cache.set(
                key=cache_key,
                value={
                    "answer": self._serialize_answer_for_cache(answer),
                    "confidence": confidence,
                    "citations": citations,
                },
                ttl_seconds=self.settings.query_cache_ttl_seconds,
            )

        trace_id = self._resolve_trace_id()
        persist_start = time.perf_counter()

        query_row = self.queries.create_query(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            query_text=query_text,
            normalized_query=normalized_query,
            filters=normalized_filters,
            top_k=top_k,
            cache_hit=cached,
            answer=self._answer_to_storage_text(answer),
            confidence=confidence,
            trace_id=trace_id,
        )

        citation_rows: list[QueryCitation] = []
        for index, citation in enumerate(citations, start=1):
            citation_rows.append(
                QueryCitation(
                    id=generate_uuid7_with_fallback(),
                    tenant_id=auth.tenant_id,
                    query_id=query_row.id,
                    document_id=uuid.UUID(str(citation["document_id"])),
                    chunk_id=uuid.UUID(str(citation["chunk_id"])),
                    snippet=str(citation["snippet"]),
                    similarity_score=float(citation["similarity_score"]),
                    rank=index,
                )
            )
        if citation_rows:
            self.queries.create_citations(
                tenant_id=auth.tenant_id, citations=citation_rows
            )

        usage = answer_result.usage if answer_result is not None else None
        if not cached and usage:
            self.billing.record_usage(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                query_id=query_row.id,
                operation="query_execution",
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                model_name=(
                    answer_result.model_name
                    if answer_result is not None
                    and answer_result.model_name is not None
                    else self.settings.llm_model
                ),
            )

        reasoning_trace_data: dict[str, Any] | None = None
        if not cached and trace is not None:
            reasoning_trace_data = trace.to_dict()
            reasoning_trace_data["trace_id"] = trace_id

        followup_items = self._generate_followups(
            query_text=query_text,
            answer_text=self._answer_to_followup_text(answer),
            tenant_id=auth.tenant_id,
            previous_messages=previous_messages,
            provider_candidates=provider_candidates,
        )
        persisted_blocks = (
            self._build_persisted_block_payloads(answer)
            if isinstance(answer, StructuredAnswerResponse)
            else []
        )
        status_history = self._build_query_status_history(
            previous_message_count=len(previous_messages),
            cached=cached,
            search_mode=search_mode,
            top_k=top_k,
            retrieved_chunks=retrieved_chunks,
            citations=citations,
            trace=trace,
            answer_text=self._answer_to_storage_text(answer),
            followup_items=followup_items,
            persisted_blocks=persisted_blocks,
            retrieval_duration_ms=retrieval_duration_ms,
            answer_duration_ms=answer_duration_ms,
        )

        self.chat.add_message(
            tenant_id=auth.tenant_id,
            conversation_id=resolved_conversation_id,
            kind=conversation_kind,
            role="assistant",
            content=self._answer_to_storage_text(answer),
            metadata_json={
                "trace_id": trace_id,
                "confidence": confidence,
                "citations": citations,
                "search_mode": search_mode,
                "provider": self._provider_metadata(answer_result),
                "reasoning_trace": reasoning_trace_data,
                "structured_answer": (
                    answer.model_dump(mode="json")
                    if isinstance(answer, StructuredAnswerResponse)
                    else None
                ),
                "blocks": persisted_blocks,
                "status_history": status_history,
                "files": [],
                "output": self._build_output_summary_from_blocks(persisted_blocks),
                "follow_up_suggestions": followup_items,
            },
        )

        self._maybe_commit()
        QUERY_PIPELINE_DURATION_SECONDS.labels(segment="persist").observe(
            time.perf_counter() - persist_start
        )

        reasoning_trace_model: ReasoningTraceModel | None = None
        if reasoning_trace_data is not None:
            reasoning_trace_model = ReasoningTraceModel(**reasoning_trace_data)

        return QueryExecutionResult(
            answer=answer,
            confidence=confidence,
            citations=citations,
            trace_id=trace_id,
            cached=cached,
            conversation_id=resolved_conversation_id,
            reasoning_trace=reasoning_trace_model,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_build_document_inventory_answer(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
    ) -> str | None:
        normalized = query_text.strip().lower()
        if not self._should_route_to_document_inventory(
            query_text=normalized,
            document_ids=document_ids,
        ):
            return None

        batch_answer = self._maybe_build_batched_inventory_answer(
            auth=auth,
            query_text=query_text,
            document_ids=document_ids,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )
        if batch_answer is not None:
            return batch_answer

        accessible_ids = self.documents.get_accessible_document_ids_global(
            user_id=auth.user_id,
            include_quarantined=True,
        )
        if document_ids is not None:
            scoped_ids = [doc_id for doc_id in document_ids if doc_id in accessible_ids]
        else:
            scoped_ids = list(accessible_ids)

        documents = self.documents.list_by_ids_global(document_ids=scoped_ids)
        if created_at_from is not None:
            documents = [doc for doc in documents if doc.created_at >= created_at_from]
        if created_at_to is not None:
            documents = [doc for doc in documents if doc.created_at <= created_at_to]

        workspace_records = self._build_workspace_records(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            documents=documents,
        )
        workspace_records = self._apply_metadata_question_filters(
            records=workspace_records,
            query_text=normalized,
        )

        if not workspace_records:
            return self._format_empty_inventory_result(
                query_text=normalized,
                all_records=self._build_workspace_records(
                    tenant_id=auth.tenant_id,
                    user_id=auth.user_id,
                    documents=documents,
                ),
            )

        content_filtered_answer = self._maybe_answer_metadata_content_query(
            auth=auth,
            query_text=normalized,
            records=workspace_records,
        )
        if content_filtered_answer is not None:
            return content_filtered_answer

        if _COMPARISON_QUERY_RE.search(normalized):
            comparison_answer = self._maybe_build_document_comparison_answer(
                query_text=normalized,
                records=workspace_records,
                tenant_id=auth.tenant_id,
            )
            if comparison_answer is not None:
                return comparison_answer

        if _COLLECTION_ANALYSIS_QUERY_RE.search(normalized):
            collection_analysis_answer = self._maybe_build_collection_analysis_answer(
                query_text=normalized,
                records=workspace_records,
            )
            if collection_analysis_answer is not None:
                return collection_analysis_answer

        embedding_model_filter = self._extract_embedding_model_filter(normalized)
        if embedding_model_filter and (
            normalized.startswith("which ")
            or normalized.startswith("show ")
            or normalized.startswith("list ")
        ):
            if (
                "indexed" in normalized
                or "failed" in normalized
                or "queued" in normalized
            ):
                return self._format_status_answer(records=workspace_records)
            return self._format_inventory_list_answer(records=workspace_records)

        if "embedding model" in normalized or "embedder" in normalized:
            return self._format_embedding_model_answer(records=workspace_records)

        if "total storage" in normalized or "storage used" in normalized:
            total_size = sum(record.document.size_bytes for record in workspace_records)
            return self._format_storage_answer(
                records=workspace_records, total_size=total_size
            )

        if "size" in normalized or "sizes" in normalized:
            return self._format_storage_answer(
                records=workspace_records,
                total_size=sum(
                    record.document.size_bytes for record in workspace_records
                ),
                include_per_document=True,
            )

        if (
            "latest" in normalized
            or "last uploaded" in normalized
            or "most recent" in normalized
        ):
            latest = max(
                workspace_records, key=lambda item: item.document.created_at
            ).document
            return (
                f"The latest uploaded document is {latest.filename}.\n"
                f"Status: {latest.status}\n"
                f"Uploaded: {latest.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"Size: {self._format_bytes(latest.size_bytes)}"
            )

        if _FAILURE_DIAG_QUERY_RE.search(normalized):
            return self._format_failure_diagnosis_answer(records=workspace_records)

        if _OCR_VISION_QUERY_RE.search(normalized):
            return self._format_ocr_vision_answer(
                records=workspace_records, query_text=normalized
            )

        if _QUALITY_QUERY_RE.search(normalized):
            return self._format_quality_answer(records=workspace_records)

        if _COLLECTION_QUERY_RE.search(normalized):
            return self._format_collection_answer(
                records=workspace_records, query_text=normalized
            )

        if "indexed" in normalized or "failed" in normalized or "queued" in normalized:
            return self._format_status_answer(records=workspace_records)

        indexed_count = sum(
            1 for record in workspace_records if record.document.status == "indexed"
        )
        return self._format_inventory_list_answer(
            records=workspace_records,
            indexed_count=indexed_count,
        )

    def _maybe_build_document_outline_grounding(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
    ) -> str | None:
        normalized = query_text.strip().lower()
        if not self._is_document_outline_query(normalized):
            return None

        accessible_ids = self.documents.get_accessible_document_ids_global(
            user_id=auth.user_id,
            include_quarantined=True,
        )
        if document_ids is not None:
            scoped_ids = [doc_id for doc_id in document_ids if doc_id in accessible_ids]
        else:
            scoped_ids = list(accessible_ids)

        documents = self.documents.list_by_ids_global(document_ids=scoped_ids)
        if created_at_from is not None:
            documents = [doc for doc in documents if doc.created_at >= created_at_from]
        if created_at_to is not None:
            documents = [doc for doc in documents if doc.created_at <= created_at_to]
        if not documents:
            return None

        lines = [
            "Document content outline snapshot. Treat this as extracted structure from the uploaded files.",
            "- Answer naturally from this outline snapshot only.",
            "- If the user asks for headings or subheadings, return the extracted titles and section hierarchy.",
            "",
        ]
        found_any = False
        for document in sorted(
            documents, key=lambda item: item.created_at, reverse=True
        ):
            chunks = self.chunks.get_by_document_id(
                tenant_id=auth.tenant_id,
                document_id=document.id,
                limit=80,
                offset=0,
            )
            title, headings = self._extract_document_outline_from_chunks(
                [chunk.content for chunk in chunks]
            )
            if title is None and not headings:
                continue
            found_any = True
            lines.append(f"Document: {document.filename}")
            if title:
                lines.append(f"Title: {title}")
            if headings:
                lines.append("Headings:")
                for heading in headings[:20]:
                    lines.append(f"- {heading}")
            lines.append("")

        if not found_any:
            return None
        return "\n".join(lines).strip()

    def _maybe_build_batched_inventory_answer(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
    ) -> str | None:
        raw_lines = [
            line.strip()
            for line in _BATCH_QUESTION_SPLIT_RE.split(query_text)
            if line.strip()
        ]
        if len(raw_lines) < 2:
            return None

        inventory_lines = [
            line
            for line in raw_lines
            if self._should_route_to_document_inventory(
                query_text=line.lower(),
                document_ids=document_ids,
            )
        ]
        if len(inventory_lines) < 2:
            return None

        responses: list[str] = []
        for line in inventory_lines:
            answer = self._build_single_inventory_answer(
                auth=auth,
                query_text=line,
                document_ids=document_ids,
                created_at_from=created_at_from,
                created_at_to=created_at_to,
            )
            if answer is None:
                continue
            responses.append(f"Q: {line}\n{answer}")

        if not responses:
            return None
        return "\n\n".join(responses)

    def _build_single_inventory_answer(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
    ) -> str | None:
        normalized = query_text.strip().lower()
        if not self._should_route_to_document_inventory(
            query_text=normalized,
            document_ids=document_ids,
        ):
            return None

        accessible_ids = self.documents.get_accessible_document_ids_global(
            user_id=auth.user_id,
            include_quarantined=True,
        )
        if document_ids is not None:
            scoped_ids = [doc_id for doc_id in document_ids if doc_id in accessible_ids]
        else:
            scoped_ids = list(accessible_ids)

        documents = self.documents.list_by_ids_global(document_ids=scoped_ids)
        if created_at_from is not None:
            documents = [doc for doc in documents if doc.created_at >= created_at_from]
        if created_at_to is not None:
            documents = [doc for doc in documents if doc.created_at <= created_at_to]

        workspace_records = self._build_workspace_records(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            documents=documents,
        )
        workspace_records = self._apply_metadata_question_filters(
            records=workspace_records,
            query_text=normalized,
        )

        if not workspace_records:
            return self._format_empty_inventory_result(
                query_text=normalized,
                all_records=self._build_workspace_records(
                    tenant_id=auth.tenant_id,
                    user_id=auth.user_id,
                    documents=documents,
                ),
            )

        content_filtered_answer = self._maybe_answer_metadata_content_query(
            auth=auth,
            query_text=normalized,
            records=workspace_records,
        )
        if content_filtered_answer is not None:
            return content_filtered_answer

        if _COMPARISON_QUERY_RE.search(normalized):
            comparison_answer = self._maybe_build_document_comparison_answer(
                query_text=normalized,
                records=workspace_records,
                tenant_id=auth.tenant_id,
            )
            if comparison_answer is not None:
                return comparison_answer

        if _COLLECTION_ANALYSIS_QUERY_RE.search(normalized):
            collection_analysis_answer = self._maybe_build_collection_analysis_answer(
                query_text=normalized,
                records=workspace_records,
            )
            if collection_analysis_answer is not None:
                return collection_analysis_answer

        embedding_model_filter = self._extract_embedding_model_filter(normalized)
        if embedding_model_filter and (
            normalized.startswith("which ")
            or normalized.startswith("show ")
            or normalized.startswith("list ")
        ):
            if (
                "indexed" in normalized
                or "failed" in normalized
                or "queued" in normalized
            ):
                return self._format_status_answer(records=workspace_records)
            return self._format_inventory_list_answer(records=workspace_records)

        if "embedding model" in normalized or "embedder" in normalized:
            return self._format_embedding_model_answer(records=workspace_records)

        if "total storage" in normalized or "storage used" in normalized:
            total_size = sum(record.document.size_bytes for record in workspace_records)
            return self._format_storage_answer(
                records=workspace_records, total_size=total_size
            )

        if "size" in normalized or "sizes" in normalized:
            return self._format_storage_answer(
                records=workspace_records,
                total_size=sum(
                    record.document.size_bytes for record in workspace_records
                ),
                include_per_document=True,
            )

        if (
            "latest" in normalized
            or "last uploaded" in normalized
            or "most recent" in normalized
        ):
            latest = max(
                workspace_records, key=lambda item: item.document.created_at
            ).document
            return (
                f"The latest uploaded document is {latest.filename}.\n"
                f"Status: {latest.status}\n"
                f"Uploaded: {latest.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"Size: {self._format_bytes(latest.size_bytes)}"
            )

        if _FAILURE_DIAG_QUERY_RE.search(normalized):
            return self._format_failure_diagnosis_answer(records=workspace_records)

        if _OCR_VISION_QUERY_RE.search(normalized):
            return self._format_ocr_vision_answer(
                records=workspace_records, query_text=normalized
            )

        if _QUALITY_QUERY_RE.search(normalized):
            return self._format_quality_answer(records=workspace_records)

        if _COLLECTION_QUERY_RE.search(normalized):
            return self._format_collection_answer(
                records=workspace_records, query_text=normalized
            )

        if "indexed" in normalized or "failed" in normalized or "queued" in normalized:
            return self._format_status_answer(records=workspace_records)

        indexed_count = sum(
            1 for record in workspace_records if record.document.status == "indexed"
        )
        return self._format_inventory_list_answer(
            records=workspace_records,
            indexed_count=indexed_count,
        )

    @staticmethod
    def _is_document_inventory_query(query_text: str) -> bool:
        if _DOCUMENT_CONTENT_OVERRIDE_RE.search(query_text):
            return False
        return bool(
            _DOCUMENT_COUNT_QUERY_RE.search(query_text)
            or _DOCUMENT_LIST_QUERY_RE.search(query_text)
            or _DOCUMENT_METADATA_QUERY_RE.search(query_text)
            or _COLLECTION_QUERY_RE.search(query_text)
            or _COLLECTION_ANALYSIS_QUERY_RE.search(query_text)
            or _QUALITY_QUERY_RE.search(query_text)
            or _OCR_VISION_QUERY_RE.search(query_text)
            or _FAILURE_DIAG_QUERY_RE.search(query_text)
            or _COMPARISON_QUERY_RE.search(query_text)
        )

    @classmethod
    def _should_route_to_document_inventory(
        cls,
        *,
        query_text: str,
        document_ids: list[uuid.UUID] | None,
    ) -> bool:
        if not cls._is_document_inventory_query(query_text):
            return False
        if not document_ids:
            return True
        if cls._is_explicit_document_metadata_query(query_text):
            return True
        if cls._is_selected_document_content_query(query_text):
            return False
        return False

    @staticmethod
    def _is_explicit_document_metadata_query(query_text: str) -> bool:
        normalized = query_text.strip().lower()
        if _DOCUMENT_CONTENT_OVERRIDE_RE.search(normalized):
            return False
        if _DOCUMENT_CONTENT_INTENT_RE.search(normalized):
            return False
        if _DOCUMENT_OPERATIONAL_METADATA_RE.search(normalized):
            return True
        return bool(
            _DOCUMENT_COUNT_QUERY_RE.search(normalized)
            or _DOCUMENT_LIST_QUERY_RE.search(normalized)
            or _DOCUMENT_METADATA_QUERY_RE.search(normalized)
        )

    @staticmethod
    def _is_selected_document_content_query(query_text: str) -> bool:
        normalized = query_text.strip().lower()
        if _DOCUMENT_CONTENT_OVERRIDE_RE.search(normalized):
            return True
        if _DOCUMENT_OUTLINE_QUERY_RE.search(normalized):
            return True
        if _DOCUMENT_CONTENT_INTENT_RE.search(normalized):
            return True
        if _QUOTED_TERM_RE.search(normalized) and _CONTENT_FILTER_QUERY_RE.search(
            normalized
        ):
            return True
        return ":" in normalized and any(
            token in normalized
            for token in ("table", "figure", "diagram", "chart", "section")
        )

    @staticmethod
    def _is_document_outline_query(query_text: str) -> bool:
        return bool(_DOCUMENT_OUTLINE_QUERY_RE.search(query_text))

    def _build_workspace_records(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        documents: list[Any],
    ) -> list[DocumentWorkspaceRecord]:
        if not documents:
            return []

        document_ids = [doc.id for doc in documents]
        embedding_summaries = self.chunks.get_embedding_summaries_by_document_ids(
            tenant_id=tenant_id,
            document_ids=document_ids,
        )
        chunk_stats = self.chunks.get_chunk_stats_by_document_ids(
            tenant_id=tenant_id,
            document_ids=document_ids,
        )
        ingestion_jobs = self.jobs.get_by_document_ids(
            tenant_id=tenant_id,
            document_ids=document_ids,
        )
        collection_names = self.collections.get_document_collection_names_global(
            user_id=user_id,
            document_ids=document_ids,
        )

        results = []
        for doc in documents:
            summary = embedding_summaries.get(doc.id)
            stats = chunk_stats.get(doc.id)
            results.append(
                DocumentWorkspaceRecord(
                    document=doc,
                    embedding_provider=summary.provider if summary else None,
                    embedding_model=summary.model if summary else None,
                    embedded_chunk_count=summary.embedded_chunk_count if summary else 0,
                    chunk_count=stats.chunk_count if stats else 0,
                    avg_chunk_quality=stats.avg_quality_score if stats else None,
                    ingestion_job=ingestion_jobs.get(doc.id),
                    collections=collection_names.get(doc.id, []),
                )
            )
        return results

    def _apply_metadata_question_filters(
        self,
        *,
        records: list[DocumentWorkspaceRecord],
        query_text: str,
    ) -> list[DocumentWorkspaceRecord]:
        next_documents = list(records)

        status_matches = [
            match.group(1).lower().replace(" ", "_").replace("-", "_")
            for match in _DOC_STATUS_RE.finditer(query_text)
        ]
        if any(token in query_text for token in ("embedding model", "embedder")):
            status_matches = [
                status for status in status_matches if status != "embedding"
            ]
        if (
            len(set(status_matches)) == 1
            and (
                query_text.startswith("show ")
                or query_text.startswith("list ")
                or query_text.startswith("which ")
            )
            and " vs " not in query_text
            and " or " not in query_text
        ):
            requested = status_matches[0]
            next_documents = [
                record
                for record in next_documents
                if record.document.status == requested
            ]

        named_match = _NAMED_FILTER_RE.search(query_text)
        if named_match:
            raw = named_match.group(1) or named_match.group(2) or ""
            needle = raw.strip().strip("?").strip().lower()
            if needle:
                next_documents = [
                    record
                    for record in next_documents
                    if needle in record.document.filename.lower()
                ]

        collection_name = self._extract_collection_filter(query_text, next_documents)
        if collection_name:
            collection_needle = collection_name.lower()
            next_documents = [
                record
                for record in next_documents
                if any(
                    collection_needle in collection.lower()
                    for collection in record.collections
                )
            ]

        embedding_model = self._extract_embedding_model_filter(query_text)
        if embedding_model:
            embedding_needle = embedding_model.lower()
            next_documents = [
                record
                for record in next_documents
                if record.embedding_model is not None
                and embedding_needle in record.embedding_model.lower()
            ]

        now = datetime.now(tz=UTC)
        if "uploaded today" in query_text or re.search(r"(?i)\btoday\b", query_text):
            today = now.date()
            next_documents = [
                record
                for record in next_documents
                if record.document.created_at.astimezone(UTC).date() == today
            ]
        elif "uploaded yesterday" in query_text or re.search(
            r"(?i)\byesterday\b", query_text
        ):
            yesterday = (now - timedelta(days=1)).date()
            next_documents = [
                record
                for record in next_documents
                if record.document.created_at.astimezone(UTC).date() == yesterday
            ]
        elif "this week" in query_text:
            week_start = (now - timedelta(days=now.weekday())).date()
            next_documents = [
                record
                for record in next_documents
                if record.document.created_at.astimezone(UTC).date() >= week_start
            ]
        elif "this month" in query_text:
            next_documents = [
                record
                for record in next_documents
                if (
                    record.document.created_at.astimezone(UTC).year == now.year
                    and record.document.created_at.astimezone(UTC).month == now.month
                )
            ]

        return next_documents

    def _format_embedding_model_answer(
        self, *, records: list[DocumentWorkspaceRecord]
    ) -> str:
        lines = ["Embedding runtime by document:"]
        for record in records:
            doc = record.document
            if record.embedding_model is None:
                lines.append(f"- {doc.filename}: not embedded yet")
                continue
            lines.append(
                f"- {doc.filename}: {record.embedding_provider} / {record.embedding_model} "
                f"({record.embedded_chunk_count} chunks)"
            )
        return "\n".join(lines)

    def _format_status_answer(self, *, records: list[DocumentWorkspaceRecord]) -> str:
        by_status: dict[str, list[Any]] = {}
        for record in records:
            by_status.setdefault(record.document.status, []).append(record.document)

        lines = [f"Document status summary for {len(records)} documents:"]
        for status in sorted(by_status):
            lines.append(f"- {status}: {len(by_status[status])}")

        lines.append("")
        lines.append("Documents:")
        for record in records:
            doc = record.document
            lines.append(f"- {doc.filename} ({doc.status})")
        return "\n".join(lines)

    def _format_storage_answer(
        self,
        *,
        records: list[DocumentWorkspaceRecord],
        total_size: int,
        include_per_document: bool = False,
    ) -> str:
        lines = [
            f"Total storage used by {len(records)} documents: {self._format_bytes(total_size)}"
        ]
        if include_per_document:
            lines.append("")
            lines.append("Per-document sizes:")
            for record in records:
                doc = record.document
                lines.append(f"- {doc.filename}: {self._format_bytes(doc.size_bytes)}")
        return "\n".join(lines)

    def _format_inventory_list_answer(
        self,
        *,
        records: list[DocumentWorkspaceRecord],
        indexed_count: int | None = None,
    ) -> str:
        resolved_indexed = indexed_count
        if resolved_indexed is None:
            resolved_indexed = sum(
                1 for record in records if record.document.status == "indexed"
            )

        lines = [f"You currently have {len(records)} documents in this workspace."]
        if resolved_indexed == len(records):
            lines.append("All of them are indexed and ready for querying.")
        else:
            lines.append(f"{resolved_indexed} of them are indexed and query-ready.")
        lines.append("")
        lines.append("Available documents:")
        for record in records:
            doc = record.document
            lines.append(f"- {doc.filename} ({doc.status})")
        return "\n".join(lines)

    def _format_empty_inventory_result(
        self,
        *,
        query_text: str,
        all_records: list[DocumentWorkspaceRecord],
    ) -> str:
        if not all_records:
            return "You currently have no available documents in this workspace."

        named_match = _NAMED_FILTER_RE.search(query_text)
        if named_match:
            raw = named_match.group(1) or named_match.group(2) or ""
            needle = raw.strip().strip("?").strip()
            if needle:
                lines = [f'No documents matched the filename filter "{needle}".']
                if (
                    _FALLBACK_LIST_RE.search(query_text)
                    or "what documents" in query_text
                ):
                    lines.append("")
                    lines.append(
                        self._format_inventory_list_answer(records=all_records)
                    )
                return "\n".join(lines)

        collection_name = self._extract_collection_filter(query_text, all_records)
        if collection_name:
            return f'No documents matched collection "{collection_name}" in the current workspace slice.'

        embedding_model = self._extract_embedding_model_filter(query_text)
        if embedding_model:
            return f'No documents matched embedding model "{embedding_model}" in the current workspace slice.'

        status_matches = [
            match.group(1).lower().replace(" ", "_").replace("-", "_")
            for match in _DOC_STATUS_RE.finditer(query_text)
        ]
        if status_matches:
            requested = status_matches[0]
            return f'No documents matched the requested status filter "{requested}".'

        return "No documents matched the requested workspace filters."

    def _build_inventory_grounding_chunks(
        self,
        *,
        query_text: str,
        grounding_text: str,
    ) -> list[RetrievedChunk]:
        metadata_content = (
            "Workspace metadata snapshot. Treat this as the source of truth for the current question.\n"
            "Rules:\n"
            "- Answer naturally, but only from the metadata in this snapshot.\n"
            "- Use fluent prose instead of copying the snapshot labels verbatim.\n"
            "- If the user asks for each document separately, organize the answer by document with clear sections.\n"
            "- Prefer complete sentences, direct wording, and concrete detail from the snapshot.\n"
            "- Never claim the workspace is empty unless the snapshot explicitly says there are no documents.\n"
            "- If a requested filename or filter has no match, say that clearly.\n"
            "- If the user asks what documents are available instead, list the available documents from this snapshot.\n\n"
            f"User request:\n{query_text}\n\n"
            f"Grounded workspace facts:\n{grounding_text}"
        )
        return [
            RetrievedChunk(
                document_id=generate_uuid7_with_fallback(),
                chunk_id=generate_uuid7_with_fallback(),
                filename="workspace-metadata",
                content=metadata_content,
                similarity_score=1.0,
                source_type="workspace",
                section_header="document_inventory",
                page_number=None,
            )
        ]

    @staticmethod
    def _build_inventory_llm_query(query_text: str) -> str:
        return (
            f"{query_text}\n\n"
            "Answer from the workspace metadata snapshot only. "
            "Keep the wording natural, direct, and non-template-like. "
            "Write like an intelligent assistant, not like a status dump. "
            "When the user asks for detailed information separately, break the answer into per-document sections. "
            "If no filename/filter matches, say that explicitly instead of saying the workspace is empty."
        )

    def _build_outline_grounding_chunks(
        self,
        *,
        query_text: str,
        grounding_text: str,
    ) -> list[RetrievedChunk]:
        outline_content = (
            "Document outline snapshot. Treat this as the source of truth for the current question.\n"
            "- Answer naturally, but only from the outline in this snapshot.\n"
            "- If the user asks for document titles or section headings, state them directly.\n\n"
            f"User request:\n{query_text}\n\n"
            f"Grounded outline facts:\n{grounding_text}"
        )
        return [
            RetrievedChunk(
                document_id=generate_uuid7_with_fallback(),
                chunk_id=generate_uuid7_with_fallback(),
                filename="document-outline",
                content=outline_content,
                similarity_score=1.0,
                source_type="workspace",
                section_header="document_outline",
                page_number=None,
            )
        ]

    @staticmethod
    def _build_outline_llm_query(query_text: str) -> str:
        return (
            f"{query_text}\n\n"
            "Answer from the document outline snapshot only. "
            "If titles or section headings are available, present them clearly and naturally."
        )

    def _extract_document_outline_from_chunks(
        self,
        chunk_contents: list[str],
    ) -> tuple[str | None, list[str]]:
        title: str | None = None
        headings: list[str] = []
        seen: set[str] = set()

        for chunk in chunk_contents[:12]:
            for raw_line in chunk.splitlines():
                line = " ".join(raw_line.split()).strip(" -\t")
                if not line or len(line) < 3:
                    continue
                if title is None and self._looks_like_document_title(line):
                    title = line
                    continue
                if self._looks_like_section_heading(line):
                    normalized = line.rstrip(".")
                    if normalized.lower() in seen:
                        continue
                    seen.add(normalized.lower())
                    headings.append(normalized)
        return title, headings

    @staticmethod
    def _looks_like_document_title(line: str) -> bool:
        lowered = line.lower()
        if any(
            token in lowered
            for token in (
                "published as",
                "conference paper",
                "cornell university",
                "{",
                "@",
                "arxiv",
            )
        ):
            return False
        if line.endswith("."):
            return False
        if _SECTION_HEADING_LINE_RE.match(line):
            return False
        return bool(_TITLE_CANDIDATE_RE.match(line))

    @staticmethod
    def _looks_like_section_heading(line: str) -> bool:
        compact = line.strip()
        if len(compact) > 120:
            return False
        if compact.endswith(".") and len(compact.split()) > 6:
            return False
        if _SECTION_HEADING_LINE_RE.match(compact):
            return True
        return bool(
            re.match(r"^\d+(?:\.\d+)*\s+[A-Z][A-Za-z0-9 ,:/()'\-]{2,80}$", compact)
        )

    def _format_failure_diagnosis_answer(
        self, *, records: list[DocumentWorkspaceRecord]
    ) -> str:
        failures = [
            record
            for record in records
            if record.document.status in {"failed", "dead_lettered"}
            or (
                record.ingestion_job is not None
                and record.ingestion_job.last_error_message
            )
        ]
        if not failures:
            return "No failed or dead-lettered documents were found in this workspace."

        lines = ["Failed ingestion diagnostics:"]
        for record in failures:
            lines.extend(self._render_failure_record(record))
        return "\n".join(lines)

    def _format_ocr_vision_answer(
        self,
        *,
        records: list[DocumentWorkspaceRecord],
        query_text: str,
    ) -> str:
        target = (
            "ocr"
            if "ocr" in query_text and "vision" not in query_text
            else (
                "vision"
                if "vision" in query_text and "ocr" not in query_text
                else "both"
            )
        )
        if target == "ocr":
            filtered = [
                record for record in records if record.document.extraction_ocr_used
            ]
            label = "OCR"
        elif target == "vision":
            filtered = [
                record for record in records if record.document.extraction_vision_used
            ]
            label = "Vision"
        else:
            filtered = [
                record
                for record in records
                if record.document.extraction_ocr_used
                or record.document.extraction_vision_used
            ]
            label = "OCR/Vision"

        if not filtered:
            return f"No documents using {label} were found."

        lines = [f"Documents using {label}:"]
        for record in filtered:
            doc = record.document
            details: list[str] = []
            if doc.extraction_ocr_used:
                details.append("OCR")
            if doc.extraction_vision_used:
                details.append("Vision")
            extra: list[str] = []
            if doc.extraction_method:
                extra.append(doc.extraction_method)
            if doc.extraction_coverage_score is not None:
                extra.append(f"coverage {round(doc.extraction_coverage_score * 100)}%")
            suffix = f" | {', '.join(extra)}" if extra else ""
            lines.append(f"- {doc.filename} ({', '.join(details)}){suffix}")
        return "\n".join(lines)

    def _format_quality_answer(self, *, records: list[DocumentWorkspaceRecord]) -> str:
        low_quality = [
            record
            for record in records
            if record.document.quarantined
            or (
                record.document.information_yield is not None
                and record.document.information_yield < 70
            )
            or (
                record.document.extraction_coverage_score is not None
                and record.document.extraction_coverage_score < 0.5
            )
        ]
        if not low_quality:
            return "No low-quality documents were detected in the current workspace."

        lines = ["Low-quality document signals:"]
        for record in low_quality:
            doc = record.document
            quality_reasons = self._quality_signals(record)
            lines.append(f"- {doc.filename}: {', '.join(quality_reasons)}")
            if doc.extraction_warnings:
                lines.append(f"  Warnings: {', '.join(doc.extraction_warnings)}")
        return "\n".join(lines)

    def _format_collection_answer(
        self,
        *,
        records: list[DocumentWorkspaceRecord],
        query_text: str,
    ) -> str:
        collection_name = self._extract_collection_filter(query_text, records)
        if collection_name:
            filtered = [
                record
                for record in records
                if any(
                    collection_name.lower() in collection.lower()
                    for collection in record.collections
                )
            ]
            if not filtered:
                return f'No documents were found in collection "{collection_name}".'

            lines = [f'Documents in collection "{collection_name}":']
            for record in filtered:
                lines.append(f"- {record.document.filename} ({record.document.status})")
            return "\n".join(lines)

        if "which collection" in query_text or "what collection" in query_text:
            lines = ["Collection membership by document:"]
            for record in records:
                doc = record.document
                if record.collections:
                    lines.append(f"- {doc.filename}: {', '.join(record.collections)}")
                else:
                    lines.append(f"- {doc.filename}: no collection")
            return "\n".join(lines)

        collection_index: dict[str, list[str]] = {}
        for record in records:
            for name in record.collections:
                collection_index.setdefault(name, []).append(record.document.filename)
        if not collection_index:
            return "No collection memberships were found for the current document set."

        lines = ["Collections in this workspace slice:"]
        for name in sorted(collection_index):
            lines.append(f"- {name}: {len(collection_index[name])} documents")
        return "\n".join(lines)

    def _maybe_build_document_comparison_answer(
        self,
        *,
        query_text: str,
        records: list[DocumentWorkspaceRecord],
        tenant_id: uuid.UUID,
    ) -> str | None:
        explicit_needles = self._extract_named_comparison_needles(query_text)
        if not self._has_explicit_comparison_intent(
            query_text=query_text,
            records=records,
            explicit_needles=explicit_needles,
        ):
            return None

        comparison_records = self._select_records_for_comparison(
            query_text=query_text,
            records=records,
            explicit_needles=explicit_needles,
        )
        if len(comparison_records) < 2:
            return None

        evidence_term = self._extract_content_filter_term(query_text)
        evidence_hits = self._collect_evidence_hits(
            tenant_id=tenant_id,
            records=comparison_records,
            evidence_term=evidence_term,
        )
        scored = [
            (record, self._compute_document_health(record))
            for record in comparison_records[:5]
        ]
        healthiest = max(scored, key=lambda item: item[1]["score"])
        weakest = min(scored, key=lambda item: item[1]["score"])

        lines = [
            f"Compared {len(scored)} documents across content evidence, ingestion health, extraction quality, and runtime setup.",
            f"Healthiest overall: {healthiest[0].document.filename} ({healthiest[1]['score']}/100).",
            f"Most at risk: {weakest[0].document.filename} ({weakest[1]['score']}/100).",
            "",
        ]
        for record, health in scored:
            doc = record.document
            extraction_bits = self._describe_extraction(record)
            runtime_bits = self._describe_runtime(record)
            lines.append(
                f"- {doc.filename}: status {doc.status}, health {health['score']}/100 ({health['band']})"
            )
            lines.append(f"  Extraction: {extraction_bits}")
            lines.append(f"  Runtime: {runtime_bits}")
            if health["reasons"]:
                lines.append(f"  Signals: {', '.join(health['reasons'])}")
            for evidence in evidence_hits.get(doc.id, []):
                lines.append(f"  Evidence: {evidence}")
        return "\n".join(lines)

    def _maybe_build_collection_analysis_answer(
        self,
        *,
        query_text: str,
        records: list[DocumentWorkspaceRecord],
    ) -> str | None:
        collection_index: dict[str, list[DocumentWorkspaceRecord]] = {}
        for record in records:
            for name in record.collections:
                collection_index.setdefault(name, []).append(record)

        if not collection_index:
            return None

        collection_name = self._extract_collection_filter(query_text, records)
        if collection_name and (
            "summary" in query_text
            or "summarize" in query_text
            or "overview" in query_text
        ):
            return self._format_collection_summary(
                collection_name=collection_name,
                records=collection_index.get(collection_name, []),
            )

        coverage_term = self._extract_collection_topic(query_text)
        if coverage_term:
            ranked_collections = sorted(
                (
                    (
                        name,
                        self._score_collection_coverage(
                            records=collection_records,
                            query_term=coverage_term,
                        ),
                    )
                    for name, collection_records in collection_index.items()
                ),
                key=lambda item: item[1]["score"],
                reverse=True,
            )
            best_name, best_payload = ranked_collections[0]
            lines = [
                f'The strongest collection for "{coverage_term}" is {best_name}.',
                f"Coverage score: {best_payload['score']:.1f}",
                f"Matching documents: {best_payload['matched_docs']}/{best_payload['document_count']}",
            ]
            if best_payload["evidence"]:
                lines.append("Evidence:")
                for evidence in best_payload["evidence"][:3]:
                    lines.append(f"- {evidence}")
            if len(ranked_collections) > 1:
                runner_up_name, runner_up_payload = ranked_collections[1]
                lines.append(
                    f"Runner-up: {runner_up_name} ({runner_up_payload['score']:.1f})"
                )
            return "\n".join(lines)

        return None

    def _maybe_answer_metadata_content_query(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        records: list[DocumentWorkspaceRecord],
    ) -> str | None:
        if not self._is_explicit_metadata_content_filter_query(query_text):
            return None

        term = self._extract_content_filter_term(query_text)
        if not term:
            return None

        retrieved = self.chunks.search_document_text(
            tenant_id=auth.tenant_id,
            query=term,
            document_ids=[record.document.id for record in records],
            limit=min(max(len(records) * 3, 6), 30),
        )
        if not retrieved:
            return f'No documents in the current filtered set matched "{term}".'

        matched: dict[uuid.UUID, DocumentWorkspaceRecord] = {
            record.document.id: record
            for record in records
            if any(hit.document_id == record.document.id for hit in retrieved)
        }
        if not matched:
            return f'No documents in the current filtered set matched "{term}".'

        scope = self._describe_filter_scope(records=records, query_text=query_text)
        lines = [f'Documents matching "{term}" {scope}:']
        hits_by_document: dict[uuid.UUID, list[Any]] = {}
        for hit in retrieved:
            hits_by_document.setdefault(hit.document_id, []).append(hit)

        for record in matched.values():
            doc = record.document
            lines.append(f"- {doc.filename} ({doc.status})")
            for hit in hits_by_document.get(doc.id, [])[:2]:
                snippet = SnippetService.clean(hit.content, max_chars=180)
                page = f" p.{hit.page_number}" if hit.page_number is not None else ""
                lines.append(f"  Evidence{page}: {snippet}")
        return "\n".join(lines)

    @staticmethod
    def _extract_content_filter_term(query_text: str) -> str | None:
        quoted = _QUOTED_TERM_RE.search(query_text)
        if quoted:
            return quoted.group(1).strip()

        for marker in (
            "mention ",
            "mentions ",
            "contains ",
            "contain ",
            "about ",
            "discuss ",
        ):
            if marker in query_text:
                term = query_text.split(marker, 1)[1].strip().strip("?").strip()
                return term or None
        return None

    @staticmethod
    def _is_explicit_metadata_content_filter_query(query_text: str) -> bool:
        normalized = query_text.strip().lower()
        if not _CONTENT_FILTER_QUERY_RE.search(normalized):
            return False
        if _QUOTED_TERM_RE.search(normalized):
            return True
        explicit_prefixes = (
            "which documents mention ",
            "which documents mentions ",
            "which documents contain ",
            "which documents contains ",
            "which documents talk about ",
            "which documents discuss ",
            "which documents are about ",
            "show documents that mention ",
            "show documents containing ",
            "show documents about ",
            "list documents that mention ",
            "list documents containing ",
            "list documents about ",
            "what documents mention ",
            "what documents contain ",
            "what documents are about ",
            "which files mention ",
            "which files contain ",
            "which pdfs mention ",
            "which pdfs contain ",
        )
        return any(prefix in normalized for prefix in explicit_prefixes)

    def _extract_collection_filter(
        self,
        query_text: str,
        records: list[DocumentWorkspaceRecord],
    ) -> str | None:
        available_collections = {
            collection.lower(): collection
            for record in records
            for collection in record.collections
        }
        if not available_collections:
            return None

        explicit_match = _COLLECTION_FILTER_RE.search(query_text)
        if explicit_match:
            raw_value = next((group for group in explicit_match.groups() if group), "")
            candidate = raw_value.strip().strip("?").strip()
            if candidate and candidate.lower() not in {
                "do you have",
                "contains",
                "membership",
            }:
                for lowered, original in available_collections.items():
                    if candidate.lower() in lowered or lowered in candidate.lower():
                        return original

        for lowered, original in available_collections.items():
            if lowered in query_text:
                return original
        return None

    @staticmethod
    def _extract_embedding_model_filter(query_text: str) -> str | None:
        explicit_match = _EMBEDDING_MODEL_FILTER_RE.search(query_text)
        if explicit_match:
            candidate = next((group for group in explicit_match.groups() if group), "")
            candidate = candidate.strip().strip("?").strip()
            if candidate and candidate.lower() not in {
                "per",
                "per document",
                "used",
                "was used",
            }:
                return candidate
        return None

    def _quality_signals(self, record: DocumentWorkspaceRecord) -> list[str]:
        doc = record.document
        quality_reasons: list[str] = []
        if doc.quarantined:
            quality_reasons.append("quarantined")
        if doc.information_yield is not None and doc.information_yield < 70:
            quality_reasons.append(f"yield {round(doc.information_yield)}%")
        if (
            doc.extraction_coverage_score is not None
            and doc.extraction_coverage_score < 0.5
        ):
            quality_reasons.append(
                f"coverage {round(doc.extraction_coverage_score * 100)}%"
            )
        if record.embedded_chunk_count == 0 and doc.status != "indexed":
            quality_reasons.append("no embedded chunks")
        if not quality_reasons:
            quality_reasons.append("no major low-quality signal recorded")
        return quality_reasons

    def _render_failure_record(self, record: DocumentWorkspaceRecord) -> list[str]:
        doc = record.document
        job = record.ingestion_job
        reason = (
            getattr(job, "last_error_message", None)
            or getattr(job, "dead_letter_reason", None)
            or getattr(job, "last_error_code", None)
            or "No explicit error message recorded."
        )
        code = getattr(job, "last_error_code", None) if job is not None else None
        attempts = (
            f"{job.attempt_count}/{job.max_attempts}"
            if job is not None and getattr(job, "max_attempts", None)
            else None
        )
        stage = getattr(job, "status", None) if job is not None else None

        lines = [f"- {doc.filename} ({doc.status})"]
        if stage:
            lines.append(f"  Stage: {stage}")
        lines.append(f"  Progress: {doc.processing_progress}%")
        if attempts:
            lines.append(f"  Attempts: {attempts}")
        if code:
            lines.append(f"  Error code: {code}")
        lines.append(f"  Reason: {reason}")
        if doc.extraction_warnings:
            lines.append(f"  Extraction warnings: {', '.join(doc.extraction_warnings)}")
        return lines

    def _describe_filter_scope(
        self,
        *,
        records: list[DocumentWorkspaceRecord],
        query_text: str,
    ) -> str:
        scope_parts: list[str] = []
        status_matches = {
            match.group(1).lower().replace(" ", "_").replace("-", "_")
            for match in _DOC_STATUS_RE.finditer(query_text)
        }
        if len(status_matches) == 1:
            scope_parts.append(f"within {next(iter(status_matches))} documents")

        collection_name = self._extract_collection_filter(query_text, records)
        if collection_name:
            scope_parts.append(f'in collection "{collection_name}"')

        embedding_model = self._extract_embedding_model_filter(query_text)
        if embedding_model:
            scope_parts.append(f'using embedding model "{embedding_model}"')

        if _OCR_VISION_QUERY_RE.search(query_text):
            if "ocr" in query_text and "vision" not in query_text:
                scope_parts.append("using OCR")
            elif "vision" in query_text and "ocr" not in query_text:
                scope_parts.append("using vision extraction")

        if _QUALITY_QUERY_RE.search(query_text):
            scope_parts.append("within the low-quality slice")

        if not scope_parts:
            return "after metadata filtering"
        return "in the filtered workspace slice (" + ", ".join(scope_parts) + ")"

    def _select_records_for_comparison(
        self,
        *,
        query_text: str,
        records: list[DocumentWorkspaceRecord],
        explicit_needles: list[str] | None = None,
    ) -> list[DocumentWorkspaceRecord]:
        resolved_needles = explicit_needles or self._extract_named_comparison_needles(
            query_text
        )
        matched = []
        for record in records:
            filename = record.document.filename.lower()
            basename = filename.rsplit(".", 1)[0]
            if filename in query_text or basename in query_text:
                matched.append(record)
                continue
            if any(
                needle in filename or needle in basename for needle in resolved_needles
            ):
                matched.append(record)

        if len(matched) >= 2:
            deduped: dict[uuid.UUID, DocumentWorkspaceRecord] = {}
            for record in matched:
                deduped[record.document.id] = record
            return list(deduped.values())

        return records[: min(len(records), 5)]

    @staticmethod
    def _extract_named_comparison_needles(query_text: str) -> list[str]:
        return [
            match.group(1).strip().lower()
            for match in _QUOTED_TERM_RE.finditer(query_text)
        ]

    def _has_explicit_comparison_intent(
        self,
        *,
        query_text: str,
        records: list[DocumentWorkspaceRecord],
        explicit_needles: list[str],
    ) -> bool:
        if any(
            token in query_text
            for token in ("compare", "comparison", "difference", "side by side")
        ):
            return True

        if any(token in query_text for token in ("versus", " vs ", " vs.", " vs?")):
            return (
                any(
                    record.document.filename.lower() in query_text
                    or record.document.filename.lower().rsplit(".", 1)[0] in query_text
                    for record in records
                )
                or len(explicit_needles) >= 2
            )

        return False

    def _collect_evidence_hits(
        self,
        *,
        tenant_id: uuid.UUID,
        records: list[DocumentWorkspaceRecord],
        evidence_term: str | None,
    ) -> dict[uuid.UUID, list[str]]:
        if evidence_term:
            hits = self.chunks.search_document_text(
                tenant_id=tenant_id,
                document_ids=[record.document.id for record in records],
                query=evidence_term,
                limit=min(max(len(records) * 2, 4), 20),
            )
            grouped: dict[uuid.UUID, list[str]] = {}
            for hit in hits:
                snippet = SnippetService.clean(hit.content, max_chars=170)
                page = (
                    f"p.{hit.page_number}" if hit.page_number is not None else "snippet"
                )
                grouped.setdefault(hit.document_id, []).append(f"{page}: {snippet}")
            return grouped

        grouped = {}
        for record in records:
            preview_chunks = self.chunks.get_by_document_id(
                tenant_id=tenant_id,
                document_id=record.document.id,
                limit=1,
            )
            if not preview_chunks:
                continue
            grouped[record.document.id] = [
                SnippetService.clean(preview_chunks[0].content, max_chars=170)
            ]
        return grouped

    @staticmethod
    def _extract_collection_topic(query_text: str) -> str | None:
        for marker in (
            "best collection for ",
            "best collection to answer ",
            "strongest coverage for ",
            "which collection has the strongest coverage for ",
            "which collection is best for ",
        ):
            if marker in query_text:
                term = (
                    query_text.split(marker, 1)[1]
                    .strip()
                    .strip("?")
                    .strip()
                    .strip('"')
                    .strip("'")
                )
                return term or None
        return None

    def _score_collection_coverage(
        self,
        *,
        records: list[DocumentWorkspaceRecord],
        query_term: str,
    ) -> dict[str, Any]:
        hits = self.chunks.search_document_text(
            tenant_id=records[0].document.tenant_id,
            document_ids=[record.document.id for record in records],
            query=query_term,
            limit=min(max(len(records) * 4, 8), 30),
        )
        matched_doc_ids = {hit.document_id for hit in hits}
        avg_health = (
            sum(self._compute_document_health(record)["score"] for record in records)
            / len(records)
            if records
            else 0.0
        )
        evidence = []
        for hit in hits[:4]:
            snippet = SnippetService.clean(hit.content, max_chars=160)
            evidence.append(f"{hit.filename}: {snippet}")
        score = (len(matched_doc_ids) * 10.0) + (len(hits) * 2.0) + (avg_health * 0.1)
        return {
            "score": score,
            "matched_docs": len(matched_doc_ids),
            "document_count": len(records),
            "evidence": evidence,
        }

    def _format_collection_summary(
        self,
        *,
        collection_name: str,
        records: list[DocumentWorkspaceRecord],
    ) -> str:
        if not records:
            return f'No documents were found in collection "{collection_name}".'

        total_size = sum(record.document.size_bytes for record in records)
        avg_health = sum(
            self._compute_document_health(record)["score"] for record in records
        ) / len(records)
        statuses: dict[str, int] = {}
        for record in records:
            statuses[record.document.status] = (
                statuses.get(record.document.status, 0) + 1
            )

        lines = [
            f'Collection summary for "{collection_name}":',
            f"- Documents: {len(records)}",
            f"- Total storage: {self._format_bytes(total_size)}",
            f"- Average document health: {avg_health:.1f}/100",
            f"- Status mix: {', '.join(f'{status}={count}' for status, count in sorted(statuses.items()))}",
            "Documents:",
        ]
        for record in records[:6]:
            health = self._compute_document_health(record)
            lines.append(
                f"- {record.document.filename}: {record.document.status}, health {health['score']}/100, "
                f"embedding {record.embedding_model or 'not embedded'}"
            )
        return "\n".join(lines)

    def _compute_document_health(
        self, record: DocumentWorkspaceRecord
    ) -> dict[str, Any]:
        doc = record.document
        score = 100.0
        reasons: list[str] = []

        if doc.status in {"failed", "dead_lettered"}:
            score -= 40
            reasons.append("failed ingestion")
        elif doc.status in {
            "queued",
            "downloading",
            "parsing",
            "chunking",
            "embedding",
        }:
            score -= 15
            reasons.append(f"in-progress ({doc.status})")
        elif doc.status == "needs_reingestion":
            score -= 25
            reasons.append("needs re-ingestion")

        if doc.quarantined:
            score -= 20
            reasons.append("quarantined")
        if doc.information_yield is not None:
            if doc.information_yield < 70:
                score -= min(25.0, (70 - doc.information_yield) * 0.5)
                reasons.append(f"low yield {round(doc.information_yield)}%")
        else:
            score -= 8
            reasons.append("missing yield score")
        if doc.extraction_coverage_score is not None:
            if doc.extraction_coverage_score < 0.5:
                score -= min(20.0, (0.5 - doc.extraction_coverage_score) * 40)
                reasons.append(
                    f"low coverage {round(doc.extraction_coverage_score * 100)}%"
                )
        else:
            score -= 6
            reasons.append("missing coverage score")

        if doc.extraction_warnings:
            score -= min(12.0, len(doc.extraction_warnings) * 4.0)
            reasons.append(f"{len(doc.extraction_warnings)} extraction warning(s)")
        if record.embedded_chunk_count == 0:
            score -= 18
            reasons.append("no embedded chunks")
        if record.chunk_count == 0:
            score -= 12
            reasons.append("no text chunks")
        if record.avg_chunk_quality is not None and record.avg_chunk_quality < 0:
            score -= min(10.0, abs(record.avg_chunk_quality) * 10.0)
            reasons.append(
                f"negative citation feedback ({record.avg_chunk_quality:.2f})"
            )

        final_score = max(0, min(100, int(round(score))))
        if final_score >= 85:
            band = "strong"
        elif final_score >= 70:
            band = "healthy"
        elif final_score >= 50:
            band = "watch"
        elif final_score >= 30:
            band = "at-risk"
        else:
            band = "critical"
        return {"score": final_score, "band": band, "reasons": reasons}

    def _describe_extraction(self, record: DocumentWorkspaceRecord) -> str:
        doc = record.document
        method = doc.extraction_method or "unknown method"
        coverage = (
            f"coverage {round(doc.extraction_coverage_score * 100)}%"
            if doc.extraction_coverage_score is not None
            else "coverage n/a"
        )
        yield_text = (
            f"yield {round(doc.information_yield)}%"
            if doc.information_yield is not None
            else "yield n/a"
        )
        modality = []
        if doc.extraction_ocr_used:
            modality.append("OCR")
        if doc.extraction_vision_used:
            modality.append("Vision")
        if not modality:
            modality.append("native text")
        return f"{method}, {coverage}, {yield_text}, {', '.join(modality)}"

    def _describe_runtime(self, record: DocumentWorkspaceRecord) -> str:
        embedding = (
            f"{record.embedding_provider} / {record.embedding_model}"
            if record.embedding_model
            else "not embedded"
        )
        collections = (
            ", ".join(record.collections) if record.collections else "no collection"
        )
        quality = (
            f", avg chunk quality {record.avg_chunk_quality:.2f}"
            if record.avg_chunk_quality is not None
            else ""
        )
        return (
            f"{embedding}, chunks {record.chunk_count}, embedded {record.embedded_chunk_count}, "
            f"collections {collections}{quality}"
        )

    @staticmethod
    def _format_bytes(size_bytes: int) -> str:
        value = float(size_bytes)
        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.2f} {unit}"
            value /= 1024
        return f"{size_bytes} B"

    def _persist_inventory_query_result(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        normalized_query: str,
        normalized_filters: dict[str, Any],
        top_k: int,
        answer: str | StructuredAnswerResponse,
        conversation_id: uuid.UUID,
        conversation_kind: str = "query",
        search_mode: str,
        confidence: float = 1.0,
        followup_items: list[str] | None = None,
        provider_metadata: dict[str, Any] | None = None,
    ) -> QueryExecutionResult:
        trace_id = self._resolve_trace_id()
        citations: list[dict[str, Any]] = []

        self.queries.create_query(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            query_text=query_text,
            normalized_query=normalized_query,
            filters=normalized_filters,
            top_k=top_k,
            cache_hit=False,
            answer=self._answer_to_storage_text(answer),
            confidence=confidence,
            trace_id=trace_id,
        )
        self.chat.add_message(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            kind=conversation_kind,
            role="assistant",
            content=self._answer_to_followup_text(answer),
            metadata_json={
                "trace_id": trace_id,
                "confidence": confidence,
                "citations": citations,
                "search_mode": search_mode,
                "provider": provider_metadata
                or {
                    "type": "system",
                    "model": "document_inventory",
                },
                "reasoning_trace": None,
                "status_history": self._followup_status_history(
                    list(followup_items or [])
                ),
                "files": [],
                "output": [],
                "follow_up_suggestions": list(followup_items or []),
            },
        )
        self._maybe_commit()

        return QueryExecutionResult(
            answer=answer,
            confidence=confidence,
            citations=citations,
            trace_id=trace_id,
            cached=False,
            conversation_id=conversation_id,
            reasoning_trace=None,
        )

    @staticmethod
    def _merge_unique_structured_blocks(
        existing: list[dict[str, Any]],
        incoming: dict[str, Any],
    ) -> list[dict[str, Any]]:
        incoming_type = str(incoming.get("type", "")).strip()
        incoming_id = str(incoming.get("id", "")).strip()
        if not incoming_type or not incoming_id:
            return existing
        next_blocks = list(existing)
        for index, block in enumerate(next_blocks):
            if (
                str(block.get("type", "")).strip() == incoming_type
                and str(block.get("id", "")).strip() == incoming_id
            ):
                next_blocks[index] = incoming
                return next_blocks
        next_blocks.append(incoming)
        return next_blocks

    def _build_persisted_block_payloads(
        self,
        answer: StructuredAnswerResponse | None,
    ) -> list[dict[str, Any]]:
        if answer is None:
            return []
        blocks: list[dict[str, Any]] = []
        if answer.comparison_table is not None:
            blocks.append(
                self.answer._build_table_payload(answer.comparison_table, index=1)
            )
        if answer.chart is not None:
            blocks.append(self.answer._build_chart_payload(answer.chart, index=1))
        if answer.diagram is not None:
            blocks.append(self.answer._build_diagram_payload(answer.diagram, index=1))
        return blocks

    def _enforce_quota(self, auth: AuthContext) -> None:
        if not self.billing.check_quota(tenant_id=auth.tenant_id):
            raise ApiError(
                code="QUOTA_EXCEEDED",
                message="Tenant token quota exceeded",
                status_code=402,
            )

    def _resolve_or_create_conversation(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        conversation_id: uuid.UUID | None,
        conversation_kind: str = "query",
    ) -> Any:
        if conversation_id:
            conversation = self.chat.get_conversation(
                tenant_id=auth.tenant_id,
                conversation_id=conversation_id,
                user_id=auth.user_id,
                kind=conversation_kind,
            )
            if not conversation:
                raise ApiError(
                    code="CONVERSATION_NOT_FOUND",
                    message="Conversation not found",
                    status_code=404,
                )
            return conversation

        return self.chat.create_conversation(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            title=query_text[:50] + "..." if len(query_text) > 50 else query_text,
            kind=conversation_kind,
        )

    def _provider_metadata(self, answer_result: Any | None) -> dict[str, Any] | None:
        if answer_result is None:
            return None

        provider_type = getattr(answer_result, "provider_type", None)
        if not isinstance(provider_type, str) or not provider_type:
            return None

        model_name = getattr(answer_result, "model_name", None)
        provider_source = getattr(answer_result, "provider_source", None)
        fallback_used = getattr(answer_result, "fallback_used", False)

        return {
            "type": provider_type,
            "model": model_name if isinstance(model_name, str) and model_name else None,
            "source": (
                provider_source
                if isinstance(provider_source, str) and provider_source
                else None
            ),
            "fallback_used": bool(fallback_used),
        }

    def _build_previous_messages(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        conversation_kind: str = "query",
    ) -> list[dict[str, str]]:
        history = self.chat.get_messages(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            kind=conversation_kind,
            limit=10,
        )
        return [
            {"role": m.role, "content": self._message_content_to_text(m.content)}
            for m in history
        ]

    def _retrieve_with_trace(
        self,
        *,
        auth: AuthContext,
        normalized_query: str,
        top_k: int,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
        source_types: list[str] | None,
        min_extraction_coverage: float | None,
        max_extraction_coverage: float | None,
        search_mode: str,
    ) -> dict[str, Any]:
        trace = TraceCollector()
        trace.start_stage("retrieval")
        retrieval_start = time.perf_counter()

        retrieved_chunks = self.retrieval.retrieve(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            query=normalized_query,
            top_k=top_k,
            document_ids=document_ids,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            source_types=source_types,
            min_extraction_coverage=min_extraction_coverage,
            max_extraction_coverage=max_extraction_coverage,
            search_mode=search_mode,
            trace=trace,
        )

        QUERY_PIPELINE_DURATION_SECONDS.labels(segment="retrieve").observe(
            time.perf_counter() - retrieval_start
        )

        hit_doc_ids = list({c.document_id for c in retrieved_chunks})
        if hit_doc_ids:
            biblio_chunks = self.retrieval.get_document_references(
                tenant_id=auth.tenant_id,
                document_ids=hit_doc_ids,
            )
            existing_chunk_ids = {c.chunk_id for c in retrieved_chunks}
            for chunk in biblio_chunks:
                if chunk.chunk_id not in existing_chunk_ids:
                    retrieved_chunks.insert(0, chunk)
                    existing_chunk_ids.add(chunk.chunk_id)

        trace.end_stage("retrieval")
        return {"retrieved_chunks": retrieved_chunks, "trace": trace}

    def _build_citation_dicts(
        self, chunks: list[RetrievedChunk]
    ) -> list[dict[str, Any]]:
        return [
            {
                "document_id": str(c.document_id),
                "chunk_id": str(c.chunk_id),
                "filename": c.filename,
                "snippet": SnippetService.clean(c.content, 240),
                "similarity_score": round(c.similarity_score, 6),
                "source_type": c.source_type,
                "section_header": c.section_header,
                "page_number": c.page_number,
            }
            for c in chunks[:3]
        ]

    def _generate_followups(
        self,
        *,
        query_text: str,
        answer_text: str,
        tenant_id: uuid.UUID,
        previous_messages: list[dict[str, str]] | None,
        provider_candidates: list[ProviderSelectionCandidate],
    ) -> list[str]:
        if not answer_text.strip():
            return []
        payload = self.followups.generate(
            query_text=query_text,
            answer_text=answer_text,
            tenant_id=tenant_id,
            previous_messages=previous_messages,
            provider_candidates=provider_candidates,
        )
        return payload.follow_ups

    @staticmethod
    def _build_followup_events(items: list[str]) -> list[StreamEvent]:
        if not items:
            return []
        return [
            QueryService._status_event(
                code="followups",
                label="Preparing Follow-ups",
                state="running",
                detail="Preparing suggested next questions",
            ),
            StreamEvent(event="followups", data={"items": items}),
            QueryService._status_event(
                code="followups",
                label="Preparing Follow-ups",
                state="completed",
                detail=f"Prepared {len(items)} follow-up suggestions",
            ),
        ]

    @staticmethod
    def _status_timestamp() -> str:
        return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")

    @classmethod
    def _status_event(
        cls,
        *,
        code: str,
        label: str,
        state: str,
        detail: str | None = None,
        duration_ms: float | None = None,
        timestamp: str | None = None,
    ) -> StreamEvent:
        payload: dict[str, Any] = {
            "code": code,
            "label": label,
            "state": state,
            "timestamp": timestamp or cls._status_timestamp(),
        }
        if detail:
            payload["detail"] = detail
        if duration_ms is not None:
            payload["duration_ms"] = round(duration_ms, 2)
        return StreamEvent(event="status", data=payload)

    @staticmethod
    def _distinct_document_count(chunks: list[RetrievedChunk]) -> int:
        return len({chunk.document_id for chunk in chunks})

    @classmethod
    def _build_query_status_history(
        cls,
        *,
        previous_message_count: int,
        cached: bool,
        search_mode: str,
        top_k: int,
        retrieved_chunks: list[RetrievedChunk],
        citations: list[dict[str, Any]],
        trace: TraceCollector | None,
        answer_text: str,
        followup_items: list[str],
        persisted_blocks: list[dict[str, Any]] | None = None,
        retrieval_duration_ms: float | None = None,
        answer_duration_ms: float | None = None,
    ) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        steps = [
            cls._status_event(
                code="context",
                label="Loading Conversation Context",
                state="completed",
                detail=(
                    f"Loaded {previous_message_count} prior messages"
                    if previous_message_count
                    else "No prior messages in this conversation"
                ),
            ),
            cls._status_event(
                code="retrieval",
                label="Retrieving Evidence",
                state="completed",
                detail=(
                    "Served from cache"
                    if cached
                    else (
                        f"{search_mode} search retrieved {len(retrieved_chunks)} chunks "
                        f"from {cls._distinct_document_count(retrieved_chunks)} documents "
                        + (
                            (
                                f"(adaptive depth "
                                f"{trace.metadata.get('effective_retrieve_top_k', top_k)} / "
                                f"{trace.metadata.get('effective_rerank_top_k', top_k)} / "
                                f"{trace.metadata.get('effective_answer_top_k', top_k)})"
                            )
                            if trace is not None
                            else f"(top_k {top_k})"
                        )
                    )
                ),
                duration_ms=retrieval_duration_ms,
            ),
            cls._status_event(
                code="grounding",
                label="Grounding Answer",
                state="completed",
                detail=(
                    f"Prepared {len(citations)} citations from {len(retrieved_chunks)} retrieved chunks"
                ),
            ),
        ]
        if trace is not None:
            trace_data = trace.to_dict()
            rerank_suffix = ""
            if trace.metadata.get("reranking_applied") and isinstance(
                trace.metadata.get("reranker_model"), str
            ):
                rerank_suffix = f" · reranked with {trace.metadata['reranker_model']}"
            depth_suffix = ""
            if (
                trace.metadata.get("retrieval_depth_mode") == "adaptive"
                and isinstance(trace.metadata.get("effective_retrieve_top_k"), int)
                and isinstance(trace.metadata.get("effective_rerank_top_k"), int)
                and isinstance(trace.metadata.get("effective_answer_top_k"), int)
            ):
                depth_suffix = (
                    " · adaptive depth "
                    f"{trace.metadata['effective_retrieve_top_k']}/"
                    f"{trace.metadata['effective_rerank_top_k']}/"
                    f"{trace.metadata['effective_answer_top_k']}"
                )
            steps.append(
                cls._status_event(
                    code="trace",
                    label="Analytic Reasoning Trace",
                    state="completed",
                    detail=(
                        f"Searched {trace_data['chunks_searched']} chunks, "
                        f"evaluated {trace_data['chunks_evaluated']}, "
                        f"selected {trace_data['chunks_selected']}{rerank_suffix}{depth_suffix}"
                    ),
                )
            )
        steps.append(
            cls._status_event(
                code="synthesis",
                label="Synthesizing Answer",
                state="completed",
                detail=f"Generated {len(answer_text)} characters of answer content",
                duration_ms=answer_duration_ms,
            )
        )
        if persisted_blocks:
            steps.append(
                cls._status_event(
                    code="outputs",
                    label="Rendering Structured Outputs",
                    state="completed",
                    detail=f"Prepared {len(persisted_blocks)} structured output blocks",
                )
            )
        for step in steps:
            history = cls._append_status_history_entry(history, step.data)
        for event in cls._build_followup_events(followup_items):
            if event.event == "status":
                history = cls._append_status_history_entry(history, event.data)
        return history

    @staticmethod
    def _extract_stream_payload(event_str: str) -> dict[str, Any] | None:
        try:
            data_line = next(
                line for line in event_str.splitlines() if line.startswith("data:")
            )
        except StopIteration:
            return None
        try:
            payload = json.loads(data_line[5:].strip())
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _append_status_history_entry(
        history: list[dict[str, Any]], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        label = str(payload.get("label", "")).strip()
        if not label:
            return history
        duration_value = payload.get("duration_ms")
        entry = {
            "code": (
                str(payload.get("code")).strip()
                if payload.get("code") is not None
                else None
            ),
            "label": label,
            "state": str(payload.get("state") or "running"),
            "detail": (
                str(payload.get("detail")).strip()
                if payload.get("detail") is not None
                else None
            ),
            "timestamp": (
                str(payload.get("timestamp")).strip()
                if payload.get("timestamp") is not None
                else QueryService._status_timestamp()
            ),
            "duration_ms": (
                round(float(duration_value), 2)
                if isinstance(duration_value, int | float)
                else None
            ),
        }
        last = history[-1] if history else None
        if (
            last
            and last.get("code") == entry["code"]
            and last.get("label") == entry["label"]
            and last.get("state") == entry["state"]
            and last.get("detail") == entry["detail"]
        ):
            return history
        return [*history, entry]

    @classmethod
    def _followup_status_history(cls, items: list[str]) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for event in cls._build_followup_events(items):
            if event.event == "status":
                history = cls._append_status_history_entry(history, event.data)
        return history

    @staticmethod
    def _build_output_summary_from_blocks(
        blocks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for index, block in enumerate(blocks):
            block_type = str(block.get("type", "output")).strip() or "output"
            title = str(
                block.get("title")
                or f"{block_type.replace('_', ' ').title()} {index + 1}"
            )
            detail = block.get("description")
            if not isinstance(detail, str) or not detail.strip():
                if block_type == "table":
                    rows = block.get("rows")
                    detail = f"{len(rows)} rows" if isinstance(rows, list) else None
                elif block_type == "chart":
                    series = block.get("series")
                    detail = (
                        f"{len(series)} points" if isinstance(series, list) else None
                    )
                elif block_type == "card":
                    content = block.get("content")
                    detail = (
                        content
                        if isinstance(content, str) and content.strip()
                        else None
                    )
                else:
                    detail = None
            summaries.append(
                {
                    "id": str(block.get("id") or f"output-{index}"),
                    "type": block_type,
                    "title": title,
                    "description": detail,
                }
            )
        return summaries

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        if isinstance(content, StructuredAnswerResponse):
            return json.dumps(content.model_dump(mode="json"), ensure_ascii=False)
        return str(content)

    @staticmethod
    def _answer_to_followup_text(answer: str | StructuredAnswerResponse) -> str:
        if isinstance(answer, StructuredAnswerResponse):
            sections: list[str] = []
            if answer.key_findings:
                sections.append("\n".join(answer.key_findings))
            if answer.detailed_analysis:
                sections.append(answer.detailed_analysis)
            if answer.limitations:
                sections.append(answer.limitations)
            if answer.conclusion:
                sections.append(answer.conclusion)
            return "\n\n".join(
                section.strip() for section in sections if section.strip()
            )
        return str(answer)

    @staticmethod
    def _serialize_answer_for_cache(answer: str | StructuredAnswerResponse) -> Any:
        if isinstance(answer, StructuredAnswerResponse):
            return answer.model_dump(mode="json")
        return answer

    @staticmethod
    def _answer_to_storage_text(answer: str | StructuredAnswerResponse) -> str:
        if isinstance(answer, StructuredAnswerResponse):
            return json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
        return str(answer)

    def _maybe_commit(self) -> None:
        if self.settings.env == "test":
            self.db.flush()
        else:
            self.db.commit()

    @staticmethod
    def _resolve_trace_id() -> str:
        return get_trace_id() or f"trc_{generate_uuid7_with_fallback()}"

    def _validate_top_k(self, top_k: int) -> None:
        if (
            top_k < self.settings.query_top_k_min
            or top_k > self.settings.query_top_k_max
        ):
            raise ApiError(
                code="TOP_K_OUT_OF_RANGE",
                message="top_k is outside allowed bounds.",
                status_code=400,
                details={
                    "min": self.settings.query_top_k_min,
                    "max": self.settings.query_top_k_max,
                },
            )

    @staticmethod
    def normalize_query(query_text: str) -> str:
        return " ".join(query_text.strip().split()).lower()

    @staticmethod
    def normalize_filters(filters: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any], json.loads(json.dumps(filters, sort_keys=True, default=str))
        )

    @staticmethod
    def build_cache_key(
        *,
        tenant_id: uuid.UUID,
        normalized_query: str,
        normalized_filters: dict[str, Any],
        top_k: int,
        embedding_provider: str,
        embedding_model: str,
        search_mode: str = "hybrid",
    ) -> str:
        payload = {
            "tenant_id": str(tenant_id),
            "query": normalized_query,
            "filters": normalized_filters,
            "top_k": top_k,
            "embedding_provider": embedding_provider,
            "embedding_model": embedding_model,
            "search_mode": search_mode,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"query_cache:{digest}"
