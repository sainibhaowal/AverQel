#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

import redis
import requests  # type: ignore[import-untyped]

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


@dataclass(slots=True)
class QueryRun:
    latency_ms: float
    ok: bool
    cached: bool
    status_code: int
    error_code: str | None


def run_query_once(url: str, headers: dict[str, str], payload: dict[str, object]) -> QueryRun:
    start = time.perf_counter()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
    except Exception:  # noqa: BLE001
        latency_ms = (time.perf_counter() - start) * 1000
        return QueryRun(
            latency_ms=latency_ms,
            ok=False,
            cached=False,
            status_code=0,
            error_code="CLIENT_EXCEPTION",
        )
    latency_ms = (time.perf_counter() - start) * 1000
    cached = False
    error_code: str | None = None
    if response.status_code == 200:
        try:
            payload_data = response.json()
            cached = bool(payload_data.get("cached", False))
        except Exception:  # noqa: BLE001
            cached = False
    else:
        try:
            error_code = (response.json().get("error") or {}).get("code")
        except Exception:  # noqa: BLE001
            error_code = None
    return QueryRun(
        latency_ms=latency_ms,
        ok=response.status_code == 200,
        cached=cached,
        status_code=response.status_code,
        error_code=error_code,
    )


def _read_token_pool(token: str, token_file: str | None) -> list[str]:
    if token_file is None:
        return [token]
    values = [line.strip() for line in open(token_file, encoding="utf-8").read().splitlines()]
    values = [value for value in values if value]
    return values or [token]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * p)
    return ordered[index]


def resolve_cold_unique_query(mode: str, explicit_unique: bool) -> bool:
    """Cold phase must use unique queries by default to avoid cache bleed."""
    if mode in {"cold", "both"}:
        return True if not explicit_unique else True
    return explicit_unique


def summarize_runs(runs: list[QueryRun], elapsed_seconds: float) -> dict[str, float | int]:
    latencies = [run.latency_ms for run in runs]
    success_count = sum(1 for run in runs if run.ok)
    cached_count = sum(1 for run in runs if run.cached)
    status_counts: dict[int, int] = {}
    error_code_counts: dict[str, int] = {}
    for run in runs:
        status_counts[run.status_code] = status_counts.get(run.status_code, 0) + 1
        if run.error_code:
            error_code_counts[run.error_code] = error_code_counts.get(run.error_code, 0) + 1

    summary: dict[str, float | int] = {
        "total_requests": len(runs),
        "success_count": success_count,
        "error_count": len(runs) - success_count,
        "success_rate_percent": round((success_count / len(runs)) * 100 if runs else 0.0, 2),
        "cached_response_percent": round((cached_count / len(runs)) * 100 if runs else 0.0, 2),
        "throughput_rps": round(len(runs) / elapsed_seconds, 2),
        "p50_ms": round(percentile(latencies, 0.50), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "p99_ms": round(percentile(latencies, 0.99), 2),
        "avg_ms": round(statistics.mean(latencies) if latencies else 0.0, 2),
    }
    for status_code, count in sorted(status_counts.items()):
        summary[f"status_{status_code}_count"] = count
    for error_code, count in sorted(error_code_counts.items()):
        summary[f"error_code_{error_code}_count"] = count
    return summary


def clear_rate_limit_counters(*, redis_url: str, key_pattern: str = "rate_limit:*") -> int:
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    keys = list(client.scan_iter(match=key_pattern, count=1000))
    if keys:
        client.delete(*keys)
    return len(keys)


def run_phase(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    total_requests: int,
    workers: int,
    unique_query_per_request: bool,
    token_pool: list[str],
) -> tuple[dict[str, float | int], list[QueryRun]]:
    runs: list[QueryRun] = []
    phase_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for index in range(total_requests):
            phase_payload = payload.copy()
            if unique_query_per_request:
                phase_payload["query"] = f"{payload['query']} [bench-{index}]"
            phase_headers = headers.copy()
            phase_headers["Authorization"] = f"Bearer {token_pool[index % len(token_pool)]}"
            futures.append(executor.submit(run_query_once, url, phase_headers, phase_payload))
        for future in as_completed(futures):
            runs.append(future.result())
    elapsed_seconds = max(time.perf_counter() - phase_start, 0.001)
    summary = summarize_runs(runs, elapsed_seconds)
    return summary, runs


def run_steady_state_phase(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    workers: int,
    duration_seconds: int,
    unique_query_per_request: bool,
    token_pool: list[str],
    request_interval_seconds: float,
) -> tuple[dict[str, float | int], list[QueryRun]]:
    runs: list[QueryRun] = []
    started = time.perf_counter()
    index = 0
    while time.perf_counter() - started < duration_seconds:
        cycle_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for _ in range(workers):
                phase_payload = payload.copy()
                if unique_query_per_request:
                    phase_payload["query"] = f"{payload['query']} [steady-{index}]"
                phase_headers = headers.copy()
                phase_headers["Authorization"] = f"Bearer {token_pool[index % len(token_pool)]}"
                futures.append(executor.submit(run_query_once, url, phase_headers, phase_payload))
                index += 1
            for future in as_completed(futures):
                runs.append(future.result())
        if request_interval_seconds > 0:
            remaining_sleep = request_interval_seconds - (time.perf_counter() - cycle_started)
            if remaining_sleep > 0:
                time.sleep(remaining_sleep)

    elapsed_seconds = max(time.perf_counter() - started, 0.001)
    summary = summarize_runs(runs, elapsed_seconds)
    summary["duration_seconds"] = duration_seconds
    return summary, runs


def main() -> int:
    parser = argparse.ArgumentParser(description="Week 3/5 query benchmark runner")
    parser.add_argument("--base-url", default="http://localhost:1000/api/v1", help="API base URL")
    parser.add_argument("--token", required=True, help="Bearer token")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    parser.add_argument("--requests", type=int, default=120, help="Total requests per phase")
    parser.add_argument("--workers", type=int, default=10, help="Parallel workers")
    parser.add_argument("--virtual-users", type=int, default=0, help="Alias for workers count")
    parser.add_argument(
        "--steady-state-seconds",
        type=int,
        default=0,
        help="Run steady-state load for the specified seconds when > 0",
    )
    parser.add_argument("--top-k", type=int, default=5, help="top_k to send")
    parser.add_argument("--query", default="what are the SLA requirements?", help="Query text")
    parser.add_argument(
        "--mode",
        choices=("cold", "warm", "both"),
        default="both",
        help="Benchmark mode for cache behavior evidence.",
    )
    parser.add_argument(
        "--warmup-requests",
        type=int,
        default=5,
        help="Warm-up requests run before warm phase.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print benchmark configuration only (no HTTP calls).",
    )
    parser.add_argument(
        "--unique-query-per-request",
        action="store_true",
        help="Legacy flag. Cold phase now enforces unique queries by default for deterministic cache isolation.",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="Optional path to newline-delimited bearer tokens (round-robin per request).",
    )
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=0.0,
        help="Optional delay target per VU cycle in steady-state mode (0 for no pacing).",
    )
    parser.add_argument(
        "--rate-limit-reset",
        action="store_true",
        help="Clear Redis rate_limit:* counters before benchmark execution.",
    )
    parser.add_argument(
        "--rate-limit-reset-between-phases",
        action="store_true",
        help="Clear Redis rate_limit:* counters between cold and warm phases (mode=both).",
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("AKS_REDIS_URL", "redis://localhost:1010/0"),
        help="Redis URL for optional benchmark rate-limit counter resets.",
    )
    args = parser.parse_args()

    url = f"{args.base_url}/queries"
    headers = {
        "Authorization": f"Bearer {args.token}",
        "X-Tenant-Id": args.tenant_id,
        "Content-Type": "application/json",
    }
    payload: dict[str, object] = {
        "query": args.query,
        "top_k": args.top_k,
        "filters": {},
    }
    cold_unique_query = resolve_cold_unique_query(args.mode, args.unique_query_per_request)
    if args.dry_run:
        report = {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "benchmark": "week3_queries",
            "dry_run": True,
            "mode": args.mode,
            "runtime_profile": {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "workers": args.workers,
                "virtual_users": (args.virtual_users if args.virtual_users > 0 else args.workers),
                "requests_per_phase": args.requests,
                "steady_state_seconds": args.steady_state_seconds,
                "top_k": args.top_k,
                "token_file": args.token_file,
                "cold_phase_unique_query_per_request": cold_unique_query,
                "request_interval_seconds": args.request_interval_seconds,
                "rate_limit_reset": args.rate_limit_reset,
                "rate_limit_reset_between_phases": args.rate_limit_reset_between_phases,
                "redis_url": args.redis_url,
            },
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    token_pool = _read_token_pool(args.token, args.token_file)
    workers = args.virtual_users if args.virtual_users > 0 else args.workers
    rate_limit_keys_deleted = 0
    if args.rate_limit_reset:
        rate_limit_keys_deleted += clear_rate_limit_counters(redis_url=args.redis_url)

    phases: dict[str, dict[str, float | int]] = {}
    if args.mode in {"cold", "both"}:
        if args.steady_state_seconds > 0:
            cold_summary, _ = run_steady_state_phase(
                url=url,
                headers=headers,
                payload=payload,
                workers=workers,
                duration_seconds=args.steady_state_seconds,
                unique_query_per_request=cold_unique_query,
                token_pool=token_pool,
                request_interval_seconds=args.request_interval_seconds,
            )
        else:
            cold_summary, _ = run_phase(
                url=url,
                headers=headers,
                payload=payload,
                total_requests=args.requests,
                workers=workers,
                unique_query_per_request=cold_unique_query,
                token_pool=token_pool,
            )
        phases["cold_cache"] = cold_summary
        if args.mode == "both" and args.rate_limit_reset_between_phases:
            rate_limit_keys_deleted += clear_rate_limit_counters(redis_url=args.redis_url)

    if args.mode in {"warm", "both"}:
        for _ in range(args.warmup_requests):
            run_query_once(url, headers, payload)
        if args.steady_state_seconds > 0:
            warm_summary, _ = run_steady_state_phase(
                url=url,
                headers=headers,
                payload=payload,
                workers=workers,
                duration_seconds=args.steady_state_seconds,
                unique_query_per_request=False,
                token_pool=token_pool,
                request_interval_seconds=args.request_interval_seconds,
            )
        else:
            warm_summary, _ = run_phase(
                url=url,
                headers=headers,
                payload=payload,
                total_requests=args.requests,
                workers=workers,
                unique_query_per_request=False,
                token_pool=token_pool,
            )
        phases["warm_cache"] = warm_summary

    report = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "benchmark": "week3_queries",
        "mode": args.mode,
        "runtime_profile": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "workers": workers,
            "requests_per_phase": args.requests,
            "steady_state_seconds": args.steady_state_seconds,
            "top_k": args.top_k,
            "cold_phase_unique_query_per_request": cold_unique_query,
            "request_interval_seconds": args.request_interval_seconds,
            "rate_limit_reset": args.rate_limit_reset,
            "rate_limit_reset_between_phases": args.rate_limit_reset_between_phases,
            "redis_url": args.redis_url,
            "rate_limit_keys_deleted": rate_limit_keys_deleted,
        },
        "results": phases,
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
