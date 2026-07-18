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
