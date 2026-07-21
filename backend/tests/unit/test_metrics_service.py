from __future__ import annotations

import pytest

from app.system.services.metrics_service import (
    metrics_payload,
    observe_db_query,
    observe_worker_stage,
)


def test_metrics_payload_returns_prometheus_tuple() -> None:
    payload, content_type = metrics_payload()
    assert isinstance(payload, bytes)
    assert isinstance(content_type, str)
    assert "text/plain" in content_type


def test_observe_db_query_success_and_error_paths() -> None:
    with observe_db_query("unit-ok"):
        pass

    with pytest.raises(RuntimeError):
        with observe_db_query("unit-error"):
            raise RuntimeError("boom")


def test_observe_worker_stage_success_and_error_paths() -> None:
    with observe_worker_stage("stage-ok"):
        pass

    with pytest.raises(ValueError):
        with observe_worker_stage("stage-error"):
            raise ValueError("boom")
