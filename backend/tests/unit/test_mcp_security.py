from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import anyio
import httpx
import pytest

from app.integrations.services import mcp_http_client
from app.integrations.services.mcp_http_client import (
    MCPRedirectRejectedError,
    SafeMCPAsyncClient,
    SafeMCPClient,
    _PinnedAsyncNetworkBackend,
)
from app.integrations.services.mcp_runtime import (
    MCPConnectorRuntime,
    mcp_catalog_is_fresh,
    summarize_mcp_result,
)


def test_sync_mcp_client_validates_and_rejects_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []
    monkeypatch.setattr(
        mcp_http_client,
        "validate_remote_endpoint",
        lambda value: checked.append(value) or value,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "https://private.invalid"}, request=request)
    )

    with SafeMCPClient(transport=transport) as client:
        with pytest.raises(MCPRedirectRejectedError):
            client.get("https://remote.example/mcp")

    assert checked == ["https://remote.example/mcp"]


def test_async_mcp_client_validates_and_rejects_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []
    monkeypatch.setattr(
        mcp_http_client,
        "validate_remote_endpoint",
        lambda value: checked.append(value) or value,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "https://private.invalid"}, request=request)
    )

    async def run() -> None:
        async with SafeMCPAsyncClient(transport=transport) as client:
            with pytest.raises(MCPRedirectRejectedError):
                await client.get("https://remote.example/mcp")

    anyio.run(run)
    assert checked == ["https://remote.example/mcp"]


def test_pinned_async_backend_uses_a_concrete_httpcore_backend() -> None:
    """Async MCP connections must not use httpcore's abstract interface."""
    backend = _PinnedAsyncNetworkBackend()

    assert type(backend._backend).__name__ != "AsyncNetworkBackend"


def test_native_mcp_catalog_must_be_connected_and_fresh() -> None:
    server = SimpleNamespace(
        enabled=True,
        status="connected",
        config={"mcp_catalog_last_sync_at": datetime.now(UTC).isoformat()},
    )
    assert mcp_catalog_is_fresh(server, max_age_seconds=900)
    server.config["mcp_catalog_last_sync_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert not mcp_catalog_is_fresh(server, max_age_seconds=900)
    server.status = "failed"
    assert not mcp_catalog_is_fresh(server, max_age_seconds=900)


def test_tool_call_does_not_retry_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = MCPConnectorRuntime(
        server_url="https://remote.example/mcp",
        client_metadata=None,
        storage=SimpleNamespace(),
        oauth_metadata=None,
        resource_metadata=None,
        declared_tools=(),
        anonymous=True,
    )
    calls = 0

    class FailingSession:
        async def call_tool(self, name: str, arguments: dict) -> None:
            del name, arguments
            nonlocal calls
            calls += 1
            raise RuntimeError("remote failure")

    @asynccontextmanager
    async def fake_session(self):
        yield FailingSession()

    monkeypatch.setattr(MCPConnectorRuntime, "session", fake_session)

    async def run() -> None:
        with pytest.raises(Exception, match="failed"):
            await runtime.call_tool("write_document", {})

    anyio.run(run)
    assert calls == 1


def test_mcp_event_result_summary_has_no_content() -> None:
    result = SimpleNamespace(
        isError=False,
        content=[SimpleNamespace(type="text", text="private body")],
        structuredContent={"private": "data"},
    )
    summary = summarize_mcp_result(result)
    assert summary == {
        "content_item_count": 1,
        "content_types": ["text"],
        "has_structured_content": True,
        "rendered_length": 37,
        "is_error": False,
    }
