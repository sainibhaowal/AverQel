from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.ingestion.services.ingestion_service import RetryableIngestionError
from app.ingestion.workers import tasks as tasks_ingestion
from app.integrations.workers import tasks_connectors
from app.system.workers import tasks_maintenance


class _DummyCounter:
    def labels(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return self

    def inc(self) -> None:
        return None

    def observe(self, value: float) -> None:
        _ = value
        return None


class _RecordingCounter(_DummyCounter):
    def __init__(self) -> None:
        self.count = 0

    def inc(self) -> None:
        self.count += 1


class _FakeSession:
    def __init__(
        self,
        *,
        rollback_raises: bool = False,
        reset_raises: bool = False,
        rollback_after_reset_raises: bool = False,
    ) -> None:
        self._rollback_raises = rollback_raises
        self._reset_raises = reset_raises
        self._rollback_after_reset_raises = rollback_after_reset_raises
        self._rollback_calls = 0

    def execute(self, stmt, params=None):  # type: ignore[no-untyped-def]
        _ = params
        if "RESET ROLE" in str(stmt) and self._reset_raises:
            raise RuntimeError("reset failed")
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        self._rollback_calls += 1
        if self._rollback_calls == 1 and self._rollback_raises:
            raise RuntimeError("rollback failed")
        if self._rollback_calls >= 2 and self._rollback_after_reset_raises:
            raise RuntimeError("rollback-after-reset failed")

    def close(self) -> None:
        return None


@dataclass
class _FakeSettings:
    ingestion_max_attempts: int = 3
    audit_log_retention_days: int = 90
    transient_record_retention_days: int = 30


class _FakeIngestionService:
    def __init__(self, db, settings):  # type: ignore[no-untyped-def]
        _ = (db, settings)

    def process_ingestion_job(self, *, tenant_id, job_id):  # type: ignore[no-untyped-def]
        _ = (tenant_id, job_id)
        return None

    def compute_retry_delay(self, *, current_attempt: int) -> int:
        _ = current_attempt
        return 7


class _RetryIngestionService(_FakeIngestionService):
    def process_ingestion_job(self, *, tenant_id, job_id):  # type: ignore[no-untyped-def]
        _ = (tenant_id, job_id)
        raise RetryableIngestionError("retry")


class _FakeCursorResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _FakeScalarResult:
    def __init__(self, values) -> None:  # type: ignore[no-untyped-def]
        self._values = values

    def all(self):  # type: ignore[no-untyped-def]
        return list(self._values)


class _FakeRowResult:
    def __init__(self, row) -> None:  # type: ignore[no-untyped-def]
        self._row = row

    def first(self):  # type: ignore[no-untyped-def]
        return self._row


class _FakeConnectorSession(_FakeSession):
    def __init__(
        self,
        connector,
        integration,
        *,
        advisory_lock_available: bool = True,
        rollback_raises: bool = False,
        reset_raises: bool = False,
        close_raises: bool = False,
    ) -> None:  # type: ignore[no-untyped-def]
        super().__init__(
            rollback_raises=rollback_raises,
            reset_raises=reset_raises,
        )
        self.connector = connector
        self.integration = integration
        self.expired = False
        self.advisory_lock_available = advisory_lock_available
        self.lock_released = False
        self._close_raises = close_raises
        self.closed = False

    def execute(self, stmt, params=None):  # type: ignore[no-untyped-def]
        _ = params
        text_stmt = str(stmt)
        if "RESET ROLE" in text_stmt or "SET ROLE" in text_stmt:
            return None
        if "pg_try_advisory_lock" in text_stmt:
            return SimpleNamespace(scalar=lambda: self.advisory_lock_available)
        if "pg_advisory_unlock" in text_stmt:
            self.lock_released = True
            return SimpleNamespace(scalar=lambda: True)
        if "FROM connectors" in text_stmt and "connectors.id" in text_stmt:
            return _FakeRowResult((self.connector, self.integration))
        if "SELECT connectors.id" in text_stmt:
            return SimpleNamespace(
                scalars=lambda: _FakeScalarResult([self.connector.id])
            )
        return None

    def expire_all(self) -> None:
        self.expired = True

    def get(self, model, identifier):  # type: ignore[no-untyped-def]
        _ = model
        if identifier == self.connector.id:
            return self.connector
        return None

    def close(self) -> None:
        self.closed = True
        if self._close_raises:
            raise RuntimeError("close failed")


def test_ingestion_ping() -> None:
    assert tasks_ingestion.ingestion_ping() == "ok"


def test_process_ingestion_job_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tasks_ingestion, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(
        tasks_ingestion, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_ingestion, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(tasks_ingestion, "IngestionService", _FakeIngestionService)
    monkeypatch.setattr(
        tasks_ingestion, "get_session_factory", lambda: (lambda: _FakeSession())
    )

    task_obj = tasks_ingestion.process_ingestion_job
    monkeypatch.setattr(task_obj, "retry", lambda **kwargs: None, raising=False)
    run_fn = tasks_ingestion.process_ingestion_job.__wrapped__
    task_obj.push_request(retries=0)
    try:
        assert (
            run_fn(
                "11111111-1111-7111-8111-111111111111",
                "22222222-2222-7222-8222-222222222222",
            )
            == "ok"
        )
    finally:
        task_obj.pop_request()


def test_process_ingestion_job_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tasks_ingestion, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(
        tasks_ingestion, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_ingestion, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(tasks_ingestion, "IngestionService", _RetryIngestionService)
    monkeypatch.setattr(
        tasks_ingestion, "get_session_factory", lambda: (lambda: _FakeSession())
    )

    def _retry(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"retry-called:{kwargs['countdown']}")

    task_obj = tasks_ingestion.process_ingestion_job
    monkeypatch.setattr(task_obj, "retry", _retry, raising=False)
    run_fn = tasks_ingestion.process_ingestion_job.__wrapped__
    task_obj.push_request(retries=1)
    with pytest.raises(RuntimeError, match="retry-called:7"):
        run_fn(
            "11111111-1111-7111-8111-111111111111",
            "22222222-2222-7222-8222-222222222222",
        )
    task_obj.pop_request()


def test_process_ingestion_job_cleanup_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_ingestion, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(
        tasks_ingestion, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_ingestion, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(tasks_ingestion, "IngestionService", _FakeIngestionService)
    monkeypatch.setattr(
        tasks_ingestion,
        "get_session_factory",
        lambda: (
            lambda: _FakeSession(
                rollback_raises=True,
                reset_raises=True,
                rollback_after_reset_raises=True,
            )
        ),
    )
    task_obj = tasks_ingestion.process_ingestion_job
    monkeypatch.setattr(task_obj, "retry", lambda **kwargs: None, raising=False)
    run_fn = tasks_ingestion.process_ingestion_job.__wrapped__
    task_obj.push_request(retries=0)
    try:
        assert (
            run_fn(
                "11111111-1111-7111-8111-111111111111",
                "22222222-2222-7222-8222-222222222222",
            )
            == "ok"
        )
    finally:
        task_obj.pop_request()


def test_run_connector_sync_task_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(
        tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "get_settings", lambda: _FakeSettings())

    connector = SimpleNamespace(
        id=uuid.UUID("11111111-1111-7111-8111-111111111111"),
        tenant_id=uuid.UUID("22222222-2222-7222-8222-222222222222"),
        config={},
    )
    integration = SimpleNamespace(slug="github")
    session = _FakeConnectorSession(connector, integration)

    monkeypatch.setattr(
        tasks_connectors,
        "get_session_factory",
        lambda: (lambda: session),
    )

    class _FakeOrchestrator:
        def __init__(self, _session):  # type: ignore[no-untyped-def]
            pass

        def sync_connector(self, connector_id, tenant_id, attempt=1):  # type: ignore[no-untyped-def]
            assert connector_id == connector.id
            assert tenant_id == connector.tenant_id
            assert attempt == 1
            return {"status": "success", "document_id": "doc-1"}

    monkeypatch.setattr(tasks_connectors, "ConnectorOrchestrator", _FakeOrchestrator)

    task_obj = tasks_connectors.run_connector_sync_task
    run_fn = task_obj.__wrapped__
    task_obj.push_request(retries=0)
    try:
        assert run_fn(str(connector.id)) == "success"
    finally:
        task_obj.pop_request()


def test_run_connector_sync_task_passes_retry_attempt_to_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(
        tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "get_settings", lambda: _FakeSettings())

    connector = SimpleNamespace(
        id=uuid.UUID("13131313-1313-7313-8313-131313131313"),
        tenant_id=uuid.UUID("35353535-3535-7535-8535-353535353535"),
        config={},
    )
    integration = SimpleNamespace(slug="github")
    session = _FakeConnectorSession(connector, integration)

    monkeypatch.setattr(
        tasks_connectors,
        "get_session_factory",
        lambda: (lambda: session),
    )

    seen_attempts: list[int] = []

    class _FakeOrchestrator:
        def __init__(self, _session):  # type: ignore[no-untyped-def]
            pass

        def sync_connector(self, connector_id, tenant_id, attempt=1):  # type: ignore[no-untyped-def]
            assert connector_id == connector.id
            assert tenant_id == connector.tenant_id
            seen_attempts.append(attempt)
            return {"status": "success", "document_id": "doc-1"}

    monkeypatch.setattr(tasks_connectors, "ConnectorOrchestrator", _FakeOrchestrator)

    task_obj = tasks_connectors.run_connector_sync_task
    run_fn = task_obj.__wrapped__
    task_obj.push_request(retries=2)
    try:
        assert run_fn(str(connector.id)) == "success"
    finally:
        task_obj.pop_request()

    assert seen_attempts == [3]


def test_run_connector_sync_task_cleans_up_session_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(
        tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "get_settings", lambda: _FakeSettings())

    connector = SimpleNamespace(
        id=uuid.UUID("12121212-1212-7212-8212-121212121212"),
        tenant_id=uuid.UUID("34343434-3434-7434-8434-343434343434"),
        config={},
    )
    integration = SimpleNamespace(slug="github")
    session = _FakeConnectorSession(
        connector,
        integration,
        rollback_raises=True,
        reset_raises=True,
        close_raises=True,
    )

    monkeypatch.setattr(
        tasks_connectors,
        "get_session_factory",
        lambda: (lambda: session),
    )

    class _FakeOrchestrator:
        def __init__(self, _session):  # type: ignore[no-untyped-def]
            pass

        def sync_connector(self, connector_id, tenant_id, attempt=1):  # type: ignore[no-untyped-def]
            assert connector_id == connector.id
            assert tenant_id == connector.tenant_id
            assert attempt == 1
            return {"status": "success", "document_id": "doc-1"}

    monkeypatch.setattr(tasks_connectors, "ConnectorOrchestrator", _FakeOrchestrator)

    task_obj = tasks_connectors.run_connector_sync_task
    run_fn = task_obj.__wrapped__
    task_obj.push_request(retries=0)
    try:
        assert run_fn(str(connector.id)) == "success"
    finally:
        task_obj.pop_request()

    assert session.lock_released is True
    assert session.closed is True


def test_run_connector_sync_task_returns_locked_when_another_run_holds_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transitions = _RecordingCounter()
    lock_contention = _RecordingCounter()
    monkeypatch.setattr(tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", transitions)
    monkeypatch.setattr(
        tasks_connectors, "WORKER_LOCK_CONTENTION_TOTAL", lock_contention
    )
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(
        tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "get_settings", lambda: _FakeSettings())

    connector = SimpleNamespace(
        id=uuid.UUID("99999999-9999-7999-8999-999999999999"),
        tenant_id=uuid.UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
        config={},
    )
    integration = SimpleNamespace(slug="github")
    session = _FakeConnectorSession(
        connector,
        integration,
        advisory_lock_available=False,
    )

    monkeypatch.setattr(
        tasks_connectors,
        "get_session_factory",
        lambda: (lambda: session),
    )

    class _FakeOrchestrator:
        def __init__(self, _session):  # type: ignore[no-untyped-def]
            raise AssertionError("sync_connector should not run when lock is held")

    monkeypatch.setattr(tasks_connectors, "ConnectorOrchestrator", _FakeOrchestrator)

    task_obj = tasks_connectors.run_connector_sync_task
    run_fn = task_obj.__wrapped__
    task_obj.push_request(retries=0)
    try:
        assert run_fn(str(connector.id)) == "locked"
    finally:
        task_obj.pop_request()

    assert session.lock_released is False
    assert transitions.count == 1
    assert lock_contention.count == 1


def test_run_connector_sync_task_retries_retryable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(
        tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "get_settings", lambda: _FakeSettings())

    connector = SimpleNamespace(
        id=uuid.UUID("33333333-3333-7333-8333-333333333333"),
        tenant_id=uuid.UUID("44444444-4444-7444-8444-444444444444"),
        config={
            "sync_checkpoint": {
                "retryable": True,
                "error_code": "connectivity_failure",
                "status": "failed",
            }
        },
    )
    integration = SimpleNamespace(slug="github")
    session = _FakeConnectorSession(connector, integration)

    monkeypatch.setattr(
        tasks_connectors,
        "get_session_factory",
        lambda: (lambda: session),
    )

    class _FakeOrchestrator:
        def __init__(self, _session):  # type: ignore[no-untyped-def]
            pass

        def sync_connector(self, connector_id, tenant_id, attempt=1):  # type: ignore[no-untyped-def]
            assert connector_id == connector.id
            assert tenant_id == connector.tenant_id
            assert attempt == 2
            return {"status": "error", "message": "temporary outage"}

    monkeypatch.setattr(tasks_connectors, "ConnectorOrchestrator", _FakeOrchestrator)

    def _retry(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"retry-called:{kwargs['countdown']}")

    task_obj = tasks_connectors.run_connector_sync_task
    monkeypatch.setattr(task_obj, "retry", _retry, raising=False)
    run_fn = task_obj.__wrapped__
    task_obj.push_request(retries=1)
    try:
        with pytest.raises(RuntimeError, match="retry-called:60"):
            run_fn(str(connector.id))
    finally:
        task_obj.pop_request()


def test_run_connector_sync_task_does_not_retry_non_retryable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(
        tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "get_settings", lambda: _FakeSettings())

    connector = SimpleNamespace(
        id=uuid.UUID("55555555-5555-7555-8555-555555555555"),
        tenant_id=uuid.UUID("66666666-6666-7666-8666-666666666666"),
        config={
            "sync_checkpoint": {
                "retryable": False,
                "error_code": "validation_failed",
                "status": "failed",
            }
        },
    )
    integration = SimpleNamespace(slug="github")
    session = _FakeConnectorSession(connector, integration)

    monkeypatch.setattr(
        tasks_connectors,
        "get_session_factory",
        lambda: (lambda: session),
    )

    class _FakeOrchestrator:
        def __init__(self, _session):  # type: ignore[no-untyped-def]
            pass

        def sync_connector(self, connector_id, tenant_id, attempt=1):  # type: ignore[no-untyped-def]
            assert connector_id == connector.id
            assert tenant_id == connector.tenant_id
            assert attempt == 1
            return {"status": "error", "message": "validation failed"}

    monkeypatch.setattr(tasks_connectors, "ConnectorOrchestrator", _FakeOrchestrator)

    retry_called = {"value": False}

    def _retry(**kwargs):  # type: ignore[no-untyped-def]
        retry_called["value"] = True
        raise RuntimeError(f"retry-called:{kwargs['countdown']}")

    task_obj = tasks_connectors.run_connector_sync_task
    monkeypatch.setattr(task_obj, "retry", _retry, raising=False)
    run_fn = task_obj.__wrapped__
    task_obj.push_request(retries=0)
    try:
        assert run_fn(str(connector.id)) == "error"
    finally:
        task_obj.pop_request()

    assert retry_called["value"] is False


def test_run_connector_sync_task_prefers_retry_after_at_from_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(
        tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter()
    )
    monkeypatch.setattr(tasks_connectors, "get_settings", lambda: _FakeSettings())

    connector = SimpleNamespace(
        id=uuid.UUID("77777777-7777-7777-8777-777777777777"),
        tenant_id=uuid.UUID("88888888-8888-7888-8888-888888888888"),
        config={
            "sync_checkpoint": {
                "retryable": True,
                "error_code": "connectivity_failure",
                "status": "failed",
                "retry_after_at": "2030-01-01T00:00:00Z",
            }
        },
    )
    integration = SimpleNamespace(slug="github")
    session = _FakeConnectorSession(connector, integration)

    monkeypatch.setattr(
        tasks_connectors,
        "get_session_factory",
        lambda: (lambda: session),
    )

    class _FakeOrchestrator:
        def __init__(self, _session):  # type: ignore[no-untyped-def]
            pass

        def sync_connector(self, connector_id, tenant_id, attempt=1):  # type: ignore[no-untyped-def]
            assert connector_id == connector.id
            assert tenant_id == connector.tenant_id
            assert attempt == 1
            return {
                "status": "error",
                "message": "temporary outage",
                "sync": {"retry_after_at": "2030-01-01T00:00:45Z"},
            }

    monkeypatch.setattr(tasks_connectors, "ConnectorOrchestrator", _FakeOrchestrator)
    monkeypatch.setattr(
        tasks_connectors, "_countdown_from_retry_after_at", lambda value: 45
    )

    def _retry(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"retry-called:{kwargs['countdown']}")

    task_obj = tasks_connectors.run_connector_sync_task
    monkeypatch.setattr(task_obj, "retry", _retry, raising=False)
    run_fn = task_obj.__wrapped__
    task_obj.push_request(retries=0)
    try:
        with pytest.raises(RuntimeError, match="retry-called:45"):
            run_fn(str(connector.id))
    finally:
        task_obj.pop_request()


def test_maintenance_heartbeat() -> None:
    assert tasks_maintenance.maintenance_heartbeat() == "ok"


def test_retention_cleanup_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_maintenance, "CursorResult", _FakeCursorResult)
    monkeypatch.setattr(tasks_maintenance, "get_settings", lambda: _FakeSettings())

    class _TenantModel:
        id = object()

    class _TenantQuery:
        def all(self):  # type: ignore[no-untyped-def]
            return [("11111111-1111-7111-8111-111111111111",)]

    class _AuditSvc:
        def __init__(self, session):  # type: ignore[no-untyped-def]
            _ = session

        def purge_old_events(self, *, tenant_id, retention_days):  # type: ignore[no-untyped-def]
            _ = (tenant_id, retention_days)
            return 2

    class _Session(_FakeSession):
        def query(self, _model):  # type: ignore[no-untyped-def]
            return _TenantQuery()

        def execute(self, stmt, params=None):  # type: ignore[no-untyped-def]
            _ = params
            text_stmt = str(stmt)
            if (
                "DELETE FROM idempotency_keys" in text_stmt
                or "DELETE FROM data_deletions" in text_stmt
            ):
                return _FakeCursorResult(1)
            return super().execute(stmt)

    monkeypatch.setattr(tasks_maintenance, "Tenant", _TenantModel)
    monkeypatch.setattr(tasks_maintenance, "AuditService", _AuditSvc)
    monkeypatch.setattr(
        tasks_maintenance, "get_session_factory", lambda: (lambda: _Session())
    )
    run_fn = tasks_maintenance.retention_cleanup.__wrapped__
    report = run_fn()
    assert report["audit_logs_deleted"] == 2
    assert report["transient_records_deleted"] == 2

    class _ErrorSession(_Session):
        def query(self, _model):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    monkeypatch.setattr(
        tasks_maintenance, "get_session_factory", lambda: (lambda: _ErrorSession())
    )
    with pytest.raises(RuntimeError):
        run_fn()


def test_process_data_deletion_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_maintenance, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        tasks_maintenance, "get_session_factory", lambda: (lambda: _FakeSession())
    )

    class _DeletionService:
        def __init__(self, session, settings):  # type: ignore[no-untyped-def]
            _ = (session, settings)

        def process_deletion(self, *, deletion_id, tenant_id):  # type: ignore[no-untyped-def]
            _ = (deletion_id, tenant_id)
            return None

    monkeypatch.setattr(tasks_maintenance, "DeletionService", _DeletionService)
    run_fn = tasks_maintenance.process_data_deletion.__wrapped__
    assert (
        run_fn(
            "11111111-1111-7111-8111-111111111111",
            "22222222-2222-7222-8222-222222222222",
        )
        == "ok"
    )

    class _DeletionServiceErr(_DeletionService):
        def process_deletion(self, *, deletion_id, tenant_id):  # type: ignore[no-untyped-def]
            _ = (deletion_id, tenant_id)
            raise RuntimeError("x")

    monkeypatch.setattr(tasks_maintenance, "DeletionService", _DeletionServiceErr)
    with pytest.raises(RuntimeError):
        run_fn(
            "11111111-1111-7111-8111-111111111111",
            "22222222-2222-7222-8222-222222222222",
        )


def test_process_data_deletion_cleanup_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_maintenance, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        tasks_maintenance,
        "get_session_factory",
        lambda: (
            lambda: _FakeSession(
                rollback_raises=True,
                reset_raises=True,
                rollback_after_reset_raises=True,
            )
        ),
    )

    class _DeletionService:
        def __init__(self, session, settings):  # type: ignore[no-untyped-def]
            _ = (session, settings)

        def process_deletion(self, *, deletion_id, tenant_id):  # type: ignore[no-untyped-def]
            _ = (deletion_id, tenant_id)
            return None

    monkeypatch.setattr(tasks_maintenance, "DeletionService", _DeletionService)
    run_fn = tasks_maintenance.process_data_deletion.__wrapped__
    assert (
        run_fn(
            "11111111-1111-7111-8111-111111111111",
            "22222222-2222-7222-8222-222222222222",
        )
        == "ok"
    )


def test_retention_cleanup_finally_exception_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter()
    )
    monkeypatch.setattr(tasks_maintenance, "get_settings", lambda: _FakeSettings())

    class _TenantModel:
        id = object()

    class _TenantQuery:
        def all(self):  # type: ignore[no-untyped-def]
            return []

    class _Session(_FakeSession):
        def query(self, _model):  # type: ignore[no-untyped-def]
            return _TenantQuery()

    monkeypatch.setattr(tasks_maintenance, "Tenant", _TenantModel)
    monkeypatch.setattr(
        tasks_maintenance,
        "get_session_factory",
        lambda: (
            lambda: _Session(
                rollback_raises=True,
                reset_raises=True,
                rollback_after_reset_raises=True,
            )
        ),
    )
    run_fn = tasks_maintenance.retention_cleanup.__wrapped__
    report = run_fn()
    assert report["audit_logs_deleted"] == 0
    assert report["transient_records_deleted"] == 0
