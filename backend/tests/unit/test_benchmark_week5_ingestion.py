from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "benchmark_week5_ingestion.py"
)


def test_dry_run_reports_status_worker_profile() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--token",
            "dummy",
            "--tenant-id",
            "00000000-0000-7000-8000-000000000001",
            "--documents",
            "10",
            "--workers",
            "3",
            "--status-workers",
            "7",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    profile = payload["runtime_profile"]
    assert profile["workers"] == 3
    assert profile["status_workers"] == 7
