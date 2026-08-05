from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_week3_queries.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("benchmark_week3_queries", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dry_run_reports_cold_unique_default_enabled() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--token",
            "dummy",
            "--tenant-id",
            "00000000-0000-7000-8000-000000000001",
            "--mode",
            "cold",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    profile = payload["runtime_profile"]
    assert profile["cold_phase_unique_query_per_request"] is True
    assert profile["request_interval_seconds"] == 0.0
    assert profile["rate_limit_reset"] is False
    assert profile["rate_limit_reset_between_phases"] is False


def test_summarize_runs_includes_status_and_error_code_counters() -> None:
    module = _load_module()
    runs = [
        module.QueryRun(latency_ms=10.0, ok=True, cached=False, status_code=200, error_code=None),
        module.QueryRun(
            latency_ms=12.5,
            ok=False,
            cached=False,
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
        ),
        module.QueryRun(
            latency_ms=8.2,
            ok=False,
            cached=False,
            status_code=503,
            error_code="PROVIDER_CIRCUIT_OPEN",
        ),
    ]

    summary = module.summarize_runs(runs, elapsed_seconds=1.0)

    assert summary["total_requests"] == 3
    assert summary["success_count"] == 1
    assert summary["error_count"] == 2
    assert summary["status_200_count"] == 1
    assert summary["status_429_count"] == 1
    assert summary["status_503_count"] == 1
    assert summary["error_code_RATE_LIMIT_EXCEEDED_count"] == 1
    assert summary["error_code_PROVIDER_CIRCUIT_OPEN_count"] == 1
