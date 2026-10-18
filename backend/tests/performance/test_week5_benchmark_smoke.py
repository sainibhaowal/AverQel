from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise AssertionError("benchmark output must be a JSON object")
    return payload


def test_query_benchmark_script_smoke() -> None:
    payload = _run_script(
        "scripts/benchmark_week3_queries.py",
        "--token",
        "benchmark-token",
        "--tenant-id",
        "00000000-0000-0000-0000-000000000001",
        "--dry-run",
    )
    assert payload["benchmark"] == "week3_queries"
    assert payload["dry_run"] is True


def test_ingestion_benchmark_script_smoke() -> None:
    payload = _run_script(
        "scripts/benchmark_week5_ingestion.py",
        "--token",
        "benchmark-token",
        "--tenant-id",
        "00000000-0000-0000-0000-000000000001",
        "--dry-run",
    )
    assert payload["benchmark"] == "week5_ingestion"
    assert payload["dry_run"] is True


def test_library_concurrency_benchmark_smoke() -> None:
    payload = _run_script(
        "scripts/benchmark_library_concurrency.py",
        "--token",
        "benchmark-token",
        "--tenant-id",
        "00000000-0000-0000-0000-000000000001",
        "--conversation-id",
        "00000000-0000-0000-0000-000000000002",
        "--file-id",
        "00000000-0000-0000-0000-000000000003",
        "--dry-run",
    )
    assert payload["benchmark"] == "library_concurrency"
    assert payload["dry_run"] is True


def test_staging_durable_load_dry_run_is_safe() -> None:
    payload = _run_script(
        "scripts/staging_durable_load.py",
        "--dry-run",
        "--provider-mode",
        "mock",
    )
    assert payload["benchmark"] == "staging_durable_load"
    assert payload["dry_run"] is True


def test_staging_durable_load_refuses_non_loopback_without_explicit_opt_in() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/staging_durable_load.py",
            "--base-url",
            "https://staging.example.invalid",
            "--dry-run",
            "--provider-mode",
            "mock",
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "--allow-staging" in completed.stderr
