from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace

import pytest

from app.integrations.services.composio_service import (
    ComposioConfigurationError,
    ComposioService,
    classify_composio_tool,
    composio_provider_slug,
    composio_user_id,
)


@pytest.mark.unit_no_db
def test_pinned_composio_sdk_exposes_catalog_oauth_and_hosted_mcp_contract() -> None:
    from composio import SESSION_PRESET_DIRECT_TOOLS, Composio

    client = Composio(api_key="test-project-key")

    assert SESSION_PRESET_DIRECT_TOOLS == "direct_tools"
    assert callable(client.sessions.create)
    assert callable(client.connected_accounts.complete_auth)
    assert callable(client.toolkits.get)
    assert callable(client.use)
    assert {"type", "search", "cursor", "limit"}.issubset(
        inspect.signature(client._client.toolkits.list).parameters
    )
    assert {"toolkit_slug", "toolkit_versions", "cursor", "limit"}.issubset(
        inspect.signature(client._client.tools.list).parameters
    )


@pytest.mark.unit_no_db
def test_composio_identity_is_tenant_and_user_scoped() -> None:
    tenant_id = uuid.UUID("0199b8e1-1f23-7a02-8b2e-89a6ed40c001")
    user_id = uuid.UUID("0199b8e1-1f23-7a02-8b2e-89a6ed40c002")

    assert composio_user_id(tenant_id, user_id) == f"averqel:{tenant_id}:{user_id}"
    assert composio_provider_slug("google_sheets") == "composio:google_sheets"
    assert composio_user_id(tenant_id, user_id) != composio_user_id(
        uuid.UUID("0199b8e1-1f23-7a02-8b2e-89a6ed40c003"), user_id
    )


@pytest.mark.unit_no_db
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("GMAIL_GET_MESSAGE", "read"),
        ("SLACK_LIST_MESSAGES", "read"),
        ("SLACK_SEND_MESSAGE", "external_message"),
        ("GOOGLE_CALENDAR_DELETE_EVENT", "delete"),
        ("UNKNOWN_EXECUTE_ACTION", "write"),
    ],
)
def test_composio_tool_risk_defaults_are_conservative(name: str, expected: str) -> None:
    assert classify_composio_tool(name) == expected


@pytest.mark.unit_no_db
def test_composio_tool_labels_take_precedence() -> None:
    assert classify_composio_tool("CUSTOM_ACTION", {"risk_labels": ["delete"]}) == "delete"
    assert classify_composio_tool("CUSTOM_ACTION", {"risk_labels": ["read"]}) == "read"


@pytest.mark.unit_no_db
def test_composio_session_id_is_encrypted_and_bound_to_owner(settings) -> None:
    service = ComposioService(None, settings)  # type: ignore[arg-type]
    tenant_id = uuid.UUID("0199b8e1-1f23-7a02-8b2e-89a6ed40c011")
    user_id = uuid.UUID("0199b8e1-1f23-7a02-8b2e-89a6ed40c012")
    server_id = uuid.UUID("0199b8e1-1f23-7a02-8b2e-89a6ed40c013")
    session_id = "session_live_secret_123"

    stored = service._encrypt_session_id(
        session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        server_id=server_id,
    )

    assert session_id not in str(stored)
    assert (
        service._decrypt_session_id(
            stored,
            tenant_id=tenant_id,
            user_id=user_id,
            server_id=server_id,
        )
        == session_id
    )
    with pytest.raises(ComposioConfigurationError, match="could not be opened"):
        service._decrypt_session_id(
            stored,
            tenant_id=tenant_id,
            user_id=uuid.UUID("0199b8e1-1f23-7a02-8b2e-89a6ed40c099"),
            server_id=server_id,
        )


@pytest.mark.unit_no_db
def test_composio_catalog_preserves_live_pagination_and_search(monkeypatch, settings) -> None:
    service = ComposioService(None, settings)  # type: ignore[arg-type]
    calls: list[dict[str, object]] = []

    class Toolkits:
        @staticmethod
        def list(**kwargs):
            calls.append(kwargs)
            return {
                "items": [
                    {
                        "slug": "gmail",
                        "name": "Google Gmail",
                        "meta": {
                            "description": "Email",
                            "categories": [{"name": "Communication"}],
                            "tools_count": 12,
                        },
                        "auth_schemes": ["OAUTH2"],
                    }
                ],
                "next_cursor": "next-page-token",
                "current_page": 2,
                "total_items": 271,
            }

    sdk = SimpleNamespace(_client=SimpleNamespace(toolkits=Toolkits()))
    monkeypatch.setattr(service, "_client", lambda **_kwargs: sdk)

    result = service.list_toolkits(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        cursor="previous-page-token",
        category="Communication",
        query="gmail",
        limit=75,
    )

    assert calls == [
        {
            "limit": 75,
            "sort_by": "alphabetically",
            "type": "native",
            "include_deprecated": False,
            "category": "Communication",
            "cursor": "previous-page-token",
            "search": "gmail",
        }
    ]
    assert result["total_items"] == 271
    assert result["current_page"] == 2
    assert result["next_cursor"] == "next-page-token"
    assert result["items"][0]["auth_schemes"] == ["OAUTH2"]


@pytest.mark.unit_no_db
def test_composio_tool_detail_preserves_cursor_and_normalizes_schema(monkeypatch, settings) -> None:
    service = ComposioService(None, settings)  # type: ignore[arg-type]
    calls: list[dict[str, object]] = []

    class Tools:
        @staticmethod
        def list(**kwargs):
            calls.append(kwargs)
            return {
                "items": [
                    {
                        "slug": "GMAIL_GET_MESSAGE",
                        "description": "Read one email",
                        "input_parameters": {"message_id": {"type": "string", "required": True}},
                    }
                ],
                "next_cursor": "tool-page-two",
            }

    sdk = SimpleNamespace(
        toolkits=SimpleNamespace(
            get=lambda _slug: {
                "slug": "gmail",
                "name": "Google Gmail",
                "meta": {"description": "Email", "tools_count": 2},
            }
        ),
        _client=SimpleNamespace(tools=Tools()),
    )
    monkeypatch.setattr(service, "_client", lambda **_kwargs: sdk)

    result = service.toolkit_details(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        toolkit_slug="gmail",
        cursor="tool-page-one",
        limit=50,
    )

    assert calls == [
        {
            "toolkit_slug": "gmail",
            "limit": 50,
            "toolkit_versions": "latest",
            "include_deprecated": False,
            "cursor": "tool-page-one",
        }
    ]
    assert result["tools_next_cursor"] == "tool-page-two"
    assert result["tools"][0]["risk_labels"] == ["read"]
    assert result["tools"][0]["input_schema"]["required"] == ["message_id"]


@pytest.mark.unit_no_db
def test_composio_mcp_endpoint_config_rejects_non_composio_hosts(monkeypatch, settings) -> None:
    service = ComposioService(None, settings)  # type: ignore[arg-type]
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    server_id = uuid.uuid4()
    config = service._encrypt_session_id(
        "session-value",
        tenant_id=tenant_id,
        user_id=user_id,
        server_id=server_id,
    )
    config["composio_toolkit_slug"] = "gmail"

    class MCP:
        url = "https://backend.composio.dev/mcp/session"
        headers = {"x-api-key": "private-session-key"}

    sdk = SimpleNamespace(use=lambda _session_id, **_kwargs: SimpleNamespace(mcp=MCP()))
    monkeypatch.setattr(service, "_client", lambda **_kwargs: sdk)
    monkeypatch.setattr(
        "app.integrations.services.composio_service.validate_remote_endpoint",
        lambda value: value,
    )
    server = SimpleNamespace(
        id=server_id,
        config=config,
        provider_slug="composio:gmail",
    )

    endpoint = service.mcp_endpoint_config(
        tenant_id=tenant_id,
        user_id=user_id,
        server=server,
    )
    assert endpoint["credentials"]["server_url"] == MCP.url
    assert endpoint["credentials"]["headers"] == MCP.headers

    MCP.url = "https://attacker.example/mcp"
    with pytest.raises(ComposioConfigurationError, match="unrecognized MCP endpoint"):
        service.mcp_endpoint_config(tenant_id=tenant_id, user_id=user_id, server=server)


@pytest.mark.unit_no_db
def test_composio_default_policy_allows_reads_but_never_skips_side_effect_approval(
    monkeypatch,
) -> None:
    from app.integrations.services import mcp_runtime

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    policy = SimpleNamespace(
        default_enabled=True,
        denied_tools=[],
        allowed_tools=[],
        risk_ceiling="external_message",
        read_only=False,
        approval_rules={
            "write": "needs_approval",
            "delete": "needs_approval",
            "external_message": "needs_approval",
        },
        tool_modes={},
        default_tool_mode="always_allow",
    )
    db = SimpleNamespace(execute=lambda _query: SimpleNamespace(scalar_one_or_none=lambda: policy))
    server = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        provider_slug="composio:gmail",
        enabled=True,
        status="connected",
        catalog_revision=1,
    )
    monkeypatch.setattr(mcp_runtime, "mcp_server_provider_available", lambda *_args: (True, None))

    read = mcp_runtime.evaluate_mcp_tool_policy(
        db=db,
        server=server,
        tool_name="GMAIL_GET_MESSAGE",
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=None,
    )
    write = mcp_runtime.evaluate_mcp_tool_policy(
        db=db,
        server=server,
        tool_name="GMAIL_CREATE_DRAFT",
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=None,
    )

    assert read.allowed is True
    assert read.requires_approval is False
    assert write.allowed is True
    assert write.requires_approval is True
