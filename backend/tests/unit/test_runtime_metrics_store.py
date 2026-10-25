from __future__ import annotations

import pytest
import redis

from app.system.services import metrics_service

pytestmark = pytest.mark.unit_no_db


class FakeRuntimeMetricsRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_writes = False
        self.published = 0

    def eval(self, _script: str, key_count: int, *args: object) -> int:
        if self.fail_writes:
            raise redis.ConnectionError("test Redis unavailable")
        counter_name = str(args[key_count])
        amount = int(str(args[key_count + 1]))
        started_at = str(args[key_count + 2])
        incomplete = str(args[key_count + 3])
        next_value = int(self.values.get(counter_name, "0")) + amount
        self.values[counter_name] = str(next_value)
        self.values.setdefault("meta:started_at", started_at)
        self.values.setdefault("meta:complete", "1")
        if incomplete == "1":
            self.values["meta:complete"] = "0"
        self.published += 1
        return next_value

    def hsetnx(self, _key: str, field: str, value: str) -> int:
        if field in self.values:
            return 0
        self.values[field] = value
        return 1

    def hgetall(self, _key: str) -> dict[str, str]:
        return dict(self.values)


@pytest.fixture
def runtime_metrics_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRuntimeMetricsRedis:
    client = FakeRuntimeMetricsRedis()
    monkeypatch.setattr(metrics_service, "get_runtime_metrics_redis_client", lambda: client)
    monkeypatch.setattr(metrics_service, "_runtime_metrics_write_incomplete", False)
    monkeypatch.setattr(metrics_service, "_runtime_metrics_write_warning_logged", False)
    return client


def test_shared_summary_uses_integer_counter_fields_not_prometheus_timestamps(
    runtime_metrics_redis: FakeRuntimeMetricsRedis,
) -> None:
    metrics_service.increment_runtime_metric("deepspace_mcp_result_references_total", 3)
    metrics_service.increment_runtime_metric("deepspace_canary_mismatches_total")

    summary = metrics_service.read_runtime_metrics_summary()

    assert summary["deepspace_mcp_result_references_total"] == 3
    assert summary["deepspace_canary_mismatches_total"] == 1
    assert summary["api_requests_total"] == 0
    assert summary["metrics_scope"] == "service-wide"
    assert summary["metrics_complete"] is True
    assert summary["metrics_started_at"]
    assert runtime_metrics_redis.published == 2


def test_worker_retry_helpers_update_the_shared_total(
    runtime_metrics_redis: FakeRuntimeMetricsRedis,
) -> None:
    metrics_service.increment_worker_retry(stage="deepspace_library_file_extract")
    metrics_service.increment_worker_dead_letter(stage="deepspace_library_file_extract")

    summary = metrics_service.read_runtime_metrics_summary()

    assert summary["worker_retries_total"] == 1
    assert summary["worker_dead_letters_total"] == 1


def test_failed_shared_write_marks_later_snapshots_incomplete(
    runtime_metrics_redis: FakeRuntimeMetricsRedis,
) -> None:
    runtime_metrics_redis.fail_writes = True
    assert metrics_service.increment_runtime_metric("api_requests_total") is False

    runtime_metrics_redis.fail_writes = False
    assert metrics_service.increment_runtime_metric("api_requests_total") is True

    summary = metrics_service.read_runtime_metrics_summary()
    assert summary["api_requests_total"] == 1
    assert summary["metrics_complete"] is False


def test_invalid_runtime_counter_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported runtime metric"):
        metrics_service.increment_runtime_metric("tenant_email_addresses_total")

    with pytest.raises(ValueError, match="positive integers"):
        metrics_service.increment_runtime_metric("api_requests_total", 0)


def test_runtime_metric_write_fails_open_if_redis_client_cannot_be_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_invalid_redis_url() -> None:
        raise ValueError("invalid Redis URL")

    monkeypatch.setattr(
        metrics_service, "get_runtime_metrics_redis_client", raise_invalid_redis_url
    )
    monkeypatch.setattr(metrics_service, "_runtime_metrics_write_incomplete", False)
    monkeypatch.setattr(metrics_service, "_runtime_metrics_write_warning_logged", True)

    assert metrics_service.increment_runtime_metric("api_requests_total") is False
    assert metrics_service._runtime_metrics_write_incomplete is True


def test_corrupt_shared_counter_does_not_render_as_zero(
    runtime_metrics_redis: FakeRuntimeMetricsRedis,
) -> None:
    runtime_metrics_redis.values["api_requests_total"] = "1792342829.0"

    with pytest.raises(metrics_service.RuntimeMetricsUnavailableError, match="invalid"):
        metrics_service.read_runtime_metrics_summary()


def test_corrupt_tracking_metadata_does_not_render_as_complete(
    runtime_metrics_redis: FakeRuntimeMetricsRedis,
) -> None:
    runtime_metrics_redis.values["meta:complete"] = "unknown"

    with pytest.raises(
        metrics_service.RuntimeMetricsUnavailableError,
        match="metadata is invalid",
    ):
        metrics_service.read_runtime_metrics_summary()
