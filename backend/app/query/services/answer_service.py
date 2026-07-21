from __future__ import annotations

import hashlib
import importlib
import ipaddress
import json
import logging
import re
import threading
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Final
from urllib.parse import urlparse
from uuid import UUID

from app.core.brand import APP_ASSISTANT_NAME, APP_BRAND_NAME, APP_ENGINE_NAME
from app.core.config import LOCAL_LLM_PROVIDERS, Settings
from app.query.schemas.followups import FollowupSuggestions
from app.query.schemas.structured_response import (
    StructuredAnswerResponse,
    StructuredChartResponse,
    StructuredDiagramResponse,
    StructuredTableResponse,
    is_valid_mermaid_syntax,
    sanitize_mermaid_syntax,
)
from app.providers.services import (
    ChatGenerateRequest,
    ProviderRegistry,
    ProviderSelectionCandidate,
)
from app.providers.services.base import ProviderRequestError
from app.query.services.prompt_templates import PromptTemplates
from app.query.services.query_classifier import QueryType
from app.query.services.retrieval_service import RetrievedChunk
from app.query.services.snippet_service import SnippetService
from app.system.services.cache_service import get_redis_client
from app.system.services.metrics_service import (
    LLM_PROVIDER_LATENCY_SECONDS,
)

logger = logging.getLogger(__name__)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017

STREAM_EVENT_DELTA: Final[str] = "delta"
STREAM_EVENT_THINKING: Final[str] = "thinking"
STREAM_EVENT_REPLACE: Final[str] = "replace"
STREAM_EVENT_TABLE: Final[str] = "table"
STREAM_EVENT_CHART: Final[str] = "chart"
STREAM_EVENT_CARD: Final[str] = "card"
STREAM_EVENT_DIAGRAM: Final[str] = "diagram"
STREAM_EVENT_FOLLOWUPS: Final[str] = "followups"
STREAM_EVENT_DONE: Final[str] = "done"
STREAM_EVENT_ERROR: Final[str] = "error"

STREAM_BUFFER_MAX_CHARS: Final[int] = 1
STREAM_BUFFER_FLUSH_PUNCTUATION: Final[tuple[str, ...]] = (
    " ",
    "\n",
    ".",
    "!",
    "?",
    ":",
    "|",
    ",",
)
STREAM_PREFILL_READ_TIMEOUT_SECONDS: Final[float] = 300.0
MAX_PROMPT_CONTEXT_CHUNKS: Final[int] = 12
MAX_PROMPT_CONTEXT_SNIPPET_CHARS: Final[int] = 1500
MAX_LOCAL_SNIPPET_COUNT: Final[int] = 3
MAX_STREAM_HISTORY_MESSAGES: Final[int] = 12

_ARCHITECTURE_QUERY_RE = re.compile(
    r"\b(architecture|architectural|workflow|process|pipeline|sequence|diagram|flow|logic|topology|hierarchy|structure)\b",
    re.IGNORECASE,
)
_CHART_QUERY_RE = re.compile(
    r"\b(chart|graph|plot|trend|trajectory|timeline|growth|decline|distribution|breakdown|comparison|metrics|projection|percentage|revenue|share)\b",
    re.IGNORECASE,
)
_GRAPH_CANVAS_QUERY_RE = re.compile(
    r"\b(graph|topology|node|edge|network|dependency|relationship map|system map|canvas|knowledge graph)\b",
    re.IGNORECASE,
)
_FOLLOWUP_NOISY_QUERY_RE = re.compile(
    r"(parse error|expecting\b|```|-->|::=|\[[^\]]*\]|\{[^}]*\}|[;<>]{2,}|got\s+['\"])",
    re.IGNORECASE,
)
_FOLLOWUP_DIRECTIVE_PREFIX_RE = re.compile(
    r"^(?:please\s+)?(?:can you\s+)?"
    r"(?:explain|summarize|compare|show|give|list|analyze|describe|fix|correct|rewrite|generate|create|provide)\s+",
    re.IGNORECASE,
)
_OPEN_CHAT_CODE_QUERY_RE = re.compile(
    r"\b(code|html|css|javascript|typescript|python|java|sql|bash|shell|script|function|class|component|api)\b",
    re.IGNORECASE,
)


def _unwrap_structured_json_candidate(text: str) -> str:
    candidate = text.strip()
    fenced = re.match(
        r"^```(?:json)?\s*([\s\S]*?)\s*```$", candidate, flags=re.IGNORECASE
    )
    if fenced:
        return fenced.group(1).strip()
    prefixed = re.match(
        r"^(?:json|copy)\s*```(?:json)?\s*([\s\S]*?)\s*```$",
        candidate,
        flags=re.IGNORECASE,
    )
    if prefixed:
        return prefixed.group(1).strip()
    return candidate


def _salvage_loose_chart_payload(
    chart: Any, confidence_score: float
) -> StructuredChartResponse | None:
    if not isinstance(chart, dict):
        return None

    raw_type = str(chart.get("chart_type", "") or "").strip().lower()
    chart_type = (
        raw_type if raw_type in {"line", "bar", "pie", "area", "scatter"} else "bar"
    )
    extracted: list[dict[str, float | str]] = []

    def push_point(point: Any) -> None:
        if not isinstance(point, dict):
            return
        label = point.get("label", point.get("name", point.get("x")))
        raw_value = point.get("value", point.get("y", point.get("val")))
        if not isinstance(label, str | int | float):
            return
        if isinstance(raw_value, int | float):
            value = float(raw_value)
        elif isinstance(raw_value, str) and raw_value.strip():
            try:
                value = float(raw_value.replace(",", "").rstrip("%"))
            except ValueError:
                return
        else:
            return
        extracted.append({"label": str(label), "value": value})

    for item in chart.get("series", []):
        if not isinstance(item, dict):
            continue
        nested = item.get("data")
        if isinstance(nested, list):
            for point in nested:
                push_point(point)
            continue
        push_point(item)

    if len(extracted) < 2 and isinstance(chart.get("data"), list):
        for point in chart["data"]:
            push_point(point)

    if len(extracted) < 2:
        return None

    try:
        return StructuredChartResponse.model_validate(
            {
                "title": str(chart.get("title", "") or "Chart Data"),
                "chart_type": chart_type,
                "series": extracted,
            }
        )
    except Exception:
        return None


class RetryableLlmError(Exception):
    """Raised for transient LLM/provider failures."""


class NonRetryableLlmError(Exception):
    """Raised for hard LLM/provider failures."""


# Backward-compatible alias retained for older tests and call sites.
RetryError = RetryableLlmError


@dataclass(slots=True)
class LlmCircuitState:
    failures: int = 0
    opened_until: datetime | None = None


@dataclass(slots=True)
class _InMemoryCounterState:
    requests: dict[str, tuple[int, float]]
    cost_micros: dict[str, int]

    def __init__(self) -> None:
        self.requests = {}
        self.cost_micros = {}


@dataclass(slots=True, frozen=True)
class AnswerCitation:
    document_id: str
    chunk_id: str
    filename: str
    snippet: str
    similarity_score: float
    source_type: str = "text"
    section_header: str | None = None
    page_number: int | None = None


@dataclass(slots=True)
class AnswerResult:
    answer: str | StructuredAnswerResponse
    confidence: float
    citations: list[AnswerCitation]
    usage: dict[str, int] | None = None
    provider_type: str | None = None
    model_name: str | None = None
    provider_source: str | None = None
    fallback_used: bool = False


@dataclass(slots=True, frozen=True)
class StreamRenderHints:
    has_table_markdown: bool = False
    has_code_block: bool = False
    has_chart_hint: bool = False
    has_bullets: bool = False
    query_type: str = "factual"


@dataclass(slots=True, frozen=True)
class StreamEvent:
    event: str
    data: dict[str, Any] = field(default_factory=dict)
    # Optional sequence metadata is retained for generic stream consumers.
    sequence: int | None = None


class AnswerService:
    _llm_circuit = LlmCircuitState()
    _limit_state = _InMemoryCounterState()
    _limit_lock = threading.Lock()

    def __init__(
        self, no_result_answer_text: str, settings: Settings | None = None
    ) -> None:
        self.no_result_answer_text = no_result_answer_text
        self.settings = settings

    @staticmethod
    def _build_open_chat_fallback_answer(query_text: str) -> str:
        normalized_query = query_text.strip()
        if normalized_query:
            return (
                "I could not get a live model response for that request just now.\n\n"
                "Please retry in a moment. If it keeps happening, switch the selected model or provider and try again."
            )
        return (
            "I could not get a live model response just now.\n\n"
            "Please retry in a moment. If it keeps happening, switch the selected model or provider and try again."
        )

    # ---------------------------------------------------------------------
    # Public sync API
    # ---------------------------------------------------------------------

    def synthesize(
        self,
        *,
        retrieved_chunks: list[RetrievedChunk],
        query_text: str | None = None,
        tenant_id: UUID | None = None,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
    ) -> AnswerResult:
        ranked = self._rank_chunks(retrieved_chunks)
        confidence = self._calculate_confidence(ranked)
        citations = self._build_citations(ranked)
        local_answer = self._build_local_fallback_answer(ranked)

        answer: str | StructuredAnswerResponse = (
            local_answer or self.no_result_answer_text
        )

        if (
            self._llm_generation_enabled(provider_candidates=provider_candidates)
            and query_text is not None
            and tenant_id is not None
        ):
            context_str = self._build_prompt_context(ranked[:MAX_PROMPT_CONTEXT_CHUNKS])
            estimated_input_tokens = self._estimate_tokens(
                self._build_llm_messages(
                    query_text,
                    context_str,
                    previous_messages,
                    query_type,
                )[0]["content"]
                + context_str
                + query_text
            )

            if not self._allow_llm_usage(
                tenant_id=tenant_id,
                estimated_input_tokens=estimated_input_tokens,
                provider_candidates=provider_candidates,
            ):
                logger.info(
                    "LLM usage denied by budget/rate guard.",
                    extra={"tenant_id": str(tenant_id)},
                )
                return AnswerResult(
                    answer=answer,
                    confidence=round(confidence, 6),
                    citations=citations,
                    usage={},
                )

            if self._llm_is_circuit_open():
                logger.info("LLM circuit open; using fallback answer.")
                return AnswerResult(
                    answer=answer,
                    confidence=round(confidence, 6),
                    citations=citations,
                    usage={},
                    fallback_used=True,
                )

            candidates = provider_candidates or [self._env_provider_candidate()]
            last_retryable = False
            for index, candidate in enumerate(candidates):
                try:
                    content, usage = self._call_llm_with_retry(
                        query_text=query_text,
                        context=context_str,
                        previous_messages=previous_messages,
                        query_type=query_type,
                        provider_override=candidate,
                    )
                    structured = self._try_parse_structured_answer(content)
                    resolved_answer: str | StructuredAnswerResponse
                    if structured is not None:
                        structured.confidence_score = round(confidence, 6)
                        resolved_answer = structured
                    else:
                        fallback_structured = StructuredAnswerResponse.fallback(content)
                        fallback_structured.confidence_score = round(confidence, 6)
                        resolved_answer = fallback_structured
                    self._record_llm_success()
                    return AnswerResult(
                        answer=resolved_answer,
                        confidence=round(confidence, 6),
                        citations=citations,
                        usage=usage,
                        provider_type=candidate.provider_type,
                        model_name=candidate.model_name,
                        provider_source=candidate.source,
                        fallback_used=index > 0,
                    )
                except RetryableLlmError:
                    last_retryable = True
                    continue
                except NonRetryableLlmError:
                    logger.info(
                        "Non-retryable LLM failure; trying next provider candidate if any."
                    )
                    continue
            if last_retryable:
                self._record_llm_failure()

        if isinstance(answer, StructuredAnswerResponse):
            answer.confidence_score = round(confidence, 6)

        return AnswerResult(
            answer=answer,
            confidence=round(confidence, 6),
            citations=citations,
            usage={},
            fallback_used=False,
        )

    def generate_followups(
        self,
        *,
        query_text: str,
        answer_text: str,
        tenant_id: UUID,
        previous_messages: list[dict[str, str]] | None = None,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
    ) -> list[str]:
        structured = self._try_parse_structured_answer(answer_text)
        if structured is not None and structured.follow_up_suggestions:
            sanitized = self._sanitize_followup_candidates(
                structured.follow_up_suggestions, query_text=query_text
            )
            if sanitized:
                return sanitized
        extracted = self._extract_markdown_suggestions(answer_text)
        if extracted:
            sanitized = self._sanitize_followup_candidates(
                extracted, query_text=query_text
            )
            if sanitized:
                return sanitized
        extracted = self._extract_followups_from_text(answer_text)
        if extracted:
            sanitized = self._sanitize_followup_candidates(
                extracted, query_text=query_text
            )
            if sanitized:
                return sanitized
        return self._fallback_followups(query_text=query_text, answer_text=answer_text)

    @staticmethod
    def _extract_followups_from_text(content: str) -> list[str]:
        items: list[str] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line = re.sub(r"^[-*]\s+", "", line)
            line = re.sub(r"^\d+[.)]\s+", "", line)
            if len(line) < 8:
                continue
            if not line.endswith("?"):
                continue
            items.append(line)
            if len(items) == 3:
                break
        return items

    @staticmethod
    def _fallback_followups(*, query_text: str, answer_text: str) -> list[str]:
        answer = answer_text.strip()
        subject = AnswerService._followup_subject_from_query(query_text)
        if AnswerService._looks_like_syntax_or_diagram_issue(query_text, answer_text):
            suggestions = [
                "Can you show the corrected version step by step?",
                "What is the exact syntax error causing this failure?",
                "Can you explain the fix in simpler terms?",
            ]
        else:
            suggestions = [
                (
                    f"Can you explain {subject} in more detail?"
                    if subject
                    else "Can you explain this more clearly?"
                ),
                "What is the most important takeaway here?",
                "Can you show the exact evidence from the documents?",
            ]
        if answer:
            lowered = answer.lower()
            if "compare" in lowered or "difference" in lowered:
                suggestions[1] = "Can you compare the main differences more clearly?"
            elif "step" in lowered or "process" in lowered:
                suggestions[1] = "Can you break this down step by step?"
            elif "summary" in lowered or "overview" in lowered:
                suggestions[1] = "Can you expand the summary with more detail?"
        return FollowupSuggestions(follow_ups=suggestions).follow_ups

    @staticmethod
    def _followup_subject_from_query(query_text: str) -> str | None:
        query = re.sub(r"\s+", " ", query_text.strip())
        query = query.strip("`\"'").rstrip("?.! ")
        if not query:
            return None
        if (
            len(query) > 80
            or "\n" in query_text
            or _FOLLOWUP_NOISY_QUERY_RE.search(query)
        ):
            return None

        subject = _FOLLOWUP_DIRECTIVE_PREFIX_RE.sub("", query).strip()
        subject = re.sub(r"^(?:me\s+)?(?:the\s+)?", "", subject, flags=re.IGNORECASE)
        subject = subject[:1].lower() + subject[1:] if subject else ""
        word_count = len(subject.split())
        if not subject or word_count < 2 or word_count > 10:
            return None
        return subject

    @staticmethod
    def _looks_like_syntax_or_diagram_issue(query_text: str, answer_text: str) -> bool:
        haystack = f"{query_text}\n{answer_text}".lower()
        return any(
            token in haystack
            for token in (
                "parse error",
                "syntax error",
                "mermaid",
                "diagram",
                "flowchart",
                "graph lr",
                "graph td",
                "expecting",
            )
        )

    @staticmethod
    def _sanitize_followup_candidates(
        items: list[str], *, query_text: str
    ) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for item in items:
            normalized = " ".join(item.split()).strip()
            if not normalized:
                continue
            if len(normalized) > 160:
                continue
            if AnswerService._should_drop_followup_candidate(
                normalized, query_text=query_text
            ):
                continue

            dedupe_key = normalized.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            cleaned.append(normalized)
            if len(cleaned) == 3:
                break

        return FollowupSuggestions(follow_ups=cleaned).follow_ups

    @staticmethod
    def _should_drop_followup_candidate(item: str, *, query_text: str) -> bool:
        if _FOLLOWUP_NOISY_QUERY_RE.search(item):
            return True

        query = " ".join(query_text.split()).strip().casefold()
        if not query:
            return False

        core = AnswerService._followup_core_text(item)
        if len(core) >= 24 and core in query:
            return True

        return False

    @staticmethod
    def _followup_core_text(item: str) -> str:
        normalized = item.strip().casefold()
        patterns = (
            (
                r"^can you explain\s+(.+?)\s+in more detail\?$",
                1,
            ),
            (
                r"^can you explain\s+(.+?)\s+more clearly\?$",
                1,
            ),
            (
                r"^can you show\s+(.+?)\??$",
                1,
            ),
            (
                r"^can you fix\s+(.+?)\??$",
                1,
            ),
        )
        for pattern, group in patterns:
            match = re.match(pattern, normalized)
            if match:
                return match.group(group).strip()
        return normalized

    # ---------------------------------------------------------------------
    # Public streaming APIs
    # ---------------------------------------------------------------------

    def stream_synthesize(
        self,
        *,
        retrieved_chunks: list[RetrievedChunk],
        query_text: str | None = None,
        tenant_id: UUID | None = None,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> Iterator[str]:
        """
        Compatibility path:
        yields plain text chunks only, suitable for older consumers.
        """
        for event in self.stream_synthesize_events(
            retrieved_chunks=retrieved_chunks,
            query_text=query_text,
            tenant_id=tenant_id,
            previous_messages=previous_messages,
            query_type=query_type,
            provider_candidates=provider_candidates,
            response_directive=response_directive,
            temperature_override=temperature_override,
            thinking_enabled=thinking_enabled,
        ):
            if event.event == STREAM_EVENT_DELTA:
                text = str(event.data.get("text", ""))
                if text:
                    yield text

    def stream_synthesize_events(
        self,
        *,
        retrieved_chunks: list[RetrievedChunk],
        query_text: str | None = None,
        tenant_id: UUID | None = None,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> Iterator[StreamEvent]:
        """
        Rich streaming path:
        emits structured events for premium chat UIs / SSE adapters.
        """
        ranked = self._rank_chunks(retrieved_chunks)

        if (
            not self._llm_generation_enabled(provider_candidates=provider_candidates)
            or query_text is None
            or tenant_id is None
        ):
            yield StreamEvent(
                event=STREAM_EVENT_ERROR,
                data=self._build_provider_failure_event_data(
                    code="STREAM_LLM_UNAVAILABLE",
                    message="No chat model is configured for live answers.",
                    provider_candidate=None,
                    fallback_used=False,
                    reason="chat generation is disabled or unavailable",
                ),
            )
            return

        if self._llm_is_circuit_open():
            logger.info("LLM circuit open during streaming.")
            fallback_text = (
                self._build_local_fallback_answer(ranked) or self.no_result_answer_text
            )
            yield from self._emit_buffered_text_with_events(fallback_text, query_type)
            return

        context_str = self._build_prompt_context(ranked[:MAX_PROMPT_CONTEXT_CHUNKS])
        estimated_input_tokens = self._estimate_tokens(
            self._build_llm_messages(
                query_text,
                context_str,
                previous_messages,
                query_type,
                structured_output=False,
                response_directive=response_directive,
            )[0]["content"]
            + context_str
            + query_text
        )

        if not self._allow_llm_usage(
            tenant_id=tenant_id,
            estimated_input_tokens=estimated_input_tokens,
            provider_candidates=provider_candidates,
        ):
            logger.info(
                "Streaming LLM usage denied by budget/rate guard.",
                extra={"tenant_id": str(tenant_id)},
            )
            fallback_text = (
                self._build_local_fallback_answer(ranked) or self.no_result_answer_text
            )
            yield from self._emit_buffered_text_with_events(fallback_text, query_type)
            return

        candidates = provider_candidates or [self._env_provider_candidate()]
        failed_candidate: ProviderSelectionCandidate | None = None
        try:
            full_text = ""
            for candidate in candidates:
                emitted_any = False
                try:
                    for chunk in self._stream_provider_text(
                        query_text=query_text,
                        context=context_str,
                        previous_messages=previous_messages,
                        query_type=query_type,
                        provider_override=candidate,
                        structured_output=False,
                        response_directive=response_directive,
                        temperature_override=temperature_override,
                        thinking_enabled=thinking_enabled,
                    ):
                        if chunk:
                            emitted_any = True
                            full_text += chunk
                            yield StreamEvent(
                                event=STREAM_EVENT_DELTA, data={"text": chunk}
                            )
                    break
                except (RetryableLlmError, NonRetryableLlmError):
                    failed_candidate = candidate
                    if emitted_any or candidate is candidates[-1]:
                        raise
                    continue

            if not full_text.strip():
                yield StreamEvent(
                    event=STREAM_EVENT_ERROR,
                    data=self._build_provider_failure_event_data(
                        code="STREAM_EMPTY_PROVIDER_RESPONSE",
                        message="The chat model did not return an answer.",
                        provider_candidate=failed_candidate,
                        fallback_used=False,
                        reason="provider returned an empty streamed response",
                    ),
                )
                return

            self._record_llm_success()
            yield from self._emit_post_stream_events(
                full_text, query_type, emit_done=True
            )
        except RetryableLlmError as exc:
            self._record_llm_failure()
            yield StreamEvent(
                event=STREAM_EVENT_ERROR,
                data=self._build_provider_failure_event_data(
                    code="STREAM_RETRYABLE_FAILURE",
                    message="Streaming interrupted; using fallback answer.",
                    provider_candidate=failed_candidate,
                    fallback_used=False,
                    reason=str(exc),
                ),
            )
        except NonRetryableLlmError as exc:
            yield StreamEvent(
                event=STREAM_EVENT_ERROR,
                data=self._build_provider_failure_event_data(
                    code="STREAM_PROVIDER_FAILURE",
                    message="The chat model failed to answer. Check the provider and selected model.",
                    provider_candidate=failed_candidate,
                    fallback_used=False,
                    reason=str(exc),
                ),
            )

    async def stream_synthesize_events_async(
        self,
        *,
        retrieved_chunks: list[RetrievedChunk],
        query_text: str | None = None,
        tenant_id: UUID | None = None,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        """
        Async rich streaming path used by the FastAPI SSE runtime.
        Emits text deltas immediately and progressively surfaces structured blocks
        as soon as they can be derived from the accumulated content.
        """
        ranked = self._rank_chunks(retrieved_chunks)

        if (
            not self._llm_generation_enabled(provider_candidates=provider_candidates)
            or query_text is None
            or tenant_id is None
        ):
            yield StreamEvent(
                event=STREAM_EVENT_ERROR,
                data=self._build_provider_failure_event_data(
                    code="STREAM_LLM_UNAVAILABLE",
                    message="No chat model is configured for live answers.",
                    provider_candidate=None,
                    fallback_used=False,
                    reason="chat generation is disabled or unavailable",
                ),
            )
            return

        if self._llm_is_circuit_open():
            logger.info("LLM circuit open during async streaming.")
            fallback_text = (
                self._build_local_fallback_answer(ranked) or self.no_result_answer_text
            )
            for event in self._emit_buffered_text_with_events(
                fallback_text, query_type
            ):
                yield event
            return

        context_str = self._build_prompt_context(ranked[:MAX_PROMPT_CONTEXT_CHUNKS])
        estimated_input_tokens = self._estimate_tokens(
            self._build_llm_messages(
                query_text,
                context_str,
                previous_messages,
                query_type,
                structured_output=False,
                response_directive=response_directive,
            )[0]["content"]
            + context_str
            + query_text
        )

        if not self._allow_llm_usage(
            tenant_id=tenant_id,
            estimated_input_tokens=estimated_input_tokens,
            provider_candidates=provider_candidates,
        ):
            logger.info(
                "Async streaming LLM usage denied by budget/rate guard.",
                extra={"tenant_id": str(tenant_id)},
            )
            fallback_text = (
                self._build_local_fallback_answer(ranked) or self.no_result_answer_text
            )
            for event in self._emit_buffered_text_with_events(
                fallback_text, query_type
            ):
                yield event
            return

        emitted_payloads: dict[str, dict[str, str]] = {
            "table": {},
            "chart": {},
            "diagram": {},
            "card": {},
        }

        try:
            full_text = ""
            candidates = provider_candidates or [self._env_provider_candidate()]
            failed_candidate: ProviderSelectionCandidate | None = None
            for candidate in candidates:
                emitted_any = False
                try:
                    async for provider_event in self._astream_provider_events(
                        query_text=query_text,
                        context=context_str,
                        previous_messages=previous_messages,
                        query_type=query_type,
                        provider_override=candidate,
                        structured_output=False,
                        response_directive=response_directive,
                        temperature_override=temperature_override,
                        thinking_enabled=thinking_enabled,
                    ):
                        event_type = str(provider_event.get("type", "delta"))
                        chunk = str(provider_event.get("text", ""))
                        if not chunk:
                            continue

                        emitted_any = True
                        if event_type == "thinking":
                            yield StreamEvent(
                                event=STREAM_EVENT_THINKING,
                                data={"text": chunk},
                            )
                            continue
                        full_text += chunk

                        yield StreamEvent(
                            event=STREAM_EVENT_DELTA, data={"text": chunk}
                        )

                        for event in self._emit_progressive_rich_events(
                            full_text=full_text,
                            emitted_payloads=emitted_payloads,
                        ):
                            yield event
                    break
                except (RetryableLlmError, NonRetryableLlmError):
                    failed_candidate = candidate
                    if emitted_any or candidate is candidates[-1]:
                        raise
                    continue

            if not full_text.strip():
                yield StreamEvent(
                    event=STREAM_EVENT_ERROR,
                    data=self._build_provider_failure_event_data(
                        code="STREAM_EMPTY_PROVIDER_RESPONSE",
                        message="The chat model did not return an answer.",
                        provider_candidate=failed_candidate,
                        fallback_used=False,
                        reason="provider returned an empty streamed response",
                    ),
                )
                return

            self._record_llm_success()
            for event in self._emit_post_stream_events(
                full_text,
                query_type,
                emit_done=True,
                emitted_payloads=emitted_payloads,
            ):
                yield event
        except RetryableLlmError as exc:
            self._record_llm_failure()
            yield StreamEvent(
                event=STREAM_EVENT_ERROR,
                data=self._build_provider_failure_event_data(
                    code="STREAM_RETRYABLE_FAILURE",
                    message="Streaming was interrupted before the chat model finished answering.",
                    provider_candidate=failed_candidate,
                    fallback_used=False,
                    reason=str(exc),
                ),
            )
        except NonRetryableLlmError as exc:
            yield StreamEvent(
                event=STREAM_EVENT_ERROR,
                data=self._build_provider_failure_event_data(
                    code="STREAM_PROVIDER_FAILURE",
                    message="The chat model failed to answer. Check the provider and selected model.",
                    provider_candidate=failed_candidate,
                    fallback_used=False,
                    reason=str(exc),
                ),
            )

    async def stream_open_chat_events_async(
        self,
        *,
        query_text: str,
        tenant_id: UUID,
        previous_messages: list[dict[str, str]] | None = None,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        if not self._llm_generation_enabled(provider_candidates=provider_candidates):
            yield StreamEvent(
                event=STREAM_EVENT_ERROR,
                data=self._build_provider_failure_event_data(
                    code="STREAM_LLM_UNAVAILABLE",
                    message="No chat model is configured for DeepSpace chat.",
                    provider_candidate=None,
                    fallback_used=False,
                    reason="chat generation is disabled or unavailable",
                ),
            )
            return

        if self._llm_is_circuit_open():
            for event in self._emit_buffered_text_with_events(
                self._build_open_chat_fallback_answer(query_text),
                QueryType.FACTUAL,
            ):
                yield event
            return

        estimated_input_tokens = self._estimate_tokens(query_text)
        if not self._allow_llm_usage(
            tenant_id=tenant_id,
            estimated_input_tokens=estimated_input_tokens,
            provider_candidates=provider_candidates,
        ):
            for event in self._emit_buffered_text_with_events(
                self._build_open_chat_fallback_answer(query_text),
                QueryType.FACTUAL,
            ):
                yield event
            return

        emitted_payloads: dict[str, dict[str, str]] = {
            "table": {},
            "chart": {},
            "diagram": {},
            "card": {},
        }
        failed_candidate: ProviderSelectionCandidate | None = None
        wants_structured_output = self._open_chat_wants_structured_output(query_text)

        try:
            full_text = ""
            candidates = provider_candidates or [self._env_provider_candidate()]
            for candidate in candidates:
                emitted_any = False
                try:
                    async for provider_event in self._astream_open_chat_provider_events(
                        query_text=query_text,
                        previous_messages=previous_messages,
                        provider_override=candidate,
                        structured_output=wants_structured_output,
                        response_directive=response_directive,
                        temperature_override=temperature_override,
                        thinking_enabled=thinking_enabled,
                    ):
                        event_type = str(provider_event.get("type", "delta"))
                        chunk = str(provider_event.get("text", ""))
                        if not chunk:
                            continue
                        emitted_any = True
                        if event_type == "thinking":
                            yield StreamEvent(
                                event=STREAM_EVENT_THINKING, data={"text": chunk}
                            )
                            continue
                        full_text += chunk
                        yield StreamEvent(
                            event=STREAM_EVENT_DELTA, data={"text": chunk}
                        )
                        for event in self._emit_progressive_rich_events(
                            full_text=full_text,
                            emitted_payloads=emitted_payloads,
                        ):
                            yield event
                    break
                except (RetryableLlmError, NonRetryableLlmError):
                    failed_candidate = candidate
                    if emitted_any or candidate is candidates[-1]:
                        raise
                    continue

            if not full_text.strip():
                logger.warning(
                    "Open chat provider returned an empty streamed response; falling back.",
                    extra={
                        "provider_type": (
                            failed_candidate.provider_type if failed_candidate else None
                        ),
                        "model_name": (
                            failed_candidate.model_name if failed_candidate else None
                        ),
                    },
                )
                for event in self._emit_buffered_text_with_events(
                    self._build_open_chat_fallback_answer(query_text),
                    QueryType.FACTUAL,
                ):
                    yield event
                return

            self._record_llm_success()
            for event in self._emit_post_stream_events(
                full_text,
                QueryType.FACTUAL,
                emit_done=True,
                emitted_payloads=emitted_payloads,
            ):
                yield event
        except RetryableLlmError:
            self._record_llm_failure()
            logger.warning(
                "Open chat retryable provider failure; falling back.", exc_info=True
            )
            for event in self._emit_buffered_text_with_events(
                self._build_open_chat_fallback_answer(query_text),
                QueryType.FACTUAL,
            ):
                yield event
        except NonRetryableLlmError:
            logger.warning(
                "Open chat non-retryable provider failure; falling back.", exc_info=True
            )
            for event in self._emit_buffered_text_with_events(
                self._build_open_chat_fallback_answer(query_text),
                QueryType.FACTUAL,
            ):
                yield event

    def _stream_generate_with_provider(
        self,
        *,
        tenant_id: UUID,
        query_text: str,
        ranked_chunks: list[RetrievedChunk],
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
    ) -> Iterator[str]:
        """
        Backward-compatible plain-text wrapper around the richer streaming API.
        """
        local_answer = (
            self._build_local_fallback_answer(ranked_chunks)
            or self.no_result_answer_text
        )

        if self._llm_is_circuit_open():
            yield f"Circuit Open: {local_answer}"
            return

        yielded = False
        for chunk in self.stream_synthesize(
            retrieved_chunks=ranked_chunks,
            query_text=query_text,
            tenant_id=tenant_id,
            previous_messages=previous_messages,
            query_type=query_type,
        ):
            yielded = True
            yield chunk

        if not yielded:
            yield local_answer

    # ---------------------------------------------------------------------
    # Public SSE adapter
    # ---------------------------------------------------------------------

    @staticmethod
    def encode_sse_event(event: StreamEvent) -> str:
        """
        Convert a StreamEvent into an SSE-ready string.
        """
        payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
        sequence = f"id: {event.sequence}\n" if event.sequence is not None else ""
        return f"{sequence}event: {event.event}\ndata: {payload}\n\n"

    # ---------------------------------------------------------------------
    # Internal helpers: rendering / fallback
    # ---------------------------------------------------------------------

    def _emit_buffered_text_with_events(
        self,
        text: str,
        query_type: QueryType,
        *,
        suppress_done: bool = False,
        suppress_replace: bool = False,
    ) -> Iterator[StreamEvent]:
        for chunk in self._buffer_text_for_stream(text):
            yield StreamEvent(event=STREAM_EVENT_DELTA, data={"text": chunk})

        yield from self._emit_post_stream_events(
            text,
            query_type,
            emit_done=not suppress_done,
            emit_replace=not suppress_replace,
        )

    def _emit_post_stream_events(
        self,
        text: str,
        query_type: QueryType,
        *,
        emit_done: bool = True,
        emit_replace: bool = True,
        emitted_payloads: dict[str, dict[str, str]] | None = None,
    ) -> Iterator[StreamEvent]:
        structured = self._try_parse_structured_answer(text)
        final_content = (
            self._structured_answer_to_markdown(structured)
            if structured is not None
            else self._strip_markdown_metadata(text)
        )

        if emit_replace:
            yield StreamEvent(
                event=STREAM_EVENT_REPLACE,
                data={
                    "content": final_content,
                    "format": "structured" if structured is not None else "markdown",
                    "structured": (
                        structured.model_dump(mode="json")
                        if structured is not None
                        else None
                    ),
                },
            )

        table_payloads = (
            [self._build_table_payload(structured.comparison_table, index=1)]
            if structured is not None and structured.comparison_table is not None
            else []
        )
        for table_payload in table_payloads:
            if not self._should_emit_payload(emitted_payloads, "table", table_payload):
                continue
            yield StreamEvent(event=STREAM_EVENT_TABLE, data=table_payload)

        chart_payloads = (
            [self._build_chart_payload(structured.chart, index=1)]
            if structured is not None and structured.chart is not None
            else self._extract_chart_payloads(final_content)
        )
        for chart_payload in chart_payloads:
            if not self._should_emit_payload(emitted_payloads, "chart", chart_payload):
                continue
            yield StreamEvent(event=STREAM_EVENT_CHART, data=chart_payload)

        diagram_payloads = (
            [self._build_diagram_payload(structured.diagram, index=1)]
            if structured is not None and structured.diagram is not None
            else self._extract_diagram_payloads(final_content)
        )
        for diagram_payload in diagram_payloads:
            if not self._should_emit_payload(
                emitted_payloads, "diagram", diagram_payload
            ):
                continue
            yield StreamEvent(event=STREAM_EVENT_DIAGRAM, data=diagram_payload)

        followups = (
            structured.follow_up_suggestions
            if structured is not None
            else self._extract_markdown_suggestions(text)
        )
        if followups:
            yield StreamEvent(event=STREAM_EVENT_FOLLOWUPS, data={"items": followups})

        if emit_done:
            yield StreamEvent(event=STREAM_EVENT_DONE, data={"completed": True})

    @staticmethod
    def _buffer_text_for_stream(text: str) -> Iterator[str]:
        """
        Buffer fallback text into smaller semantic chunks.
        This is still fallback-mode streaming, but it should not stall on long sentences
        or cut through words unnecessarily.
        """
        if not text:
            return

        tokens = re.findall(r"\S+\s*|\n", text)
        buffer: list[str] = []
        current_len = 0

        for token in tokens:
            token_len = len(token)
            if (
                buffer
                and current_len + token_len > STREAM_BUFFER_MAX_CHARS
                and not token.endswith(tuple(STREAM_BUFFER_FLUSH_PUNCTUATION))
            ):
                chunk = "".join(buffer).strip()
                if chunk:
                    yield chunk
                buffer = []
                current_len = 0

            buffer.append(token)
            current_len += token_len

            if (
                token.rstrip().endswith(STREAM_BUFFER_FLUSH_PUNCTUATION)
                or current_len >= STREAM_BUFFER_MAX_CHARS
            ):
                chunk = "".join(buffer).strip()
                if chunk:
                    yield chunk
                buffer = []
                current_len = 0

        if buffer:
            chunk = "".join(buffer).strip()
            if chunk:
                yield chunk

    @staticmethod
    def _build_render_hints(text: str, query_type: QueryType) -> StreamRenderHints:
        lowered = text.lower()
        return StreamRenderHints(
            has_table_markdown="|" in text and "---" in text,
            has_code_block="```" in text,
            has_chart_hint=("chart data" in lowered)
            or ("graph" in lowered)
            or ("plot" in lowered),
            has_bullets=("\n-" in text) or ("\n*" in text) or ("\n1." in text),
            query_type=(
                query_type.value if hasattr(query_type, "value") else str(query_type)
            ),
        )

    @staticmethod
    def _try_parse_structured_answer(text: str) -> StructuredAnswerResponse | None:
        if not text:
            return None
        candidate = _unwrap_structured_json_candidate(text)
        if not candidate.startswith("{"):
            return None
        try:
            return StructuredAnswerResponse.model_validate_json(candidate)
        except Exception:  # noqa: BLE001
            return AnswerService._salvage_structured_answer(candidate)

    @staticmethod
    def _salvage_structured_answer(candidate: str) -> StructuredAnswerResponse | None:
        try:
            parsed = json.loads(candidate)
        except Exception:  # noqa: BLE001
            return None

        if not isinstance(parsed, dict):
            return None

        payload: dict[str, Any] = {
            "key_findings": (
                [
                    str(item).strip()
                    for item in parsed.get("key_findings", [])
                    if str(item).strip()
                ]
                if isinstance(parsed.get("key_findings"), list)
                else []
            ),
            "detailed_analysis": str(parsed.get("detailed_analysis", "") or ""),
            "limitations": str(parsed.get("limitations", "") or ""),
            "conclusion": str(parsed.get("conclusion", "") or ""),
            "confidence_score": float(parsed.get("confidence_score", 0.0) or 0.0),
            "follow_up_suggestions": (
                [
                    str(item).strip()
                    for item in parsed.get("follow_up_suggestions", [])
                    if str(item).strip()
                ]
                if isinstance(parsed.get("follow_up_suggestions"), list)
                else []
            ),
        }

        comparison_table = parsed.get("comparison_table")
        if isinstance(comparison_table, dict):
            try:
                payload["comparison_table"] = StructuredTableResponse.model_validate(
                    comparison_table
                )
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Discarding invalid salvaged comparison_table.", exc_info=True
                )

        chart = parsed.get("chart")
        if isinstance(chart, dict):
            try:
                payload["chart"] = StructuredChartResponse.model_validate(chart)
            except Exception:  # noqa: BLE001
                loose_chart = _salvage_loose_chart_payload(
                    chart,
                    payload["confidence_score"],
                )
                if loose_chart is not None:
                    payload["chart"] = loose_chart
                else:
                    logger.debug("Discarding invalid salvaged chart.", exc_info=True)

        diagram = parsed.get("diagram")
        if isinstance(diagram, dict):
            try:
                payload["diagram"] = StructuredDiagramResponse.model_validate(diagram)
            except Exception:  # noqa: BLE001
                logger.debug("Discarding invalid salvaged diagram.", exc_info=True)

        has_structured_signal = any(
            [
                payload["key_findings"],
                payload["detailed_analysis"],
                payload["limitations"],
                payload["conclusion"],
                payload.get("comparison_table"),
                payload.get("chart"),
                payload.get("diagram"),
                payload["follow_up_suggestions"],
            ]
        )
        if not has_structured_signal:
            return None

        try:
            return StructuredAnswerResponse.model_validate(payload)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to salvage structured answer payload.", exc_info=True)
            return None

    @staticmethod
    def _structured_answer_to_markdown(answer: StructuredAnswerResponse) -> str:
        sections: list[str] = []

        # ── Diagram Handling (Absolute TOP) ──
        has_diagram = (
            answer.diagram
            and answer.diagram.source == "mermaid"
            and (answer.diagram.syntax or "").strip()
        )

        analysis_text = answer.detailed_analysis or ""

        if has_diagram:
            syntax = answer.diagram.syntax.strip()
            # Self-heal common LLM syntax errors
            import re

            syntax = re.sub(
                r"^graph\s+(TD|LR|BT|RL)([A-Za-z])",
                r"graph \1\n\2",
                syntax,
                flags=re.MULTILINE,
            )
            syntax = re.sub(r"(subgraph)(\S)", r"\1 \2", syntax, flags=re.MULTILINE)

            # Absolute Top Placement
            sections.append(
                f"### {answer.diagram.title or 'Diagram'}\n\n```mermaid\n{syntax}\n```"
            )

            # STRIP inline duplicates from detailed_analysis to prevent "jumping down"
            # We look for any mermaid code block that matches the core syntax signature
            def get_signature(text: str) -> str:
                return "".join(text.split()).replace('"', "").replace("'", "")

            syntax_sig = get_signature(syntax)

            # Find and remove inline mermaid blocks that match this syntax
            blocks = re.findall(r"```mermaid\s*([\s\S]*?)```", analysis_text)
            for block in blocks:
                if get_signature(block) == syntax_sig:
                    # Remove the block (including fences) from analysis_text
                    # Use a safely escaped version of the block for re.sub
                    escaped_block = re.escape(block.strip())
                    analysis_text = re.sub(
                        rf"```mermaid\s*{escaped_block}\s*```\s*", "", analysis_text
                    )

        if answer.key_findings:
            sections.append(
                "### Key Findings\n"
                + "\n".join(f"- {item}" for item in answer.key_findings)
            )
        if analysis_text.strip():
            sections.append(analysis_text.strip())
        if answer.limitations:
            sections.append(f"### Limitations\n{answer.limitations.strip()}")
        if answer.conclusion:
            sections.append(f"### Conclusion\n{answer.conclusion.strip()}")
        return "\n\n".join(section for section in sections if section).strip()

    @staticmethod
    def _build_table_payload(table: Any, *, index: int) -> dict[str, Any]:
        return {
            "id": f"table-{index}",
            "title": table.title,
            "headers": table.headers,
            "rows": table.rows,
        }

    @staticmethod
    def _build_chart_payload(chart: Any, *, index: int) -> dict[str, Any]:
        return {
            "id": f"chart-{index}",
            "title": chart.title,
            "chart_type": chart.chart_type,
            "series": [point.model_dump(mode="json") for point in chart.series],
        }

    @staticmethod
    def _build_diagram_payload(diagram: Any, *, index: int) -> dict[str, Any]:
        return {
            "id": f"diagram-{index}",
            "title": diagram.title,
            "diagram_type": diagram.diagram_type,
            "source": diagram.source,
            "syntax": diagram.syntax,
            "description": diagram.description,
            "graph": (
                diagram.graph.model_dump(mode="json")
                if getattr(diagram, "graph", None) is not None
                else None
            ),
        }

    def _emit_progressive_rich_events(
        self,
        *,
        full_text: str,
        emitted_payloads: dict[str, dict[str, str]],
    ) -> Iterator[StreamEvent]:
        structured = self._try_parse_structured_answer(full_text)

        table_payloads = (
            [self._build_table_payload(structured.comparison_table, index=1)]
            if structured is not None and structured.comparison_table is not None
            else self._extract_markdown_tables(full_text)
        )
        for table_payload in table_payloads:
            if not self._should_emit_payload(emitted_payloads, "table", table_payload):
                continue
            yield StreamEvent(event=STREAM_EVENT_TABLE, data=table_payload)

        chart_payloads = (
            [self._build_chart_payload(structured.chart, index=1)]
            if structured is not None and structured.chart is not None
            else self._extract_chart_payloads(full_text)
        )
        for chart_payload in chart_payloads:
            if not self._should_emit_payload(emitted_payloads, "chart", chart_payload):
                continue
            yield StreamEvent(event=STREAM_EVENT_CHART, data=chart_payload)

        diagram_payloads = (
            [self._build_diagram_payload(structured.diagram, index=1)]
            if structured is not None and structured.diagram is not None
            else self._extract_diagram_payloads(full_text)
        )
        for diagram_payload in diagram_payloads:
            if not self._should_emit_payload(
                emitted_payloads, "diagram", diagram_payload
            ):
                continue
            yield StreamEvent(event=STREAM_EVENT_DIAGRAM, data=diagram_payload)

    @staticmethod
    def _extract_markdown_tables(text: str) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        lines = text.splitlines()
        i = 0
        while i < len(lines) - 1:
            current = lines[i].strip()
            separator = lines[i + 1].strip()
            if "|" not in current or "|" not in separator:
                i += 1
                continue
            normalized_separator = (
                separator.replace("|", "").replace(":", "").replace("-", "").strip()
            )
            if normalized_separator:
                i += 1
                continue

            headers = [cell.strip() for cell in current.strip("|").split("|")]
            rows: list[list[str]] = []
            i += 2
            while i < len(lines):
                row_line = lines[i].strip()
                if not row_line or "|" not in row_line:
                    break
                rows.append([cell.strip() for cell in row_line.strip("|").split("|")])
                i += 1

            if headers and rows:
                tables.append(
                    {
                        "id": f"table-{len(tables) + 1}",
                        "title": "Comparison Table",
                        "headers": headers,
                        "rows": rows,
                    }
                )
            continue
        return tables

    @staticmethod
    def _extract_chart_payloads(text: str) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        marker = "chart data"
        lowered = text.lower()
        if marker not in lowered:
            return payloads

        section = text[lowered.index(marker) :]
        lines = [line.strip("- *") for line in section.splitlines()[1:] if line.strip()]
        series: list[dict[str, float | str]] = []
        for line in lines:
            if ":" not in line:
                if series:
                    break
                continue
            label, raw_value = line.split(":", 1)
            value_str = raw_value.strip().rstrip("%")
            try:
                value = float(value_str)
            except ValueError:
                continue
            series.append({"label": label.strip(), "value": value})

        if series:
            payloads.append(
                {
                    "id": "chart-1",
                    "title": "Chart Data",
                    "chart_type": "bar",
                    "series": series,
                }
            )
        return payloads

    @staticmethod
    def _extract_diagram_payloads(text: str) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for index, match in enumerate(
            re.finditer(r"```mermaid\s+([\s\S]*?)```", text, flags=re.IGNORECASE),
            start=1,
        ):
            syntax = match.group(1).strip()
            if not syntax:
                continue
            syntax = sanitize_mermaid_syntax(syntax)
            if not is_valid_mermaid_syntax(syntax):
                continue
            payloads.append(
                {
                    "id": f"diagram-{index}",
                    "title": "Generated Diagram",
                    "diagram_type": AnswerService._detect_mermaid_diagram_type(syntax),
                    "source": "mermaid",
                    "syntax": syntax,
                    "description": "",
                    "incomplete": False,
                }
            )
        if payloads:
            return payloads

        incomplete_match = re.search(
            r"```mermaid\s+([\s\S]*)$", text, flags=re.IGNORECASE
        )
        if not incomplete_match:
            return payloads

        syntax = incomplete_match.group(1).strip()
        if not syntax or "```" in syntax:
            return payloads
        syntax = sanitize_mermaid_syntax(syntax)

        payloads.append(
            {
                "id": "diagram-1",
                "title": "Generated Diagram",
                "diagram_type": AnswerService._detect_mermaid_diagram_type(syntax),
                "source": "mermaid",
                "syntax": syntax,
                "description": "",
                "incomplete": True,
            }
        )
        return payloads

    @staticmethod
    def _detect_mermaid_diagram_type(syntax: str) -> str:
        normalized = syntax.lstrip().lower()
        if normalized.startswith("sequencediagram"):
            return "mermaid_sequence"
        if normalized.startswith("statediagram"):
            return "mermaid_state"
        if normalized.startswith("classdiagram"):
            return "mermaid_class"
        if normalized.startswith("erdiagram"):
            return "mermaid_er"
        if normalized.startswith("journey"):
            return "mermaid_journey"
        if normalized.startswith("timeline"):
            return "mermaid_timeline"
        if normalized.startswith("gantt"):
            return "mermaid_gantt"
        if normalized.startswith("mindmap"):
            return "mermaid_mindmap"
        if normalized.startswith("pie"):
            return "mermaid_pie"
        if normalized.startswith("gitgraph"):
            return "mermaid_gitgraph"
        if normalized.startswith("quadrantchart"):
            return "mermaid_quadrant"
        if normalized.startswith("requirementdiagram"):
            return "mermaid_requirement"
        if normalized.startswith("block-beta"):
            return "mermaid_block"
        if normalized.startswith("xychart-beta"):
            return "mermaid_xychart"
        if normalized.startswith("architecture-beta"):
            return "mermaid_architecture"
        if normalized.startswith("sankey"):
            return "mermaid_sankey"
        if normalized.startswith("packet"):
            return "mermaid_packet"
        if normalized.startswith("kanban"):
            return "mermaid_kanban"
        if normalized.startswith(
            ("c4context", "c4container", "c4component", "c4dynamic", "c4deployment")
        ):
            return "mermaid_c4"
        return "mermaid_flowchart"

    @staticmethod
    def _payload_signature(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _should_emit_payload(
        cls,
        emitted_payloads: dict[str, dict[str, str]] | None,
        payload_type: str,
        payload: dict[str, Any],
    ) -> bool:
        if emitted_payloads is None:
            return True

        payload_id = str(payload["id"])
        signature = cls._payload_signature(payload)
        previous_signature = emitted_payloads[payload_type].get(payload_id)
        if previous_signature == signature:
            return False
        emitted_payloads[payload_type][payload_id] = signature
        return True

    def _build_local_fallback_answer(self, ranked: list[RetrievedChunk]) -> str:
        top = ranked[:MAX_LOCAL_SNIPPET_COUNT]
        answer_snippets = [SnippetService.clean(item.content, 200) for item in top]
        return " ".join(snippet for snippet in answer_snippets if snippet)

    @staticmethod
    def _rank_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return sorted(chunks, key=lambda item: item.similarity_score, reverse=True)

    @staticmethod
    def _build_citations(ranked: list[RetrievedChunk]) -> list[AnswerCitation]:
        citations: list[AnswerCitation] = []
        for item in ranked:
            citations.append(
                AnswerCitation(
                    document_id=str(item.document_id),
                    chunk_id=str(item.chunk_id),
                    filename=item.filename,
                    snippet=SnippetService.clean(item.content, 240),
                    similarity_score=round(item.similarity_score, 6),
                    source_type=item.source_type,
                    section_header=item.section_header,
                    page_number=item.page_number,
                )
            )
        return citations

    # ---------------------------------------------------------------------
    # Confidence / gating
    # ---------------------------------------------------------------------

    def _llm_generation_enabled(
        self,
        *,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
    ) -> bool:
        if self.settings is None:
            return False
        if provider_candidates is not None:
            return len(provider_candidates) > 0
        if self.settings.ai_integration_scope != "embeddings_and_generation":
            return False
        if self.settings.llm_provider == "disabled":
            return False
        if self.settings.llm_provider in LOCAL_LLM_PROVIDERS:
            return True
        return bool(self.settings.llm_api_key)

    def _calculate_confidence(self, chunks: list[RetrievedChunk]) -> float:
        if not chunks:
            return 0.0

        scores = [c.similarity_score for c in chunks]
        top_score = scores[0]
        top3 = scores[:3]
        avg_top3 = sum(top3) / len(top3)
        unique_docs = len({c.document_id for c in chunks})
        source_bonus = min(unique_docs / 3.0, 1.0)

        if len(scores) >= 2:
            mean = sum(scores) / len(scores)
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)
            agreement = max(0.0, 1.0 - (variance * 10))
        else:
            agreement = 1.0

        spread = scores[0] - scores[-1] if len(scores) > 1 else 0.0
        spread_factor = max(0.0, 1.0 - spread)

        raw = (
            0.40 * top_score
            + 0.25 * avg_top3
            + 0.15 * source_bonus
            + 0.10 * agreement
            + 0.10 * spread_factor
        )
        return round(max(0.0, min(raw, 1.0)), 6)

    @staticmethod
    def _is_local_provider_candidate(candidate: ProviderSelectionCandidate) -> bool:
        if bool(candidate.metadata.get("is_local")):
            return True
        if candidate.provider_type in {"ollama", "lmstudio", "vllm"}:
            return True
        base_url = candidate.base_url
        if not base_url:
            return False
        hostname = (urlparse(base_url).hostname or "").strip().lower()
        if hostname in {"localhost", "127.0.0.1", "host.docker.internal"}:
            return True
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            return False
        return ip.is_loopback or ip.is_private

    def _allow_llm_usage(
        self,
        *,
        tenant_id: UUID,
        estimated_input_tokens: int,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
    ) -> bool:
        settings = self.settings
        if settings is None:
            return False
        if settings.env == "test" and provider_candidates:
            return True
        if provider_candidates and any(
            self._is_local_provider_candidate(candidate)
            for candidate in provider_candidates
        ):
            return True
        if estimated_input_tokens > settings.llm_max_tokens_per_request:
            return False

        month_key = datetime.now(tz=UTC).strftime("%Y%m")
        rpm_key = f"llm_usage:{tenant_id}:rpm:{int(time.time() // 60)}"
        budget_key = f"llm_usage:{tenant_id}:budget:{month_key}"

        estimated_cost = (
            estimated_input_tokens / 1_000_000.0
        ) * settings.llm_cost_per_1m_input_tokens_usd + (
            settings.llm_max_tokens_per_request / 1_000_000.0
        ) * settings.llm_cost_per_1m_output_tokens_usd
        estimated_cost_micros = int(estimated_cost * 1_000_000)

        try:
            client = get_redis_client()
            with client.pipeline() as pipe:
                pipe.incr(rpm_key)
                pipe.expire(rpm_key, 120, nx=True)
                pipe.get(budget_key)
                raw = pipe.execute()  # type: ignore[no-untyped-call]

            rpm_count = int(raw[0])
            current_budget = float(raw[2]) if raw[2] is not None else 0.0

            if rpm_count > settings.llm_max_requests_per_minute:
                return False
            if (
                current_budget + (estimated_cost_micros / 1_000_000.0)
                > settings.llm_monthly_budget_usd
            ):
                return False

            client.incrbyfloat(budget_key, estimated_cost_micros / 1_000_000.0)
            client.expire(budget_key, 35 * 24 * 3600, nx=True)
            return True
        except Exception:  # noqa: BLE001
            logger.warning(
                "LLM usage guard Redis unavailable; using in-memory fallback."
            )
            with self._limit_lock:
                now = time.time()
                rpm_current = self._limit_state.requests.get(rpm_key)
                if rpm_current is None or rpm_current[1] <= now:
                    rpm_count = 1
                    self._limit_state.requests[rpm_key] = (rpm_count, now + 120)
                else:
                    rpm_count = rpm_current[0] + 1
                    self._limit_state.requests[rpm_key] = (rpm_count, rpm_current[1])

                if rpm_count > settings.llm_max_requests_per_minute:
                    return False

                existing_micros = self._limit_state.cost_micros.get(budget_key, 0)
                if existing_micros + estimated_cost_micros > int(
                    settings.llm_monthly_budget_usd * 1_000_000
                ):
                    return False

                self._limit_state.cost_micros[budget_key] = (
                    existing_micros + estimated_cost_micros
                )
                return True

    @classmethod
    def _llm_is_circuit_open(cls) -> bool:
        opened_until = cls._llm_circuit.opened_until
        if opened_until is None:
            return False
        if datetime.now(tz=UTC) < opened_until:
            return True
        cls._llm_circuit.failures = 0
        cls._llm_circuit.opened_until = None
        return False

    def _record_llm_failure(self) -> None:
        if self.settings is None:
            return
        self._llm_circuit.failures += 1
        if (
            self._llm_circuit.failures
            >= self.settings.provider_circuit_breaker_threshold
        ):
            self._llm_circuit.opened_until = datetime.now(tz=UTC) + timedelta(
                seconds=self.settings.provider_circuit_breaker_reset_seconds,
            )

    def _record_llm_success(self) -> None:
        self._llm_circuit.failures = 0
        self._llm_circuit.opened_until = None

    # ---------------------------------------------------------------------
    # Prompt / provider
    # ---------------------------------------------------------------------

    def _build_llm_messages(
        self,
        query: str,
        context: str,
        history: list[dict[str, str]] | None,
        query_type: QueryType = QueryType.FACTUAL,
        *,
        structured_output: bool = True,
        response_directive: str | None = None,
    ) -> list[dict[str, str]]:
        sys_prompt = PromptTemplates.get_template(query_type).format(context=context)
        sys_prompt += (
            "\nIMPORTANT: You must respond in the exact same language that the user's Question is written in."
            "\nIMPORTANT: Prefer clean markdown with headings, bullets, and tables when helpful."
            "\nIMPORTANT: When the context contains numeric trends or quantitative comparisons (e.g. revenue, growth, percentages), use a ` ```chart ` block with the correct JSON payload to provide a high-fidelity visual."
            "\nIMPORTANT: Do not use Mermaid for numeric charts or trends; use the dedicated ` ```chart ` block instead."
        )
        if structured_output:
            sys_prompt += self._build_structured_output_instruction(
                query=query,
                query_type=query_type,
            )
        else:
            sys_prompt += (
                "\nIMPORTANT: Respond as clean readable markdown only. Do not wrap the answer in JSON."
                "\nIMPORTANT: If a diagram helps, render it directly as a Mermaid code block."
                "\nIMPORTANT: Use markdown tables directly instead of JSON fields."
            )
        if response_directive:
            sys_prompt += f"\nIMPORTANT: {response_directive.strip()}"

        messages: list[dict[str, str]] = [{"role": "system", "content": sys_prompt}]

        if history:
            messages.extend(history[-MAX_STREAM_HISTORY_MESSAGES:])

        messages.append(
            {
                "role": "user",
                "content": (
                    f"Context Documents:\n{context}\n\nQuestion: {query}\n\nGrounded Answer:"
                ),
            }
        )
        return messages

    def _build_open_chat_messages(
        self,
        query: str,
        history: list[dict[str, str]] | None,
        *,
        structured_output: bool = False,
        response_directive: str | None = None,
    ) -> list[dict[str, str]]:
        sys_prompt = (
            f"You are {APP_ASSISTANT_NAME}, the {APP_BRAND_NAME} intelligence running on the {APP_ENGINE_NAME} engine inside AverQel."
            "\nIMPORTANT: This is open chat, not grounded query mode."
            "\nIMPORTANT: Answer naturally and helpfully, even when no documents are involved."
            "\nIMPORTANT: Do not claim document verification, citations, references, or evidence unless the user explicitly provides source text in the chat."
            "\nIMPORTANT: Prefer clean markdown with headings, bullets, and tables when helpful."
            "\nIMPORTANT: Respond in the same language as the user's message."
            "\nIMPORTANT: You are an autonomous agent with access to tools. When you need to search documents, crawl websites, or sync services, output a tool call block. The system will execute it and feed the results back to you."
            '\nIMPORTANT: To call a tool, output: ```tool_call\n{"name": "tool_name", "arguments": {}}\n```'
            "\nIMPORTANT: Available tools: search_ecosystem_docs, web_search, crawl_url, sync_connector, list_connectors, get_connector_status, gmail_search, gmail_read, gmail_send, gmail_manage, calendar_list_events, calendar_find_free_slots, calendar_create_event, notion_create_page, notion_append_content."
            "\nIMPORTANT: You have full access to the user's Gmail, Google Calendar, and Notion if connected. You can search communications, manage your schedule, and create/update documentation. Always ask for permission before destructive actions (delete) or outbound actions (send email, create meeting) if not explicitly instructed."
            "\nIMPORTANT: You are a proactive brain. You can perform multi-app workflows (e.g., 'Draft a reply to this email and save it to my Notion'). You can also see and analyze images or screenshots provided in the chat to troubleshoot issues or extract data."
            "\nIMPORTANT: You have the authority to trigger autonomous actions such as web crawling, ecosystem synchronization, and cross-app data transfers. Always acknowledge the action you have initiated."
            "\nIMPORTANT: Use Mermaid code blocks only for real diagrams such as architecture, workflow, sequence, ER, state, class, journey, timeline, or mindmap."
            "\nIMPORTANT: Do not use Mermaid for ordinary charts or numeric trends."
            "\nIMPORTANT: AverQel can render native charts, tables, diagrams, and code blocks directly in the chat."
            "\nIMPORTANT: Never say you cannot generate a chart, diagram, table, or code block just because it is not an image."
            "\nIMPORTANT: When the user asks for code, answer with a proper fenced code block using the correct language tag."
        )
        if structured_output:
            sys_prompt += self._build_structured_output_instruction(
                query=query,
                query_type=QueryType.FACTUAL,
            )
            sys_prompt += (
                f"\nIMPORTANT: In open chat, use the {APP_BRAND_NAME} structured artifact system when charts, tables, or diagrams are requested."
                "\nIMPORTANT: Do not refuse chart or diagram creation."
            )
        else:
            sys_prompt += (
                "\nIMPORTANT: Respond as clean readable markdown only. Do not wrap the answer in JSON."
                "\nIMPORTANT: DO NOT output internal 'Response Object' or structured JSON blocks as code blocks."
                '\nIMPORTANT: For quantitative analysis (trends, metrics, distributions), always use a high-fidelity ` ```chart ` block with exactly: `{"chart_type": "bar|line|pie|area", "title": "...", "series": [{"label": "...", "value": 10}]}`.'
                "\nIMPORTANT: DO NOT use Mermaid for charts (bar chart, pie chart, xychart); use the ` ```chart ` block instead."
                "\nIMPORTANT: For structural diagrams (workflows, architecture, mindmaps), use ` ```mermaid `."
                "\nIMPORTANT: Place all visuals (charts, diagrams, tables) INLINE, immediately after the text that describes them. DO NOT put them all at the bottom."
            )
        if response_directive:
            sys_prompt += f"\nIMPORTANT: {response_directive.strip()}"

        messages: list[dict[str, str]] = [{"role": "system", "content": sys_prompt}]
        if history:
            messages.extend(history[-MAX_STREAM_HISTORY_MESSAGES:])
        messages.append({"role": "user", "content": query})
        return messages

    @staticmethod
    def _open_chat_wants_structured_output(query: str) -> bool:
        normalized = query.strip()
        if not normalized:
            return False
        if _OPEN_CHAT_CODE_QUERY_RE.search(normalized):
            return False
        return bool(
            AnswerService._build_structured_output_instruction(
                query=normalized,
                query_type=QueryType.FACTUAL,
            )
        )

    @staticmethod
    def _build_structured_output_instruction(
        *, query: str, query_type: QueryType
    ) -> str:
        normalized = query.strip()
        if not normalized:
            return ""

        lowered = normalized.lower()
        wants_graph_canvas = bool(_GRAPH_CANVAS_QUERY_RE.search(normalized))
        wants_diagram = (
            bool(_ARCHITECTURE_QUERY_RE.search(normalized)) or wants_graph_canvas
        )
        wants_chart = bool(_CHART_QUERY_RE.search(normalized))
        wants_table = query_type == QueryType.COMPARISON or wants_chart
        wants_cards = query_type in {
            QueryType.SYNTHESIS,
            QueryType.SUMMARIZATION,
            QueryType.VERIFICATION,
        }
        wants_structured = (
            wants_cards
            or wants_graph_canvas
            or wants_diagram
            or wants_chart
            or wants_table
        )

        if not wants_structured:
            return ""

        preferred_diagram_type = "mermaid_flowchart"
        preferred_diagram_source = "mermaid"
        preferred_mermaid_starter = "flowchart TD"
        padded_lowered = f" {lowered} "
        if "sequence" in lowered or "handoff" in lowered or "interaction" in lowered:
            preferred_diagram_type = "mermaid_sequence"
            preferred_mermaid_starter = "sequenceDiagram"
        elif "state diagram" in lowered or "state machine" in lowered:
            preferred_diagram_type = "mermaid_state"
            preferred_mermaid_starter = "stateDiagram-v2"
        elif "class diagram" in lowered or "object model" in lowered:
            preferred_diagram_type = "mermaid_class"
            preferred_mermaid_starter = "classDiagram"
        elif "entity relationship" in lowered or "er diagram" in lowered:
            preferred_diagram_type = "mermaid_er"
            preferred_mermaid_starter = "erDiagram"
        elif "journey" in lowered:
            preferred_diagram_type = "mermaid_journey"
            preferred_mermaid_starter = "journey"
        elif "timeline" in lowered:
            preferred_diagram_type = "mermaid_timeline"
            preferred_mermaid_starter = "timeline"
        elif "gantt" in lowered:
            preferred_diagram_type = "mermaid_gantt"
            preferred_mermaid_starter = "gantt"
        elif "mind map" in lowered or "mindmap" in lowered or "hierarchy" in lowered:
            preferred_diagram_type = "mermaid_mindmap"
            preferred_mermaid_starter = "mindmap"
        elif (
            "pie chart" in lowered
            or lowered.startswith("pie ")
            or "distribution share" in lowered
        ):
            preferred_diagram_type = "mermaid_pie"
            preferred_mermaid_starter = "pie"
        elif (
            "git graph" in lowered
            or "commit graph" in lowered
            or "branch history" in lowered
        ):
            preferred_diagram_type = "mermaid_gitgraph"
            preferred_mermaid_starter = "gitGraph"
        elif "quadrant" in lowered:
            preferred_diagram_type = "mermaid_quadrant"
            preferred_mermaid_starter = "quadrantChart"
        elif "requirement diagram" in lowered or "requirements diagram" in lowered:
            preferred_diagram_type = "mermaid_requirement"
            preferred_mermaid_starter = "requirementDiagram"
        elif "xy chart" in lowered or "xychart" in lowered:
            preferred_diagram_type = "mermaid_xychart"
            preferred_mermaid_starter = "xychart-beta"
        elif (
            "c4" in lowered
            or "container diagram" in lowered
            or "component diagram" in lowered
        ):
            preferred_diagram_type = "mermaid_c4"
            preferred_mermaid_starter = "C4Context"
        elif "architecture-beta" in lowered or "architecture diagram" in lowered:
            preferred_diagram_type = "mermaid_architecture"
            preferred_mermaid_starter = "architecture-beta"
        elif "sankey" in lowered:
            preferred_diagram_type = "mermaid_sankey"
            preferred_mermaid_starter = "sankey-beta"
        elif "packet" in lowered:
            preferred_diagram_type = "mermaid_packet"
            preferred_mermaid_starter = "packet-beta"
        elif "kanban" in lowered:
            preferred_diagram_type = "mermaid_kanban"
            preferred_mermaid_starter = "kanban"
        elif " left-to-right " in padded_lowered or " lr " in padded_lowered:
            preferred_mermaid_starter = "flowchart LR"
        elif " right-to-left " in padded_lowered or " rl " in padded_lowered:
            preferred_mermaid_starter = "flowchart RL"
        elif " bottom-to-top " in padded_lowered or " bt " in padded_lowered:
            preferred_mermaid_starter = "flowchart BT"
        elif wants_graph_canvas:
            preferred_diagram_type = "graph_canvas"
            preferred_diagram_source = "graph_json"

        instructions = [
            "\nIMPORTANT: Respond as a single valid JSON object with these keys exactly:",
            "key_findings, detailed_analysis, limitations, conclusion, confidence_score, follow_up_suggestions, comparison_table, chart, diagram.",
            "\nIMPORTANT: Use null for comparison_table, chart, or diagram when they are not needed.",
            "\nIMPORTANT: detailed_analysis must read like a polished answer in markdown and should explain the result around any structured artifacts instead of duplicating them verbatim.",
            "\nCRITICAL: NEVER wrap the detailed_analysis string in triple-backticks (```). It is ALREADY rendered as markdown. Putting it in backticks forces it into a clumsy 'CODE' box which is a failure.",
        ]

        if wants_table:
            instructions.append(
                "\nIMPORTANT: comparison_table must be filled for meaningful side-by-side comparisons with title, headers, and rows. Use at least two headers and one data row when comparison data exists."
            )
        if wants_chart:
            chart_type_hint = "bar"
            # Priority: Specialized -> Generic
            if any(
                k in lowered
                for k in [
                    "scatter",
                    "correlation",
                    "relationship",
                    "distribution",
                    "bubble",
                ]
            ):
                chart_type_hint = "scatter"
            elif any(k in lowered for k in ["area", "volume", "stacked", "cumulative"]):
                chart_type_hint = "area"
            elif any(
                k in lowered
                for k in [
                    "pie",
                    "share",
                    "percentage",
                    "distribution",
                    "proportion",
                    "breakdown",
                    "composition",
                    "segments",
                    "market",
                ]
            ):
                chart_type_hint = "pie"
            elif any(
                k in lowered
                for k in [
                    "time",
                    "over years",
                    "trend",
                    "history",
                    "monthly",
                    "annually",
                    "growth",
                ]
            ):
                chart_type_hint = "line"

            instructions.append(
                f"\nIMPORTANT: chart must be filled for trends or numeric comparisons. Prefer `chart_type`: `{chart_type_hint}` for this query."
                '\nIMPORTANT: Use EXACT chart JSON schema: `{"chart_type": "...", "title": "...", "series": [{"label": "NAME", "value": 123.45}]}`.'
                "\nIMPORTANT: Support for `chart_type` includes: `line`, `bar`, `area`, `scatter`, `pie`."
                "\nIMPORTANT: For distribution, share, or market data, ALWAYS use `chart_type`: `pie`. NEVER use Mermaid `pie` diagram."
                "\nIMPORTANT: Use `scatter` for correlation analysis between two variables. Use the `z` field to represent a third numeric dimension (bubble size). DO NOT connect scatter points with lines."
                "\nIMPORTANT: Use `area` for CUMULATIVE growth, VOLUME increases, or aggregate metrics. Avoid using `line` for volume as it lacks depth; `area` is more premium for these cases."
                "\nIMPORTANT: The `label` field MUST be a readable name (e.g. 'Apple', 'Jan 2024', 'Stage 1'). NEVER use the raw number as the label."
                "\nIMPORTANT: Always provide at least 2 data points for a meaningful chart."
            )
        if wants_diagram:
            instructions.append(
                "\nIMPORTANT: diagram must be filled for architecture, workflow, sequence, or process questions. "
                "DO NOT write Mermaid code blocks inside `detailed_analysis` unless an inline placement is strictly better for the explanation."
                f"\nIMPORTANT: Prefer `{preferred_diagram_type}` for this question."
            )
            if preferred_diagram_source == "graph_json":
                instructions.append(
                    "\nIMPORTANT: For this question, prefer source=`graph_json` and diagram_type=`graph_canvas`. "
                    "Return diagram.graph with typed nodes and edges. Keep syntax as an empty string when using graph_json."
                )
            else:
                instructions.append(
                    "\nIMPORTANT: When source=`mermaid`, use Mermaid syntax only and keep diagram.graph as null."
                    "\nIMPORTANT: DO NOT use Mermaid 'bar chart', 'pie', 'xychart-beta', or 'gantt' for numeric data; use the native `chart` property instead."
                    "\nIMPORTANT: The first Mermaid line must be a real Mermaid starter, such as "
                    "`flowchart TD`, `flowchart LR`, `flowchart RL`, `flowchart BT`, `graph TD`, `graph LR`, "
                    "`sequenceDiagram`, `stateDiagram-v2`, `classDiagram`, `erDiagram`, `journey`, "
                    "`timeline`, `mindmap`, `gitGraph`, `quadrantChart`, `gantt`, `pie`, "
                    "`requirementDiagram`, `C4Context`, `architecture-beta`, `zenuml`, "
                    "`sankey-beta`, `packet-beta`, `kanban`, `block-beta`, or `xychart-beta`."
                    "\nIMPORTANT: Never invent wrappers like `diagram TD`, `diagram LR`, or prose before the Mermaid syntax."
                    f"\nIMPORTANT: For this question, prefer starting the Mermaid block with `{preferred_mermaid_starter}`."
                    "\nIMPORTANT: Keep Mermaid syntax valid for the requested diagram family."
                    '\nIMPORTANT: ALWAYS wrap node labels in double quotes: `A["Label"]` or `B["Data Flow"]`.'
                    "\nIMPORTANT: NEVER use curly braces `{}` for node labels in flowcharts; use `[]`, `(())`, or `> <`."
                    "\nIMPORTANT: Avoid punctuation like commas, dots, or parentheses in node IDs; keep IDs simple (e.g. `A`, `Node1`)."
                    "\nIMPORTANT: For `erDiagram`, use canonical Mermaid ER relationships like "
                    "`Document ||--o{ Chunk : contains` and put entity fields on indented lines below each entity."
                    "\nIMPORTANT: For `erDiagram`, never use pseudo-table pipes like `| USERS |`."
                    "\nIMPORTANT: For `classDiagram`, use Mermaid class syntax like `class Document { +string id }`."
                    "\nIMPORTANT: For `classDiagram`, prefer `direction TB` near the top unless a different direction is clearly better."
                    "\nIMPORTANT: For `classDiagram`, use valid multiplicities only: `1`, `0..1`, `*`, `0..*`, or `1..*`."
                    "\nIMPORTANT: For `classDiagram`, do not use words like `many` for multiplicity."
                    "\nIMPORTANT: For `classDiagram`, do not model associations as fields like `list<Document>` or `List<Chunk>`."
                    "\nIMPORTANT: For `classDiagram`, keep only primitive/scalar fields inside classes and express associations with relation lines."
                    "\nIMPORTANT: For `classDiagram`, keep relation labels very short and omit them if the diagram becomes crowded."
                    "\nIMPORTANT: For `classDiagram`, prefer at most 3 fields per class and keep field labels short."
                    "\nIMPORTANT: For `stateDiagram-v2`, use valid state transitions like `[*] --> Uploaded`."
                    "\nIMPORTANT: For `mindmap`, keep each node label short and plain. Avoid citations, commas, colons, parentheses, and long sentences inside nodes."
                    "\nIMPORTANT: For `journey`, keep section names and task labels short and plain."
                    "\nIMPORTANT: For `timeline`, keep event labels short and avoid citation-style punctuation."
                    "\nIMPORTANT: For `gantt`, include valid Mermaid gantt structure such as `dateFormat YYYY-MM-DD`, `section Ingestion`, and `Task :done, id1, 2025-01-01, 1d`."
                    "\nIMPORTANT: For `pie`, keep slice labels short and numeric values explicit."
                    "\nIMPORTANT: For `quadrantChart`, define `title`, axis labels, and concise quadrant points."
                    "\nIMPORTANT: For `xychart-beta`, include compact x-axis and one or more numeric series."
                    "\nIMPORTANT: For Mermaid C4 diagrams, keep aliases short and avoid HTML styling."
                )
        if wants_cards:
            instructions.append(
                "\nIMPORTANT: key_findings, limitations, and conclusion should be substantive when the question asks for synthesis, verification, executive takeaways, or risk framing."
            )
        return "".join(instructions)

    def _call_llm_with_retry(
        self,
        *,
        query_text: str,
        context: str,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_override: ProviderSelectionCandidate | None = None,
        thinking_enabled: bool = False,
    ) -> tuple[str, dict[str, int]]:
        max_retries = 3
        base_delay_seconds = 1.0

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return self._call_llm_provider(
                    query_text=query_text,
                    context=context,
                    previous_messages=previous_messages,
                    query_type=query_type,
                    provider_override=provider_override,
                    thinking_enabled=thinking_enabled,
                )
            except RetryableLlmError as exc:
                last_exc = exc
                if attempt == max_retries:
                    raise
                logger.warning(
                    "LLM retryable failure.",
                    extra={"attempt": attempt, "max_retries": max_retries},
                )
                time.sleep(base_delay_seconds * (2 ** (attempt - 1)))

        raise NonRetryableLlmError("Max retries exceeded.") from last_exc

    def _call_llm_provider(
        self,
        *,
        query_text: str,
        context: str,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_override: ProviderSelectionCandidate | None = None,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> tuple[str, dict[str, int]]:
        settings = self._require_settings()
        start = time.monotonic()
        registry = ProviderRegistry(settings)
        provider = (
            registry.get_chat_provider_from_selection(provider_override)
            if provider_override is not None
            else registry.get_chat_provider()
        )
        request = ChatGenerateRequest(
            model=(
                provider_override.model_name
                if provider_override is not None
                else settings.llm_model
            ),
            temperature=(
                temperature_override
                if temperature_override is not None
                else settings.llm_temperature
            ),
            max_tokens=settings.llm_max_tokens_per_request,
            messages=self._build_llm_messages(
                query_text,
                context,
                previous_messages,
                query_type,
                response_directive=response_directive,
            ),
            base_url=(
                provider_override.base_url
                if provider_override is not None
                and provider_override.base_url is not None
                else settings.llm_api_base_url
            ),
            api_key=(
                provider_override.api_key
                if provider_override is not None
                else settings.llm_api_key
            ),
            reasoning_enabled=thinking_enabled,
            reasoning_effort="medium" if thinking_enabled else None,
            reasoning_visibility="provider_exposed" if thinking_enabled else None,
            metadata={
                "timeout_seconds": float(settings.provider_timeout_seconds),
                "httpx_module": importlib.import_module("httpx"),
                "provider_type": (
                    provider_override.provider_type
                    if provider_override is not None
                    else settings.llm_provider
                ),
            },
        )
        try:
            result = provider.generate(request)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ProviderRequestError):
                if exc.status_code in (429, 500, 502, 503, 504):
                    raise RetryableLlmError(
                        f"LLM provider retryable status {exc.status_code}"
                    ) from exc
                if 400 <= exc.status_code < 500:
                    raise NonRetryableLlmError(
                        f"LLM provider non-retryable status {exc.status_code}"
                    ) from exc
            message = str(exc)
            if "status 429" in message or any(
                f"status {code}" in message for code in (500, 502, 503, 504)
            ):
                raise RetryableLlmError(f"LLM provider retryable {message}") from exc
            if "status 4" in message:
                raise NonRetryableLlmError(
                    f"LLM provider non-retryable {message}"
                ) from exc
            raise RetryableLlmError("LLM provider request failed.") from exc
        finally:
            self._observe_provider_latency(start, provider_override=provider_override)
        return result.content, result.usage if isinstance(result.usage, dict) else {}

    async def _astream_provider_events(
        self,
        *,
        query_text: str,
        context: str,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_override: ProviderSelectionCandidate | None = None,
        structured_output: bool = True,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> AsyncIterator[dict[str, str]]:
        settings = self._require_settings()
        start = time.monotonic()
        registry = ProviderRegistry(settings)
        provider = (
            registry.get_chat_provider_from_selection(provider_override)
            if provider_override is not None
            else registry.get_chat_provider()
        )
        request = ChatGenerateRequest(
            model=(
                provider_override.model_name
                if provider_override is not None
                else settings.llm_model
            ),
            temperature=(
                temperature_override
                if temperature_override is not None
                else settings.llm_temperature
            ),
            max_tokens=settings.llm_max_tokens_per_request,
            messages=self._build_llm_messages(
                query_text,
                context,
                previous_messages,
                query_type,
                structured_output=structured_output,
                response_directive=response_directive,
            ),
            base_url=(
                provider_override.base_url
                if provider_override is not None
                and provider_override.base_url is not None
                else settings.llm_api_base_url
            ),
            api_key=(
                provider_override.api_key
                if provider_override is not None
                else settings.llm_api_key
            ),
            stream=True,
            reasoning_enabled=thinking_enabled,
            reasoning_effort="medium" if thinking_enabled else None,
            reasoning_visibility="provider_exposed" if thinking_enabled else None,
            metadata={
                "timeout_seconds": float(settings.provider_timeout_seconds),
                "read_timeout_seconds": STREAM_PREFILL_READ_TIMEOUT_SECONDS,
                "httpx_module": importlib.import_module("httpx"),
                "provider_type": (
                    provider_override.provider_type
                    if provider_override is not None
                    else settings.llm_provider
                ),
            },
        )
        try:
            stream_events = getattr(provider, "stream_generate_events", None)
            if callable(stream_events):
                async for event in stream_events(request):
                    event_type = str(event.get("type", "delta"))
                    text = str(event.get("text", ""))
                    if text:
                        yield {"type": event_type, "text": text}
                return
            async for content in provider.stream_generate(request):
                if content:
                    yield {"type": "delta", "text": content}
        except RetryableLlmError:
            raise
        except NonRetryableLlmError:
            raise
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "status 429" in message or any(
                f"status {code}" in message for code in (500, 502, 503, 504)
            ):
                raise RetryableLlmError(f"LLM provider retryable {message}") from exc
            if "status 4" in message:
                raise NonRetryableLlmError(
                    f"LLM provider non-retryable {message}"
                ) from exc
            if isinstance(exc, RetryableLlmError | NonRetryableLlmError):
                raise
            raise RetryableLlmError(f"Streaming request failed: {message}") from exc
        finally:
            self._observe_provider_latency(start, provider_override=provider_override)

    async def _astream_open_chat_provider_events(
        self,
        *,
        query_text: str,
        previous_messages: list[dict[str, str]] | None = None,
        provider_override: ProviderSelectionCandidate | None = None,
        structured_output: bool = False,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> AsyncIterator[dict[str, str]]:
        settings = self._require_settings()
        start = time.monotonic()
        registry = ProviderRegistry(settings)
        provider = (
            registry.get_chat_provider_from_selection(provider_override)
            if provider_override is not None
            else registry.get_chat_provider()
        )
        request = ChatGenerateRequest(
            model=(
                provider_override.model_name
                if provider_override is not None
                else settings.llm_model
            ),
            temperature=(
                temperature_override
                if temperature_override is not None
                else settings.llm_temperature
            ),
            max_tokens=settings.llm_max_tokens_per_request,
            messages=self._build_open_chat_messages(
                query_text,
                previous_messages,
                structured_output=structured_output,
                response_directive=response_directive,
            ),
            base_url=(
                provider_override.base_url
                if provider_override is not None
                and provider_override.base_url is not None
                else settings.llm_api_base_url
            ),
            api_key=(
                provider_override.api_key
                if provider_override is not None
                else settings.llm_api_key
            ),
            stream=True,
            reasoning_enabled=thinking_enabled,
            reasoning_effort="medium" if thinking_enabled else None,
            reasoning_visibility="provider_exposed" if thinking_enabled else None,
            metadata={
                "timeout_seconds": float(settings.provider_timeout_seconds),
                "read_timeout_seconds": STREAM_PREFILL_READ_TIMEOUT_SECONDS,
                "httpx_module": importlib.import_module("httpx"),
                "provider_type": (
                    provider_override.provider_type
                    if provider_override is not None
                    else settings.llm_provider
                ),
            },
        )
        try:
            stream_events = getattr(provider, "stream_generate_events", None)
            if callable(stream_events):
                async for event in stream_events(request):
                    event_type = str(event.get("type", "delta"))
                    text = str(event.get("text", ""))
                    if text:
                        yield {"type": event_type, "text": text}
                return
            async for content in provider.stream_generate(request):
                if content:
                    yield {"type": "delta", "text": content}
        except RetryableLlmError:
            raise
        except NonRetryableLlmError:
            raise
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "status 429" in message or any(
                f"status {code}" in message for code in (500, 502, 503, 504)
            ):
                raise RetryableLlmError(f"LLM provider retryable {message}") from exc
            if "status 4" in message:
                raise NonRetryableLlmError(
                    f"LLM provider non-retryable {message}"
                ) from exc
            raise RetryableLlmError("LLM provider request failed.") from exc
        finally:
            self._observe_provider_latency(start, provider_override=provider_override)

    async def _astream_provider_text(
        self,
        *,
        query_text: str,
        context: str,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_override: ProviderSelectionCandidate | None = None,
        structured_output: bool = True,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> AsyncIterator[str]:
        async for event in self._astream_provider_events(
            query_text=query_text,
            context=context,
            previous_messages=previous_messages,
            query_type=query_type,
            provider_override=provider_override,
            structured_output=structured_output,
            response_directive=response_directive,
            temperature_override=temperature_override,
            thinking_enabled=thinking_enabled,
        ):
            if event["type"] == "delta":
                yield event["text"]

    def _stream_provider_text(
        self,
        *,
        query_text: str,
        context: str,
        previous_messages: list[dict[str, str]] | None = None,
        query_type: QueryType = QueryType.FACTUAL,
        provider_override: ProviderSelectionCandidate | None = None,
        structured_output: bool = True,
        response_directive: str | None = None,
        temperature_override: float | None = None,
        thinking_enabled: bool = False,
    ) -> Iterator[str]:
        settings = self._require_settings()
        start = time.monotonic()
        registry = ProviderRegistry(settings)
        provider = (
            registry.get_chat_provider_from_selection(provider_override)
            if provider_override is not None
            else registry.get_chat_provider()
        )
        request = ChatGenerateRequest(
            model=(
                provider_override.model_name
                if provider_override is not None
                else settings.llm_model
            ),
            temperature=(
                temperature_override
                if temperature_override is not None
                else settings.llm_temperature
            ),
            max_tokens=settings.llm_max_tokens_per_request,
            messages=self._build_llm_messages(
                query_text,
                context,
                previous_messages,
                query_type,
                structured_output=structured_output,
                response_directive=response_directive,
            ),
            base_url=(
                provider_override.base_url
                if provider_override is not None
                and provider_override.base_url is not None
                else settings.llm_api_base_url
            ),
            api_key=(
                provider_override.api_key
                if provider_override is not None
                else settings.llm_api_key
            ),
            stream=True,
            reasoning_enabled=thinking_enabled,
            reasoning_effort="medium" if thinking_enabled else None,
            reasoning_visibility="provider_exposed" if thinking_enabled else None,
            metadata={
                "timeout_seconds": float(settings.provider_timeout_seconds),
                "read_timeout_seconds": STREAM_PREFILL_READ_TIMEOUT_SECONDS,
                "httpx_module": importlib.import_module("httpx"),
                "provider_type": (
                    provider_override.provider_type
                    if provider_override is not None
                    else settings.llm_provider
                ),
            },
        )
        try:
            yield from provider.stream_generate_sync(request)
        except RetryableLlmError:
            raise
        except NonRetryableLlmError:
            raise
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "status 429" in message or any(
                f"status {code}" in message for code in (500, 502, 503, 504)
            ):
                raise RetryableLlmError(f"LLM provider retryable {message}") from exc
            if "status 4" in message:
                raise NonRetryableLlmError(
                    f"LLM provider non-retryable {message}"
                ) from exc

            if isinstance(exc, RetryableLlmError | NonRetryableLlmError):
                raise
            raise RetryableLlmError(f"Streaming request failed: {message}") from exc
        finally:
            self._observe_provider_latency(start, provider_override=provider_override)

    @staticmethod
    def _extract_markdown_suggestions(text: str) -> list[str]:
        # Handle ---suggestions--- or *suggestions--- or ### Suggestions
        patterns = [
            r"(?i)(?:---|\*|###)\s*suggestions\s*(?:---|:)?\s*\n(.*?)(?:\n\s*(?:---|\*|###)|$)",
            r"(?i)follow[ -]up questions:?\s*\n(.*?)(?:\n\n|$)",
        ]
        suggestions: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.DOTALL):
                raw = match.group(1).strip()
                lines = [
                    line.strip().strip("*- ").strip()
                    for line in raw.splitlines()
                    if line.strip() and len(line.strip().strip("-*# ")) > 0
                ]
                suggestions.extend(lines)
        return suggestions

    @staticmethod
    def _strip_markdown_metadata(text: str) -> str:
        # Strip suggestions and other metadata blocks
        patterns = [
            r"(?i)(?:---|\*|###)\s*suggestions\s*(?:---|:)?\s*\n.*?(?:\n\s*(?:---|\*|###)|$)",
            r"(?i)follow[ -]up questions:?\s*\n.*?(?:\n\n|$)",
            r"(?i)---chart data---.*?(?:\n---|$)",
        ]
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)
        # Also clean up trailing separators if any
        cleaned = re.sub(r"\n\s*(?:---|\*|###)\s*$", "", cleaned)
        return cleaned.strip()

    def _require_settings(self) -> Settings:
        if self.settings is None:
            raise NonRetryableLlmError("LLM settings are not configured.")
        return self.settings

    def _observe_provider_latency(
        self,
        start: float,
        *,
        provider_override: ProviderSelectionCandidate | None = None,
    ) -> None:
        settings = self.settings
        if settings is None:
            return
        try:
            LLM_PROVIDER_LATENCY_SECONDS.labels(
                provider=(
                    provider_override.provider_type
                    if provider_override is not None
                    else settings.llm_provider
                ),
                model=(
                    provider_override.model_name
                    if provider_override is not None
                    else settings.llm_model
                ),
            ).observe(time.monotonic() - start)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to record LLM latency metric.", exc_info=True)

    @staticmethod
    def _redact_provider_failure_reason(reason: str) -> str:
        lowered = reason.lower()
        if "429" in lowered:
            return "rate_limited"
        if any(code in lowered for code in ("500", "502", "503", "504", "timeout")):
            return "provider_unavailable"
        if "401" in lowered or "403" in lowered:
            return "provider_auth_failed"
        if "400" in lowered or "422" in lowered:
            return "provider_request_invalid"
        return "provider_failure"

    def _build_provider_failure_event_data(
        self,
        *,
        code: str,
        message: str,
        provider_candidate: ProviderSelectionCandidate | None,
        fallback_used: bool,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "provider": (
                {
                    "type": provider_candidate.provider_type,
                    "model": provider_candidate.model_name,
                    "source": provider_candidate.source,
                }
                if provider_candidate is not None
                else None
            ),
            "fallback_used": fallback_used,
            "reason": self._redact_provider_failure_reason(reason),
        }

    def _env_provider_candidate(self) -> ProviderSelectionCandidate:
        settings = self._require_settings()
        return ProviderSelectionCandidate(
            provider_type=settings.llm_provider,
            model_name=settings.llm_model,
            feature_scope="chat",
            source="env_fallback",
            base_url=settings.llm_api_base_url,
            api_key=settings.llm_api_key,
            metadata={"compatibility_fallback": True},
        )

    # ---------------------------------------------------------------------
    # Context / estimation
    # ---------------------------------------------------------------------

    @staticmethod
    def _build_prompt_context(chunks: list[RetrievedChunk]) -> str:
        lines: list[str] = []
        for index, item in enumerate(chunks, start=1):
            snippet = " ".join(item.content.strip().split())
            if len(snippet) > MAX_PROMPT_CONTEXT_SNIPPET_CHARS:
                snippet = snippet[: MAX_PROMPT_CONTEXT_SNIPPET_CHARS - 3] + "..."
            lines.append(f"[{index}] (File: {item.filename}) Content: {snippet}")
        return "\n".join(lines)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        normalized = text.strip()
        if not normalized:
            return 0
        return len(normalized.split())
