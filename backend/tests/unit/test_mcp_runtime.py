from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import anyio
import pytest

from app.services.integrations import mcp_runtime
from app.services.integrations.mcp_runtime import (
    MCPConnectorRuntime,
    UniversalMCPConnector,
)


def test_build_mcp_runtime_parses_mcp_bundle() -> None:
    runtime = mcp_runtime.build_mcp_runtime(
        {
            "auth_mode": "mcp",
            "credentials": {
                "server_url": "https://example.invalid/mcp",
                "mcp_tools": ["search_files", "read_file_content"],
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "client_info": {
                    "redirect_uris": [
                        "https://averqel.localhost/api/v1/integrations/connectors/oauth/callback"
                    ],
                    "client_name": "AverQel",
                },
            },
        }
    )

    assert runtime is not None
    assert runtime.server_url == "https://example.invalid/mcp"
    assert runtime.declared_tools == ("search_files", "read_file_content")
    assert str(runtime.client_metadata.redirect_uris[0]) == (
        "https://averqel.localhost/api/v1/integrations/connectors/oauth/callback"
    )


def test_build_mcp_runtime_returns_none_without_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_runtime, "MCP_SDK_AVAILABLE", False)

    runtime = mcp_runtime.build_mcp_runtime({"auth_mode": "mcp", "credentials": {}})

    assert runtime is None


def test_build_mcp_runtime_supports_anonymous_official_server() -> None:
    runtime = mcp_runtime.build_mcp_runtime(
        {
            "auth_mode": "mcp",
            "credentials": {
                "server_url": "https://learn.microsoft.com/api/mcp",
                "transport": "streamable_http",
                "oauth_mode": "none",
            },
        }
    )
    assert runtime is not None
    assert runtime.anonymous is True


def test_build_mcp_runtime_supports_streamable_sse_fallback() -> None:
    runtime = mcp_runtime.build_mcp_runtime(
        {
            "auth_mode": "mcp",
            "mcp_sse_fallback": True,
            "credentials": {
                "server_url": "https://example.invalid/mcp",
                "transport": "streamable_http",
                "access_token": "access-token",
                "client_info": {
                    "redirect_uris": ["https://example.invalid/callback"],
                    "client_name": "AverQel",
                },
            },
        }
    )

    assert runtime is not None
    assert runtime.transport == "streamable_http"
    assert runtime.fallback_transport == "sse"


def test_mcp_runtime_snapshot_formats_text_and_structured_payload(monkeypatch) -> None:
    runtime = MCPConnectorRuntime(
        server_url="https://example.invalid/mcp",
        client_metadata=mcp_runtime.OAuthClientMetadata.model_validate(
            {
                "redirect_uris": [
                    "https://averqel.localhost/api/v1/integrations/connectors/oauth/callback"
                ],
                "client_name": "AverQel",
                "token_endpoint_auth_method": "none",
            }
        ),
        storage=mcp_runtime._InMemoryTokenStorage(),
        oauth_metadata=None,
        resource_metadata=None,
        declared_tools=("search",),
    )

    async def fake_call_tool(
        self: MCPConnectorRuntime,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        del self, name, arguments
        return SimpleNamespace(
            isError=False,
            structuredContent={"items": [{"id": "doc-1", "name": "Design Notes"}]},
            content=[SimpleNamespace(type="text", text="Rendered body")],
        )

    monkeypatch.setattr(MCPConnectorRuntime, "call_tool", fake_call_tool)

    async def _run_snapshot() -> dict[str, Any]:
        return await runtime.snapshot_from_tool_call(
            provider="test",
            tool_name="search",
            arguments={"query": "design"},
            title="Test Snapshot",
            scope_label="all items",
            filename="test.md",
        )

    result = anyio.run(_run_snapshot)

    assert result["status"] == "success"
    assert result["filename"] == "test.md"
    assert "Design Notes" in result["payload"]
    assert "Rendered body" in result["payload"]


@pytest.mark.parametrize(
    ("slug", "sync_helper_name"),
    [
        ("google-drive", "sync_google_drive"),
        ("gmail", "sync_gmail"),
        ("google-calendar", "sync_google_calendar"),
        ("github", "sync_github"),
        ("slack", "sync_slack"),
        ("notion", "sync_notion"),
    ],
)
def test_universal_mcp_connector_routes_correctly(
    monkeypatch: pytest.MonkeyPatch,
    slug: str,
    sync_helper_name: str,
) -> None:
    async def _fake_sync(_runtime: Any, _config: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "message": "MCP sync complete.",
        }

    monkeypatch.setattr(mcp_runtime, sync_helper_name, _fake_sync)

    # Mock Integration and Session
    from app.models.integrations.integration import Integration

    mock_integration = Integration(slug=slug)
    mock_session = SimpleNamespace(get=lambda _model, _id: mock_integration)

    connector = SimpleNamespace(
        id="conn-1",
        integration_id="int-1",
        config={
            "auth_mode": "mcp",
            "credentials": {
                "server_url": "https://example.invalid/mcp",
                "access_token": "abc",
                "client_info": {
                    "redirect_uris": ["http://localhost"],
                    "client_name": "test",
                },
            },
        },
        integration=mock_integration,
    )

    service = UniversalMCPConnector(connector, mock_session)
    result = service.sync()

    assert result["status"] == "success"
    assert result["message"] == "MCP sync complete."


def test_universal_mcp_connector_failure_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _failing_sync(_runtime: Any, _config: dict[str, Any]) -> dict[str, Any]:
        raise mcp_runtime.MCPRuntimeError("MCP unavailable")

    monkeypatch.setattr(mcp_runtime, "sync_google_drive", _failing_sync)

    from app.models.integrations.integration import Integration

    mock_integration = Integration(slug="google-drive")
    mock_session = SimpleNamespace(get=lambda _model, _id: mock_integration)

    connector = SimpleNamespace(
        id="conn-1",
        integration_id="int-1",
        config={
            "auth_mode": "mcp",
            "credentials": {
                "server_url": "https://example.invalid/mcp",
                "access_token": "abc",
                "client_info": {
                    "redirect_uris": ["http://localhost"],
                    "client_name": "test",
                },
            },
        },
        integration=mock_integration,
    )

    service = UniversalMCPConnector(connector, mock_session)
    result = service.sync()

    assert result["status"] == "error"
    assert "MCP unavailable" in result["message"]
