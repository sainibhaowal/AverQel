from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

API_REQUESTS_TOTAL = Counter(
    "aks_api_requests_total",
    "Total API requests",
    labelnames=("method", "path", "status"),
)
API_REQUEST_LATENCY_SECONDS = Histogram(
    "aks_api_request_latency_seconds",
    "API request latency in seconds",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
API_ERRORS_TOTAL = Counter(
    "aks_api_errors_total",
    "Total API errors by canonical error code",
    labelnames=("code",),
)

WORKER_JOB_TRANSITIONS_TOTAL = Counter(
    "aks_worker_job_transitions_total",
    "Worker job transitions by stage and status",
    labelnames=("stage", "status"),
)
WORKER_RETRIES_TOTAL = Counter(
    "aks_worker_retries_total",
    "Worker retries by stage",
    labelnames=("stage",),
)
WORKER_DEAD_LETTER_TOTAL = Counter(
    "aks_worker_dead_letter_total",
    "Worker dead-letter events by stage",
    labelnames=("stage",),
)
WORKER_LOCK_CONTENTION_TOTAL = Counter(
    "aks_worker_lock_contention_total",
    "Worker lock contention events by stage",
    labelnames=("stage",),
)
SUBAGENT_STALE_SLOT_REAPED_TOTAL = Counter(
    "aks_subagent_stale_slot_reaped_total",
    "Stale sub-agent slot reclamation events",
)
WORKER_STAGE_DURATION_SECONDS = Histogram(
    "aks_worker_stage_duration_seconds",
    "Worker stage duration in seconds",
    labelnames=("stage",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
DEEPSPACE_CONTINUATION_EVENTS_TOTAL = Counter(
    "aks_deepspace_continuation_events_total",
    "Full-autonomy continuation lifecycle events",
    labelnames=("status",),
)

QUERY_PIPELINE_DURATION_SECONDS = Histogram(
    "aks_query_pipeline_duration_seconds",
    "Query pipeline duration in seconds by segment",
    labelnames=("segment",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
QUERY_CACHE_EVENTS_TOTAL = Counter(
    "aks_query_cache_events_total",
    "Query cache events",
    labelnames=("event",),
)

EXTRACTION_METHOD_TOTAL = Counter(
    "aks_extraction_method_total",
    "Extraction completions by method",
    labelnames=("method",),
)
EXTRACTION_FALLBACK_TOTAL = Counter(
    "aks_extraction_fallback_total",
    "Extraction fallback events by path and reason",
    labelnames=("path", "reason"),
)
EXTRACTION_LOW_CONFIDENCE_TOTAL = Counter(
    "aks_extraction_low_confidence_total",
    "Low-confidence extraction events by confidence band",
    labelnames=("band",),
)
EXTRACTION_FAILURE_TOTAL = Counter(
    "aks_extraction_failure_total",
    "Extraction failures by canonical error code",
    labelnames=("code",),
)
EXTRACTION_STAGE_DURATION_SECONDS = Histogram(
    "aks_extraction_stage_duration_seconds",
    "Extraction stage duration in seconds",
    labelnames=("stage",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

DB_QUERY_DURATION_SECONDS = Histogram(
    "aks_db_query_duration_seconds",
    "Database query duration in seconds by repository operation",
    labelnames=("operation",),
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
DB_ERRORS_TOTAL = Counter(
    "aks_db_errors_total",
    "Database errors by operation",
    labelnames=("operation",),
)
DB_CONNECTION_CHECKOUT_DURATION_SECONDS = Histogram(
    "aks_db_connection_checkout_duration_seconds",
    "Database connection/session checkout duration in seconds",
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)

EMBEDDING_PROVIDER_LATENCY_SECONDS = Histogram(
    "aks_embedding_provider_latency_seconds",
    "Embedding provider latency in seconds",
    labelnames=("provider", "model"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
EMBEDDING_PROVIDER_FAILURES_TOTAL = Counter(
    "aks_embedding_provider_failures_total",
    "Embedding provider failures by reason",
    labelnames=("reason",),
)
LLM_PROVIDER_LATENCY_SECONDS = Histogram(
    "aks_llm_provider_latency_seconds",
    "LLM provider latency in seconds",
    labelnames=("provider", "model"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
LLM_PROVIDER_FAILURES_TOTAL = Counter(
    "aks_llm_provider_failures_total",
    "LLM provider failures by reason",
    labelnames=("reason",),
)
LLM_PROVIDER_FALLBACK_TOTAL = Counter(
    "aks_llm_provider_fallback_total",
    "LLM provider fallback events by reason",
    labelnames=("reason",),
)
MAINTENANCE_JOB_EVENTS_TOTAL = Counter(
    "aks_maintenance_job_events_total",
    "Maintenance job events by job and status",
    labelnames=("job", "status"),
)


def _safe_label(value: str, *, default: str = "unknown") -> str:
    normalized = (value or "").strip()
    return normalized or default


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def read_metrics_summary() -> tuple[int, int, int]:
    """Return request, error, and database-query counts from this process."""
    totals = {"requests": 0, "errors": 0, "queries": 0}
    for family in API_REQUESTS_TOTAL.collect():
        for sample in family.samples:
            if sample.name == "aks_api_requests_total":
                totals["requests"] += int(sample.value)
    for family in API_ERRORS_TOTAL.collect():
        for sample in family.samples:
            if sample.name == "aks_api_errors_total":
                totals["errors"] += int(sample.value)
    for family in DB_QUERY_DURATION_SECONDS.collect():
        for sample in family.samples:
            if sample.name == "aks_db_query_duration_seconds_count":
                totals["queries"] += int(sample.value)
    return totals["requests"], totals["errors"], totals["queries"]


def increment_query_cache_event(*, event: str) -> None:
    QUERY_CACHE_EVENTS_TOTAL.labels(event=_safe_label(event)).inc()


def increment_worker_retry(*, stage: str) -> None:
    WORKER_RETRIES_TOTAL.labels(stage=_safe_label(stage)).inc()


def increment_worker_dead_letter(*, stage: str) -> None:
    WORKER_DEAD_LETTER_TOTAL.labels(stage=_safe_label(stage)).inc()


def increment_worker_lock_contention(*, stage: str) -> None:
    WORKER_LOCK_CONTENTION_TOTAL.labels(stage=_safe_label(stage)).inc()


def increment_subagent_stale_slot_reaped() -> None:
    SUBAGENT_STALE_SLOT_REAPED_TOTAL.inc()


def increment_extraction_method(*, method: str) -> None:
    EXTRACTION_METHOD_TOTAL.labels(method=_safe_label(method)).inc()


def increment_extraction_fallback(*, path: str, reason: str) -> None:
    EXTRACTION_FALLBACK_TOTAL.labels(
        path=_safe_label(path),
        reason=_safe_label(reason),
    ).inc()


def increment_extraction_low_confidence(*, band: str) -> None:
    EXTRACTION_LOW_CONFIDENCE_TOTAL.labels(band=_safe_label(band)).inc()


def increment_extraction_failure(*, code: str) -> None:
    EXTRACTION_FAILURE_TOTAL.labels(code=_safe_label(code)).inc()


def increment_embedding_provider_failure(*, reason: str) -> None:
    EMBEDDING_PROVIDER_FAILURES_TOTAL.labels(reason=_safe_label(reason)).inc()


def increment_llm_provider_failure(*, reason: str) -> None:
    LLM_PROVIDER_FAILURES_TOTAL.labels(reason=_safe_label(reason)).inc()


def increment_llm_provider_fallback(*, reason: str) -> None:
    LLM_PROVIDER_FALLBACK_TOTAL.labels(reason=_safe_label(reason)).inc()


def increment_maintenance_job_event(*, job: str, status: str) -> None:
    MAINTENANCE_JOB_EVENTS_TOTAL.labels(
        job=_safe_label(job),
        status=_safe_label(status),
    ).inc()


@contextmanager
def observe_db_query(operation: str) -> Generator[None, None, None]:
    operation_label = _safe_label(operation)
    start = time.perf_counter()
    try:
        yield
    except Exception:  # noqa: BLE001
        DB_ERRORS_TOTAL.labels(operation=operation_label).inc()
        raise
    finally:
        DB_QUERY_DURATION_SECONDS.labels(operation=operation_label).observe(
            time.perf_counter() - start
        )


@contextmanager
def observe_worker_stage(stage: str) -> Generator[None, None, None]:
    stage_label = _safe_label(stage)
    start = time.perf_counter()
    try:
        yield
        WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage_label, status="success").inc()
    except Exception:  # noqa: BLE001
        WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage_label, status="error").inc()
        raise
    finally:
        WORKER_STAGE_DURATION_SECONDS.labels(stage=stage_label).observe(
            time.perf_counter() - start
        )


@contextmanager
def observe_extraction_stage(stage: str) -> Generator[None, None, None]:
    stage_label = _safe_label(stage)
    start = time.perf_counter()
    try:
        yield
    finally:
        EXTRACTION_STAGE_DURATION_SECONDS.labels(stage=stage_label).observe(
            time.perf_counter() - start
        )


@contextmanager
def observe_query_pipeline_segment(segment: str) -> Generator[None, None, None]:
    segment_label = _safe_label(segment)
    start = time.perf_counter()
    try:
        yield
    finally:
        QUERY_PIPELINE_DURATION_SECONDS.labels(segment=segment_label).observe(
            time.perf_counter() - start
        )


@contextmanager
def observe_embedding_provider(
    provider: str, model: str
) -> Generator[None, None, None]:
    provider_label = _safe_label(provider)
    model_label = _safe_label(model)
    start = time.perf_counter()
    try:
        yield
    finally:
        EMBEDDING_PROVIDER_LATENCY_SECONDS.labels(
            provider=provider_label,
            model=model_label,
        ).observe(time.perf_counter() - start)


@contextmanager
def observe_llm_provider(provider: str, model: str) -> Generator[None, None, None]:
    provider_label = _safe_label(provider)
    model_label = _safe_label(model)
    start = time.perf_counter()
    try:
        yield
    finally:
        LLM_PROVIDER_LATENCY_SECONDS.labels(
            provider=provider_label,
            model=model_label,
        ).observe(time.perf_counter() - start)
