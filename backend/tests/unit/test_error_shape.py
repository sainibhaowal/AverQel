from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
