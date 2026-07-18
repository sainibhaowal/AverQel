from __future__ import annotations

import json
import logging

import pytest

from app.core.context import bind_request_context, clear_request_context
from app.core.logging import configure_logging


def test_structured_logging_contains_required_fields_and_redacts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    tokens = bind_request_context(
        trace_id="trc_test_week5",
        tenant_id="tenant_test_week5",
        user_id="user_test_week5",
    )
    try:
        logger = logging.getLogger("week5.logging")
        logger.info("authorization token leak check", extra={"token": "secret-value"})
    finally:
        clear_request_context(tokens)

    captured = capsys.readouterr().err.strip().splitlines()
    assert captured, "expected at least one json log line"
    payload = json.loads(captured[-1])
    assert payload["timestamp"]
    assert payload["level"] == "INFO"
    assert payload["module"] == "week5.logging"
    assert payload["trace_id"] == "trc_test_week5"
    assert payload["tenant_id"] == "tenant_test_week5"
    assert payload["user_id"] == "user_test_week5"
    assert "[redacted]" in payload["message"]
    assert "secret-value" not in json.dumps(payload)
