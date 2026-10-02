from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_deepspace_latency_benchmark_dry_run_is_safe() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_deepspace_latency.py",
            "--token",
            "test-token",
            "--tenant-id",
            "test-tenant",
            "--dry-run",
        ],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["benchmark"] == "deepspace_latency_observed_summary"
    assert payload["dry_run"] is True


def test_deepspace_latency_benchmark_dry_run_does_not_enable_streaming() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_deepspace_latency.py",
            "--token",
            "test-token",
            "--tenant-id",
            "test-tenant",
            "--stream",
            "--dry-run",
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "--allow-staging" in completed.stderr
