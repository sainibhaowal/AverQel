#!/usr/bin/env python3
"""Read-only DeepSpace latency benchmark for localhost or approved staging."""

from __future__ import annotations

import argparse
import json
import socket
import statistics
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests  # type: ignore[import-untyped]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:1000/api/v1")
    parser.add_argument("--token", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--allow-staging", action="store_true")
    parser.add_argument(
        "--stream", action="store_true", help="Run an explicitly opted-in staging stream"
    )
    parser.add_argument("--write-staging-data", action="store_true")
    parser.add_argument("--prompt", default="Return exactly BENCHMARK_OK.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    max_requests = 10 if args.stream else 100
    if args.requests < 1 or args.requests > max_requests:
        parser.error(f"requests must be 1..{max_requests}")
    parsed = urlparse(args.base_url)
    host = parsed.hostname or ""
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if args.stream and not args.prompt.strip():
        parser.error("--stream requires a non-empty synthetic --prompt")
    if args.stream and (not args.allow_staging or not args.write_staging_data):
        parser.error("--stream requires --allow-staging and --write-staging-data")
    if (
        args.stream
        and host not in local_hosts
        and any(marker in host.lower() for marker in ("prod", "production", "live"))
    ):
        parser.error("stream benchmarks are refused for production-like hosts")
    if not args.dry_run and host not in local_hosts and not args.allow_staging:
        parser.error("non-local benchmarks require --allow-staging and an approved staging URL")

    report: dict[str, object] = {
        "benchmark": "deepspace_latency_observed_summary",
        "generated_at": datetime.now(UTC).isoformat(),
        "dry_run": args.dry_run,
        "requests": args.requests,
        "endpoint": "/deepspace/chats/operational-summary",
        "hostname": socket.gethostname() if args.dry_run else host,
        "mode": "stream" if args.stream else "observed_summary",
    }
    if args.dry_run:
        print(json.dumps(report))
        return 0

    headers = {"Authorization": f"Bearer {args.token}", "X-Tenant-Id": args.tenant_id}
    latencies: list[float] = []
    summaries: list[dict[str, object]] = []
    url = f"{args.base_url.rstrip('/')}/deepspace/chats/operational-summary"
    if args.stream:
        stream_url = f"{args.base_url.rstrip('/')}/deepspace/chats/stream"
        stream_results: list[dict[str, object]] = []
        for _ in range(args.requests):
            started = time.perf_counter()
            first_event_ms: float | None = None
            event_count = 0
            response = requests.post(
                stream_url,
                headers={**headers, "Accept": "text/event-stream"},
                json={"message": args.prompt, "client_request_id": f"benchmark-{uuid.uuid4().hex}"},
                timeout=args.timeout,
                stream=True,
            )
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("event:"):
                    continue
                event_count += 1
                event_name = line[6:].strip()
                if first_event_ms is None and event_name in {"delta", "model_message", "thinking"}:
                    first_event_ms = (time.perf_counter() - started) * 1000
            total_ms = (time.perf_counter() - started) * 1000
            stream_results.append(
                {
                    "status_code": response.status_code,
                    "event_count": event_count,
                    "time_to_first_event_ms": (
                        round(first_event_ms, 2) if first_event_ms is not None else None
                    ),
                    "total_ms": round(total_ms, 2),
                }
            )
        report["stream_results"] = stream_results
        print(json.dumps(report))
        return 0

    for _ in range(args.requests):
        started = time.perf_counter()
        response = requests.get(url, headers=headers, timeout=args.timeout)
        response.raise_for_status()
        latencies.append((time.perf_counter() - started) * 1000)
        payload = response.json()
        if isinstance(payload, dict):
            summaries.append(payload)

    ordered = sorted(latencies)
    report.update(
        {
            "transport_p50_ms": round(statistics.median(latencies), 2),
            "transport_p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 2),
            "observed_turn_summary": summaries[-1] if summaries else {},
        }
    )
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
