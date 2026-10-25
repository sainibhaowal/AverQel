from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.deepspace.workers import tasks as tasks_deepspace
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
    auth_session_retention_days: int = 90
    feedback_retention_days: int = 365
    support_ticket_retention_days: int = 365


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

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._values)


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
            return SimpleNamespace(scalars=lambda: _FakeScalarResult([self.connector.id]))
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
    monkeypatch.setattr(tasks_ingestion, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_ingestion, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
    monkeypatch.setattr(tasks_ingestion, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(tasks_ingestion, "IngestionService", _FakeIngestionService)
    monkeypatch.setattr(tasks_ingestion, "get_session_factory", lambda: (lambda: _FakeSession()))

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
    monkeypatch.setattr(tasks_ingestion, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_ingestion, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
    monkeypatch.setattr(tasks_ingestion, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(tasks_ingestion, "IngestionService", _RetryIngestionService)
    monkeypatch.setattr(tasks_ingestion, "get_session_factory", lambda: (lambda: _FakeSession()))

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
    monkeypatch.setattr(tasks_ingestion, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_ingestion, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
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
    monkeypatch.setattr(tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
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
    monkeypatch.setattr(tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
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
    monkeypatch.setattr(tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
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
    monkeypatch.setattr(tasks_connectors, "WORKER_LOCK_CONTENTION_TOTAL", lock_contention)
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
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
    monkeypatch.setattr(tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
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
    monkeypatch.setattr(tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
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
    monkeypatch.setattr(tasks_connectors, "WORKER_JOB_TRANSITIONS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_RETRIES_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_connectors, "WORKER_STAGE_DURATION_SECONDS", _DummyCounter())
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
    monkeypatch.setattr(tasks_connectors, "_countdown_from_retry_after_at", lambda value: 45)

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


@pytest.mark.unit_no_db
def test_duplicate_deepspace_worker_does_not_finalize_the_original_queue_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RedisLock:
        def set(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return False

        def get(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return None

        def close(self) -> None:
            return None

    session = _FakeSession()
    finished_turns: list[dict[str, object]] = []
    monkeypatch.setattr(
        tasks_deepspace,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://isolated-test"),
    )
    monkeypatch.setattr(tasks_deepspace, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(
        tasks_deepspace.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: _RedisLock(),
    )
    monkeypatch.setattr(
        tasks_deepspace.DeepSpaceTurnQueueStore,
        "finish",
        lambda _self, **kwargs: finished_turns.append(kwargs),
    )

    result = tasks_deepspace.run_deepspace_task.run(
        tenant_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        roles=["user"],
        permissions=["queries:run"],
        conversation_id=str(uuid.uuid4()),
        prompt="A turn already owned by another worker",
        client_request_id="same-request-key",
        thinking_enabled=False,
    )

    assert result == "already-running"
    assert finished_turns == []


@pytest.mark.unit_no_db
def test_deepspace_worker_fails_stream_without_terminal_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Lock:
        value: str | None = None

        def set(self, _key, value, **_kwargs):  # type: ignore[no-untyped-def]
            self.value = value
            return True

        def get(self, key):  # type: ignore[no-untyped-def]
            return self.value if str(key).startswith("deepspace:worker-lock:") else None

        def delete(self, _key):  # type: ignore[no-untyped-def]
            self.value = None

        def close(self) -> None:
            return None

    class _QueryResult:
        def scalar_one_or_none(self):  # type: ignore[no-untyped-def]
            return None

    class _Session(_FakeSession):
        def execute(self, statement, params=None):  # type: ignore[no-untyped-def]
            _ = params
            if hasattr(statement, "selected_columns"):
                return _QueryResult()
            return None

    class _Queue:
        def finish(self, **kwargs):  # type: ignore[no-untyped-def]
            finished_turns.append(kwargs)

        def state(self, **_kwargs):  # type: ignore[no-untyped-def]
            return SimpleNamespace(paused=False)

    class _EventFanout:
        def __init__(self, **_kwargs):  # type: ignore[no-untyped-def]
            return None

        async def start(self) -> None:
            return None

        async def submit(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        async def close(self) -> None:
            return None

    conversation_id = uuid.uuid4()
    session = _Session()
    finished_turns: list[dict[str, object]] = []
    finished_runs: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    lock = _Lock()

    class _Service:
        def __init__(self, **_kwargs):  # type: ignore[no-untyped-def]
            return None

        async def stream_turn(self, **_kwargs):  # type: ignore[no-untyped-def]
            yield f'event: start\ndata: {{"conversation_id":"{conversation_id}"}}\n\n'

    monkeypatch.setattr(
        tasks_deepspace,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://isolated-test"),
    )
    monkeypatch.setattr(tasks_deepspace, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(tasks_deepspace.redis.Redis, "from_url", lambda *_a, **_k: lock)
    monkeypatch.setattr(tasks_deepspace, "set_db_tenant_context", lambda *_a, **_k: None)
    monkeypatch.setattr(tasks_deepspace, "DeepSpaceChatService", _Service)
    monkeypatch.setattr(tasks_deepspace, "AsyncRunEventFanout", _EventFanout)
    monkeypatch.setattr(tasks_deepspace, "latest_sequence", lambda *_a, **_k: 0)
    monkeypatch.setattr(tasks_deepspace, "DeepSpaceTurnQueueStore", lambda _db: _Queue())
    monkeypatch.setattr(
        tasks_deepspace.DeepSpaceRuntimeStore,
        "finish_for_request",
        lambda _self, **kwargs: finished_runs.append(kwargs),
    )
    monkeypatch.setattr(
        tasks_deepspace,
        "_publish_failure",
        lambda **kwargs: failures.append(kwargs),
    )
    monkeypatch.setattr(
        tasks_deepspace.dispatch_deepspace_turn_queue,
        "apply_async",
        lambda **_kwargs: None,
    )

    result = tasks_deepspace.run_deepspace_task.run(
        tenant_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        roles=["user"],
        permissions=["queries:run"],
        conversation_id=str(conversation_id),
        prompt="A response that exits early",
        client_request_id="missing-terminal-frame",
        thinking_enabled=False,
    )

    assert result == "failed"
    assert finished_turns[0]["status"] == "failed"
    assert finished_runs[0]["status"] == "failed"
    assert failures[0]["client_request_id"] == "missing-terminal-frame"
    assert "stopped before finishing" in failures[0]["message"]


def test_retention_cleanup_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter())
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

        def purge_platform_events(self, *, retention_days):  # type: ignore[no-untyped-def]
            assert retention_days == 90
            return 0

    class _Session(_FakeSession):
        def query(self, _model):  # type: ignore[no-untyped-def]
            return _TenantQuery()

        def execute(self, stmt, params=None):  # type: ignore[no-untyped-def]
            _ = params
            text_stmt = str(stmt)
            if hasattr(stmt, "selected_columns"):
                return SimpleNamespace(scalars=lambda: _FakeScalarResult([]))
            if (
                "DELETE FROM idempotency_keys" in text_stmt
                or "DELETE FROM data_deletions" in text_stmt
            ):
                return _FakeCursorResult(1)
            return super().execute(stmt)

    monkeypatch.setattr(tasks_maintenance, "Tenant", _TenantModel)
    monkeypatch.setattr(tasks_maintenance, "AuditService", _AuditSvc)
    monkeypatch.setattr(tasks_maintenance, "get_session_factory", lambda: (lambda: _Session()))
    run_fn = tasks_maintenance.retention_cleanup.__wrapped__
    report = run_fn()
    assert report["audit_logs_deleted"] == 2
    assert report["transient_records_deleted"] == 2

    class _ErrorSession(_Session):
        def query(self, _model):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    monkeypatch.setattr(tasks_maintenance, "get_session_factory", lambda: (lambda: _ErrorSession()))
    with pytest.raises(RuntimeError):
        run_fn()


def test_process_data_deletion_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_maintenance, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(tasks_maintenance, "get_session_factory", lambda: (lambda: _FakeSession()))

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
    monkeypatch.setattr(tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter())
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
    monkeypatch.setattr(tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_maintenance, "get_settings", lambda: _FakeSettings())

    class _TenantModel:
        id = object()

    class _TenantQuery:
        def all(self):  # type: ignore[no-untyped-def]
            return []

    class _AuditSvc:
        def __init__(self, session):  # type: ignore[no-untyped-def]
            _ = session

        def purge_platform_events(self, *, retention_days):  # type: ignore[no-untyped-def]
            assert retention_days == 90
            return 0

    class _Session(_FakeSession):
        def query(self, _model):  # type: ignore[no-untyped-def]
            return _TenantQuery()

    monkeypatch.setattr(tasks_maintenance, "Tenant", _TenantModel)
    monkeypatch.setattr(tasks_maintenance, "AuditService", _AuditSvc)
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


def test_storage_cleanup_removes_successful_jobs_and_redacts_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.system.models.storage_cleanup import StorageCleanupJob

    monkeypatch.setattr(tasks_maintenance, "MAINTENANCE_JOB_EVENTS_TOTAL", _DummyCounter())
    monkeypatch.setattr(tasks_maintenance, "get_settings", lambda: _FakeSettings())

    class _TenantModel:
        id = object()

    class _Query:
        def __init__(self, items) -> None:  # type: ignore[no-untyped-def]
            self.items = items

        def filter(self, *args):  # type: ignore[no-untyped-def]
            _ = args
            return self

        def order_by(self, *args):  # type: ignore[no-untyped-def]
            _ = args
            return self

        def limit(self, _limit):  # type: ignore[no-untyped-def]
            return self

        def with_for_update(self, **kwargs):  # type: ignore[no-untyped-def]
            _ = kwargs
            return self

        def all(self):  # type: ignore[no-untyped-def]
            return list(self.items)

    class _Session(_FakeSession):
        def __init__(self, job) -> None:  # type: ignore[no-untyped-def]
            super().__init__()
            self.job = job
            self.deleted = []
            self.closed = False

        def query(self, model):  # type: ignore[no-untyped-def]
            if model is _TenantModel.id:
                return _Query([])
            assert model is StorageCleanupJob
            return _Query([self.job])

        def delete(self, row) -> None:  # type: ignore[no-untyped-def]
            self.deleted.append(row)

        def close(self) -> None:
            self.closed = True

    class _StorageService:
        def __init__(self, _settings) -> None:  # type: ignore[no-untyped-def]
            pass

        def delete_object(self, *, bucket, object_key, raise_on_error):  # type: ignore[no-untyped-def]
            _ = (bucket, object_key, raise_on_error)

    monkeypatch.setattr(tasks_maintenance, "Tenant", _TenantModel)
    monkeypatch.setattr(tasks_maintenance, "StorageService", _StorageService)

    def _job(*, attempts: int = 0):
        return SimpleNamespace(
            tenant_id=uuid.uuid4(),
            owner_user_id=uuid.uuid4(),
            bucket="account-data",
            object_key="private/user/path",
            status="pending",
            attempts=attempts,
            next_attempt_at=datetime.now(UTC) - timedelta(minutes=1),
        )

    successful_job = _job()
    success_session = _Session(successful_job)
    monkeypatch.setattr(tasks_maintenance, "get_session_factory", lambda: lambda: success_session)
    report = tasks_maintenance.storage_cleanup.__wrapped__()
    assert report["succeeded"] == 1
    assert report["failed"] == 0
    assert success_session.deleted == [successful_job]
    assert success_session.closed is True

    class _FailingStorageService(_StorageService):
        def delete_object(self, *, bucket, object_key, raise_on_error):  # type: ignore[no-untyped-def]
            _ = (bucket, object_key, raise_on_error)
            raise RuntimeError("private object path and storage credentials")

    monkeypatch.setattr(tasks_maintenance, "StorageService", _FailingStorageService)
    failed_job = _job(attempts=tasks_maintenance.STORAGE_CLEANUP_MAX_ATTEMPTS - 1)
    failed_session = _Session(failed_job)
    monkeypatch.setattr(tasks_maintenance, "get_session_factory", lambda: lambda: failed_session)
    report = tasks_maintenance.storage_cleanup.__wrapped__()
    assert report["succeeded"] == 0
    assert report["failed"] == 1
    assert failed_job.owner_user_id is None
    assert failed_job.attempts == tasks_maintenance.STORAGE_CLEANUP_MAX_ATTEMPTS
    assert failed_job.status == "failed"
    assert failed_job.last_error == "storage_delete_failed"
    assert failed_session.deleted == []
