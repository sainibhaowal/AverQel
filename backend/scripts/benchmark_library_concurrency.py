#!/usr/bin/env python3
"""Bounded authenticated concurrency smoke test for heavy Library APIs."""

from __future__ import annotations

import argparse
import json
import platform
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import requests  # type: ignore[import-untyped]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:1000/api/v1")
    parser.add_argument("--token", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--file-id", required=True)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.requests < 1 or args.requests > 10_000 or args.workers < 1 or args.workers > 100:
        parser.error("requests must be 1..10000 and workers must be 1..100")
    report = {
        "benchmark": "library_concurrency",
        "generated_at": datetime.now(UTC).isoformat(),
        "dry_run": args.dry_run,
        "runtime": platform.python_version(),
        "requests": args.requests,
        "workers": args.workers,
    }
    if args.dry_run:
        print(json.dumps(report))
        return 0
    url = f"{args.base_url}/deepspace/library/{args.conversation_id}/files/{args.file_id}/csv-page"
    headers = {"Authorization": f"Bearer {args.token}", "X-Tenant-Id": args.tenant_id}
    start = time.perf_counter()

    def request_page(index: int) -> tuple[int, float]:
        request_start = time.perf_counter()
        response = requests.get(
            url, headers=headers, params={"offset": index * 200, "limit": 200}, timeout=args.timeout
        )
        response.raise_for_status()
        return response.status_code, (time.perf_counter() - request_start) * 1000

    latencies: list[float] = []
    statuses: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(request_page, index) for index in range(args.requests)]
        for future in as_completed(futures):
            status, latency = future.result()
            statuses[str(status)] = statuses.get(str(status), 0) + 1
            latencies.append(latency)
    elapsed = max(time.perf_counter() - start, 0.001)
    latencies.sort()
    report.update(
        {
            "success_count": len(latencies),
            "throughput_rps": round(len(latencies) / elapsed, 2),
            "p50_ms": round(latencies[len(latencies) // 2], 2) if latencies else 0,
            "p95_ms": (
                round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))], 2)
                if latencies
                else 0
            ),
            "statuses": statuses,
        }
    )
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
