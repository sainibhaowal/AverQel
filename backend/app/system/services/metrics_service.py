from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, cast

import redis
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.core.config import get_settings

logger = logging.getLogger(__name__)

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
DEEPSPACE_CACHE_USAGE_TOTAL = Counter(
    "aks_deepspace_cache_usage_total",
    "DeepSpace provider cache usage observations",
    labelnames=("provider", "status"),
)
DEEPSPACE_CONTEXT_COMPACTIONS_TOTAL = Counter(
    "aks_deepspace_context_compactions_total",
    "DeepSpace context compaction events",
    labelnames=("reason",),
)
DEEPSPACE_MCP_RESULT_REFERENCES_TOTAL = Counter(
    "aks_deepspace_mcp_result_references_total",
    "MCP results stored as bounded server-side references",
)
DEEPSPACE_CONTEXT_OVERFLOW_PREVENTED_TOTAL = Counter(
    "aks_deepspace_context_overflow_prevented_total",
    "Requests made safe by context fitting or compaction",
    labelnames=("action",),
)
DEEPSPACE_BUDGET_ALLOCATIONS_TOTAL = Counter(
    "aks_deepspace_budget_allocations_total",
    "Adaptive DeepSpace budget allocations by workload and context tier",
    labelnames=("workload", "context_tier"),
)
DEEPSPACE_RESULT_REFERENCE_EVENTS_TOTAL = Counter(
    "aks_deepspace_result_reference_events_total",
    "DeepSpace native and MCP result-reference events",
    labelnames=("kind", "status"),
)
DEEPSPACE_EXECUTION_BATCHES_TOTAL = Counter(
    "aks_deepspace_execution_batches_total",
    "DeepSpace execution batches by scheduling mode",
    labelnames=("mode",),
)
DEEPSPACE_CANARY_MISMATCHES_TOTAL = Counter(
    "aks_deepspace_canary_mismatches_total",
    "Non-authoritative DeepSpace tool-profile canary mismatches",
)

# Dashboard counters are shared across API and Celery processes through Redis.
# Prometheus remains the source for detailed scrape metrics; these fixed,
# low-cardinality totals provide a service-wide admin snapshot and event stream.
RUNTIME_METRICS_HASH_KEY = "averqel:runtime-metrics:v1:counters"
RUNTIME_METRICS_UPDATE_CHANNEL = "averqel:runtime-metrics:v1:updates"
RUNTIME_METRICS_PUBLISH_THROTTLE_KEY = "averqel:runtime-metrics:v1:publish-window"
RUNTIME_METRIC_COUNTER_FIELDS = frozenset(
    {
        "api_requests_total",
        "api_errors_total",
        "db_query_count",
        "worker_retries_total",
        "worker_dead_letters_total",
        "deepspace_cache_reads_total",
        "deepspace_cache_writes_total",
        "deepspace_context_compactions_total",
        "deepspace_overflow_prevented_total",
        "deepspace_mcp_result_references_total",
        "deepspace_budget_allocations_total",
        "deepspace_result_reference_events_total",
        "deepspace_execution_batches_total",
        "deepspace_canary_mismatches_total",
    }
)

_RUNTIME_METRIC_INCREMENT_SCRIPT = """
local value = redis.call('HINCRBY', KEYS[1], ARGV[1], ARGV[2])
redis.call('HSETNX', KEYS[1], 'meta:started_at', ARGV[3])
redis.call('HSETNX', KEYS[1], 'meta:complete', '1')
if ARGV[4] == '1' then
    redis.call('HSET', KEYS[1], 'meta:complete', '0')
end
if redis.call('SET', KEYS[2], '1', 'NX', 'PX', 250) then
    redis.call('PUBLISH', KEYS[3], 'metrics_changed')
end
return value
"""

_runtime_metrics_write_incomplete = False
_runtime_metrics_write_warning_logged = False


class RuntimeMetricsUnavailableError(RuntimeError):
    """The shared runtime metrics store could not provide a trustworthy snapshot."""


@lru_cache(maxsize=1)
def get_runtime_metrics_redis_client() -> redis.Redis:
    """Return a bounded Redis client for best-effort metrics writes and snapshots."""
    settings = get_settings()
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
        retry_on_timeout=False,
    )


def increment_runtime_metric(metric_name: str, amount: int = 1) -> bool:
    """Atomically add a service-wide event and notify active admin streams.

    Metrics are deliberately fail-open so a telemetry outage cannot fail an
    application request. A process that observes a failed write marks the
    shared snapshot incomplete on its next successful write.
    """
    global _runtime_metrics_write_incomplete, _runtime_metrics_write_warning_logged

    if metric_name not in RUNTIME_METRIC_COUNTER_FIELDS:
        raise ValueError(f"Unsupported runtime metric counter: {metric_name}")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
        raise ValueError("Runtime metric increments must be positive integers")

    try:
        get_runtime_metrics_redis_client().eval(
            _RUNTIME_METRIC_INCREMENT_SCRIPT,
            3,
            RUNTIME_METRICS_HASH_KEY,
            RUNTIME_METRICS_PUBLISH_THROTTLE_KEY,
            RUNTIME_METRICS_UPDATE_CHANNEL,
            metric_name,
            str(amount),
            datetime.now(UTC).isoformat(),
            "1" if _runtime_metrics_write_incomplete else "0",
        )
    except Exception:  # noqa: BLE001
        # Keep request/worker behavior independent from telemetry, including
        # invalid Redis configuration and client construction failures.
        _runtime_metrics_write_incomplete = True
        if not _runtime_metrics_write_warning_logged:
            logger.warning(
                "Shared runtime metric write failed; dashboard totals may be incomplete.",
                extra={"metric_name": metric_name},
                exc_info=True,
            )
            _runtime_metrics_write_warning_logged = True
        return False
    return True


def _build_runtime_metrics_summary(values: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for field in RUNTIME_METRIC_COUNTER_FIELDS:
        raw_value = values.get(field, "0")
        try:
            parsed_value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise RuntimeMetricsUnavailableError("Shared runtime metrics data is invalid") from exc
        if parsed_value < 0:
            raise RuntimeMetricsUnavailableError("Shared runtime metrics data is invalid")
        summary[field] = parsed_value

    complete_value = values.get("meta:complete")
    if complete_value not in {"0", "1"}:
        raise RuntimeMetricsUnavailableError("Shared runtime metrics metadata is invalid")
    started_at_value = values.get("meta:started_at")
    if not isinstance(started_at_value, str) or not started_at_value:
        raise RuntimeMetricsUnavailableError("Shared runtime metrics metadata is invalid")
    try:
        started_at = datetime.fromisoformat(started_at_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeMetricsUnavailableError("Shared runtime metrics metadata is invalid") from exc
    if started_at.tzinfo is None:
        raise RuntimeMetricsUnavailableError("Shared runtime metrics metadata is invalid")

    summary["metrics_scope"] = "service-wide"
    summary["metrics_complete"] = complete_value == "1"
    summary["metrics_started_at"] = started_at
    summary["snapshot_at"] = datetime.now(UTC)
    return summary


def read_runtime_metrics_summary() -> dict[str, Any]:
    """Read service-wide counters, including API and worker processes."""
    try:
        client = get_runtime_metrics_redis_client()
        client.hsetnx(
            RUNTIME_METRICS_HASH_KEY,
            "meta:started_at",
            datetime.now(UTC).isoformat(),
        )
        client.hsetnx(RUNTIME_METRICS_HASH_KEY, "meta:complete", "1")
        values = cast(dict[str, Any], client.hgetall(RUNTIME_METRICS_HASH_KEY))
        return _build_runtime_metrics_summary(values)
    except RuntimeMetricsUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeMetricsUnavailableError("Shared runtime metrics store is unavailable") from exc


async def read_runtime_metrics_summary_async(client: Any) -> dict[str, Any]:
    """Async snapshot reader used by the long-lived admin event stream."""
    try:
        await client.hsetnx(
            RUNTIME_METRICS_HASH_KEY,
            "meta:started_at",
            datetime.now(UTC).isoformat(),
        )
        await client.hsetnx(RUNTIME_METRICS_HASH_KEY, "meta:complete", "1")
        values = await client.hgetall(RUNTIME_METRICS_HASH_KEY)
        return _build_runtime_metrics_summary(values)
    except RuntimeMetricsUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeMetricsUnavailableError("Shared runtime metrics store is unavailable") from exc


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
UNSUPPORTED_FORMAT_FALLBACK_TOTAL = Counter(
    "aks_unsupported_format_fallback_total",
    "Accepted uploads handled by download/text fallback",
    labelnames=("extension",),
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
STORAGE_RETENTION_RUNS_TOTAL = Counter(
    "aks_storage_retention_runs_total",
    "Storage retention and reconciliation runs by operation and status",
    labelnames=("operation", "status"),
)
STORAGE_RETENTION_ITEMS_TOTAL = Counter(
    "aks_storage_retention_items_total",
    "Storage lifecycle items by retention decision",
    labelnames=("decision",),
)
STORAGE_RETENTION_MISMATCHES_TOTAL = Counter(
    "aks_storage_retention_mismatches_total",
    "Storage reconciliation category mismatches",
)
STORAGE_QUOTA_RESERVATIONS_TOTAL = Counter(
    "aks_storage_quota_reservations_total",
    "Atomic storage reservation outcomes",
    labelnames=("outcome",),
)


def _safe_label(value: str, *, default: str = "unknown") -> str:
    normalized = (value or "").strip()
    return normalized or default


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def increment_query_cache_event(*, event: str) -> None:
    QUERY_CACHE_EVENTS_TOTAL.labels(event=_safe_label(event)).inc()


def increment_worker_retry(*, stage: str) -> None:
    WORKER_RETRIES_TOTAL.labels(stage=_safe_label(stage)).inc()
    increment_runtime_metric("worker_retries_total")


def increment_worker_dead_letter(*, stage: str) -> None:
    WORKER_DEAD_LETTER_TOTAL.labels(stage=_safe_label(stage)).inc()
    increment_runtime_metric("worker_dead_letters_total")


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
def observe_db_query(operation: str) -> Generator[None]:
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
        increment_runtime_metric("db_query_count")


@contextmanager
def observe_worker_stage(stage: str) -> Generator[None]:
    stage_label = _safe_label(stage)
    start = time.perf_counter()
    try:
        yield
        WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage_label, status="success").inc()
    except Exception:  # noqa: BLE001
        WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage_label, status="error").inc()
        raise
    finally:
        WORKER_STAGE_DURATION_SECONDS.labels(stage=stage_label).observe(time.perf_counter() - start)


@contextmanager
def observe_extraction_stage(stage: str) -> Generator[None]:
    stage_label = _safe_label(stage)
    start = time.perf_counter()
    try:
        yield
    finally:
        EXTRACTION_STAGE_DURATION_SECONDS.labels(stage=stage_label).observe(
            time.perf_counter() - start
        )


@contextmanager
def observe_query_pipeline_segment(segment: str) -> Generator[None]:
    segment_label = _safe_label(segment)
    start = time.perf_counter()
    try:
        yield
    finally:
        QUERY_PIPELINE_DURATION_SECONDS.labels(segment=segment_label).observe(
            time.perf_counter() - start
        )


@contextmanager
def observe_embedding_provider(provider: str, model: str) -> Generator[None]:
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
def observe_llm_provider(provider: str, model: str) -> Generator[None]:
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
