#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import platform
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests  # type: ignore[import-untyped]
from build_week5_benchmark_dataset import build_dataset

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


@dataclass(slots=True)
class UploadRun:
    accepted: bool
    upload_latency_ms: float
    document_id: str | None
    ingestion_job_id: str | None
    status_code: int
    error_code: str | None
    poll_token: str


@dataclass(slots=True)
class PollRun:
    status: str
    latency_ms: float
    attempts: int
    last_http_status: int


def _read_token_pool(token: str, token_file: str | None) -> list[str]:
    tokens = [token]
    if token_file:
        values = [
            line.strip() for line in Path(token_file).read_text(encoding="utf-8").splitlines()
        ]
        values = [value for value in values if value]
        if values:
            tokens = values
    return tokens


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * p)
    return ordered[index]


def upload_once(
    *,
    base_url: str,
    token: str,
    tenant_id: str,
    file_path: Path,
    timeout_seconds: int,
) -> UploadRun:
    url = f"{base_url}/documents/upload"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": tenant_id,
        "Idempotency-Key": str(uuid.uuid4()),
    }
    start = time.perf_counter()
    content_type, _ = mimetypes.guess_type(file_path.name)
    if content_type is None:
        content_type = "application/octet-stream"
    with file_path.open("rb") as handle:
        response = requests.post(
            url,
            headers=headers,
            files={"file": (file_path.name, handle, content_type)},
            timeout=timeout_seconds,
        )
    latency_ms = (time.perf_counter() - start) * 1000
    if response.status_code != 200:
        error_code: str | None = None
        try:
            error_code = (response.json().get("error") or {}).get("code")
        except Exception:  # noqa: BLE001
            error_code = None
        return UploadRun(
            accepted=False,
            upload_latency_ms=latency_ms,
            document_id=None,
            ingestion_job_id=None,
            status_code=response.status_code,
            error_code=error_code,
            poll_token=token,
        )
    payload = response.json()
    return UploadRun(
        accepted=True,
        upload_latency_ms=latency_ms,
        document_id=str(payload.get("document_id", "")) or None,
        ingestion_job_id=str(payload.get("ingestion_job_id", "")) or None,
        status_code=response.status_code,
        error_code=None,
        poll_token=token,
    )


def poll_document_status(
    *,
    base_url: str,
    token: str,
    tenant_id: str,
    document_id: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
    request_timeout_seconds: int,
) -> PollRun:
    status_url = f"{base_url}/documents/{document_id}/status"
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": tenant_id}
    start = time.perf_counter()
    attempts = 0
    last_http_status = 0
    while time.perf_counter() - start <= timeout_seconds:
        attempts += 1
        response = requests.get(status_url, headers=headers, timeout=request_timeout_seconds)
        last_http_status = response.status_code
        if response.status_code == 200:
            payload = response.json()
            status = str(payload.get("status", "unknown"))
            if status in {"indexed", "failed", "dead_lettered"}:
                return PollRun(
                    status=status,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    attempts=attempts,
                    last_http_status=response.status_code,
                )
        time.sleep(poll_interval_seconds)
    return PollRun(
        status="timeout",
        latency_ms=timeout_seconds * 1000,
        attempts=attempts,
        last_http_status=last_http_status,
    )


def _chunked(items: list[Path], size: int) -> list[list[Path]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Week 5 ingestion benchmark runner")
    parser.add_argument("--base-url", default="http://localhost:1000/api/v1", help="API base URL")
    parser.add_argument("--token", required=True, help="Bearer token")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    parser.add_argument("--documents", type=int, default=20, help="Number of uploads")
    parser.add_argument("--workers", type=int, default=5, help="Parallel upload workers")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for uploads")
    parser.add_argument(
        "--dataset-dir",
        default="tmp/week5_benchmark_dataset",
        help="Directory containing benchmark corpus files. Generated if missing.",
    )
    parser.add_argument(
        "--target-pages-total",
        type=int,
        default=5000,
        help="Target estimated pages for generated corpus profile.",
    )
    parser.add_argument(
        "--status-timeout-seconds",
        type=int,
        default=180,
        help="Timeout while waiting for indexed/failed terminal status per doc",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=30,
        help="Per-request timeout for HTTP calls",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=1.0,
        help="Polling interval for ingestion status",
    )
    parser.add_argument(
        "--status-workers",
        type=int,
        default=10,
        help="Max parallel workers for status polling.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print benchmark configuration only (no HTTP calls).",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="Optional path to newline-delimited bearer tokens (round-robin per request).",
    )
    args = parser.parse_args()

    if args.dry_run:
        dry_report = {
            "benchmark": "week5_ingestion",
            "dry_run": True,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "runtime_profile": {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "documents": args.documents,
                "workers": args.workers,
                "status_workers": args.status_workers,
                "batch_size": args.batch_size,
                "dataset_dir": args.dataset_dir,
                "token_file": args.token_file,
            },
        }
        print(json.dumps(dry_report, indent=2, sort_keys=True))
        return 0

    token_pool = _read_token_pool(args.token, args.token_file)
    dataset_dir = Path(args.dataset_dir)
    manifest = build_dataset(
        output_dir=dataset_dir,
        documents=args.documents,
        target_pages_total=args.target_pages_total,
    )
    corpus = sorted(
        [
            path
            for path in dataset_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".txt", ".md", ".pdf"}
        ]
    )
    if len(corpus) < args.documents:
        raise SystemExit(
            f"Expected at least {args.documents} corpus files in {dataset_dir}, got {len(corpus)}"
        )
    corpus = corpus[: args.documents]
    upload_runs: list[UploadRun] = []
    upload_start = time.perf_counter()
    for batch_index, batch in enumerate(_chunked(corpus, max(1, args.batch_size))):
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            upload_futures = [
                executor.submit(
                    upload_once,
                    base_url=args.base_url,
                    token=token_pool[
                        (batch_index * max(1, args.batch_size) + index) % len(token_pool)
                    ],
                    tenant_id=args.tenant_id,
                    file_path=file_path,
                    timeout_seconds=args.request_timeout_seconds,
                )
                for index, file_path in enumerate(batch)
            ]
            for future in as_completed(upload_futures):
                upload_runs.append(future.result())
    upload_elapsed = max(time.perf_counter() - upload_start, 0.001)

    accepted = [run for run in upload_runs if run.accepted and run.document_id]
    terminal_statuses: list[PollRun] = []
    with ThreadPoolExecutor(
        max_workers=max(1, min(args.status_workers, len(accepted)))
    ) as executor:
        poll_futures: list[Future[PollRun]] = []
        for run in accepted:
            if run.document_id is None:
                continue
            poll_futures.append(
                executor.submit(
                    poll_document_status,
                    base_url=args.base_url,
                    token=run.poll_token,
                    tenant_id=args.tenant_id,
                    document_id=run.document_id,
                    timeout_seconds=args.status_timeout_seconds,
                    poll_interval_seconds=args.poll_interval_seconds,
                    request_timeout_seconds=args.request_timeout_seconds,
                )
            )
        for poll_future in as_completed(poll_futures):
            terminal_statuses.append(poll_future.result())

    upload_latencies = [run.upload_latency_ms for run in upload_runs]
    ingestion_latencies = [run.latency_ms for run in terminal_statuses]
    indexed_count = sum(1 for run in terminal_statuses if run.status == "indexed")
    failed_count = sum(1 for run in terminal_statuses if run.status == "failed")
    dead_letter_count = sum(1 for run in terminal_statuses if run.status == "dead_lettered")
    timeout_count = sum(1 for run in terminal_statuses if run.status == "timeout")
    upload_status_counts: dict[int, int] = {}
    upload_error_code_counts: dict[str, int] = {}
    for run in upload_runs:
        upload_status_counts[run.status_code] = upload_status_counts.get(run.status_code, 0) + 1
        if run.error_code:
            upload_error_code_counts[run.error_code] = (
                upload_error_code_counts.get(run.error_code, 0) + 1
            )

    total = len(upload_runs)
    success_rate = (indexed_count / total) * 100 if total else 0.0
    accepted_rate = (len(accepted) / total) * 100 if total else 0.0
    report = {
        "benchmark": "week5_ingestion",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "runtime_profile": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "documents": args.documents,
            "workers": args.workers,
            "status_workers": args.status_workers,
            "batch_size": args.batch_size,
            "dataset_dir": str(dataset_dir),
            "dataset_profile": manifest["dataset_profile"],
        },
        "summary": {
            "total_upload_attempts": total,
            "accepted_uploads": len(accepted),
            "accepted_rate_percent": round(accepted_rate, 2),
            "indexed_count": indexed_count,
            "failed_count": failed_count,
            "dead_lettered_count": dead_letter_count,
            "timeout_count": timeout_count,
            "indexing_success_rate_percent": round(success_rate, 2),
            "upload_throughput_rps": round(total / upload_elapsed, 2),
            "avg_status_poll_attempts": round(
                (
                    (sum(run.attempts for run in terminal_statuses) / len(terminal_statuses))
                    if terminal_statuses
                    else 0.0
                ),
                2,
            ),
        },
        "upload_latency_ms": {
            "p50": round(percentile(upload_latencies, 0.50), 2),
            "p95": round(percentile(upload_latencies, 0.95), 2),
            "p99": round(percentile(upload_latencies, 0.99), 2),
        },
        "end_to_index_latency_ms": {
            "p50": round(percentile(ingestion_latencies, 0.50), 2),
            "p95": round(percentile(ingestion_latencies, 0.95), 2),
            "p99": round(percentile(ingestion_latencies, 0.99), 2),
        },
        "diagnostics": {
            "upload_status_counts": {
                str(key): value for key, value in sorted(upload_status_counts.items())
            },
            "upload_error_code_counts": {
                key: value for key, value in sorted(upload_error_code_counts.items())
            },
            "poll_last_http_status_counts": {
                str(code): sum(1 for run in terminal_statuses if run.last_http_status == code)
                for code in sorted({run.last_http_status for run in terminal_statuses})
            },
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
