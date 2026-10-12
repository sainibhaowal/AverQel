from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.errors import ApiError, register_exception_handlers
from app.core.middleware import RequestContextMiddleware


def test_api_error_schema_shape() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise ApiError(code="FORBIDDEN", message="Test failure", status_code=403)

    client = TestClient(app)
    response = client.get("/boom")

    payload = response.json()
    assert response.status_code == 403
    assert payload["error"]["code"] == "FORBIDDEN"
    assert payload["error"]["message"] == "Test failure"
    assert "trace_id" in payload
    assert "timestamp" in payload


def test_api_error_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="Unknown API error code"):
        ApiError(code="UNKNOWN_CODE", message="x", status_code=400)


def test_transient_database_lock_error_returns_retryable_service_overload() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    class PostgresLockTimeoutError(Exception):
        sqlstate = "55P03"

    @app.get("/busy")
    def busy() -> None:
        raise OperationalError("SELECT 1", {}, PostgresLockTimeoutError("lock timeout"))

    response = TestClient(app, raise_server_exceptions=False).get("/busy")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["error"]["code"] == "SERVICE_OVERLOAD"
    assert "temporary database issue" in response.json()["error"]["message"]


def test_unrecognized_database_operational_error_is_not_marked_retryable() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    class UniqueConstraintViolationError(Exception):
        sqlstate = "23505"

    @app.get("/database-error")
    def database_error() -> None:
        raise OperationalError("INSERT", {}, UniqueConstraintViolationError("duplicate"))

    response = TestClient(app, raise_server_exceptions=False).get("/database-error")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
