from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.deepspace.services.mcp_bridge import DeepSpaceMCPBridge
from app.deepspace.services.mcp_tool_broker import MCPToolBroker
from app.integrations.catalog.mcp_official_providers import CURATED_MCP_CATALOG_SOURCE
from app.integrations.models.composio_credential import ComposioCredential
from app.integrations.models.mcp_connection_policy import MCPConnectionPolicy
from app.integrations.models.mcp_server import MCPRegistryEntry, MCPServer
from app.integrations.services.composio_service import (
    ComposioConfigurationError,
    ComposioService,
    composio_user_id,
)
from app.integrations.services.mcp_runtime import MCPConnectorRuntime
from app.platform.database.session import set_db_tenant_context, set_db_user_context
from tests.conftest import SeededUser


def _headers(seeded: SeededUser, *, role: str = "user") -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={role},
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_composio_key_is_user_managed_encrypted_and_isolated(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    db_session: Session,
    monkeypatch,
) -> None:
    user = seed_user(
        "tenant-composio-status",
        "composio-user@example.com",
        "StrongPass!1234",
        ("user",),
    )
    other_user = seed_user(
        "tenant-composio-other-credential",
        "composio-other@example.com",
        "StrongPass!1234",
        ("user",),
    )
    monkeypatch.setattr(
        "app.integrations.services.composio_service._sdk",
        lambda _api_key: SimpleNamespace(
            _client=SimpleNamespace(
                toolkits=SimpleNamespace(list=lambda **_kwargs: SimpleNamespace(items=[]))
            )
        ),
    )
    project_key = "composio-test-project-key-123"

    status_response = client.get("/api/v1/mcp/composio/status", headers=_headers(user))
    assert status_response.status_code == 200
    assert status_response.json()["configured"] is False
    assert "api_key" not in status_response.text

    response = client.put(
        "/api/v1/mcp/composio/credential",
        headers=_headers(user),
        json={"api_key": project_key},
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert project_key not in response.text
    set_db_tenant_context(db_session, user.tenant_id)
    set_db_user_context(db_session, user.user_id)
    credential = db_session.execute(
        select(ComposioCredential).where(
            ComposioCredential.tenant_id == user.tenant_id,
            ComposioCredential.user_id == user.user_id,
        )
    ).scalar_one()
    assert project_key.encode() not in credential.secret_ciphertext
    assert credential.secret_nonce
    assert credential.secret_kid

    other_status = client.get("/api/v1/mcp/composio/status", headers=_headers(other_user))
    assert other_status.status_code == 200
    assert other_status.json()["configured"] is False
    with pytest.raises(ComposioConfigurationError, match="Add your Composio project API key"):
        ComposioService(db_session, get_settings())._api_key(
            tenant_id=other_user.tenant_id,
            user_id=other_user.user_id,
        )

    own_server = MCPServer(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        provider_slug="composio:own_app",
        name="Own app",
        transport="streamable_http",
        config={"composio_session_ciphertext": "own-session"},
        account_identity={},
        enabled=True,
        status="connected",
    )
    set_db_tenant_context(db_session, user.tenant_id)
    set_db_user_context(db_session, user.user_id)
    db_session.add(own_server)
    db_session.commit()
    other_server = MCPServer(
        tenant_id=other_user.tenant_id,
        user_id=other_user.user_id,
        provider_slug="composio:other_app",
        name="Other user's app",
        transport="streamable_http",
        config={"composio_session_ciphertext": "other-session"},
        account_identity={},
        enabled=True,
        status="connected",
    )
    set_db_tenant_context(db_session, other_user.tenant_id)
    set_db_user_context(db_session, other_user.user_id)
    db_session.add(other_server)
    db_session.commit()

    remove_response = client.delete(
        "/api/v1/mcp/composio/credential",
        headers=_headers(user),
    )
    assert remove_response.status_code == 204
    set_db_tenant_context(db_session, user.tenant_id)
    set_db_user_context(db_session, user.user_id)
    assert (
        db_session.execute(
            select(ComposioCredential).where(
                ComposioCredential.tenant_id == user.tenant_id,
                ComposioCredential.user_id == user.user_id,
            )
        ).scalar_one_or_none()
        is None
    )
    own_server = db_session.get(MCPServer, own_server.id)
    assert own_server is not None
    db_session.refresh(own_server)
    assert own_server.enabled is False
    assert own_server.status == "disconnected"
    assert "composio_session_ciphertext" not in own_server.config
    set_db_tenant_context(db_session, other_user.tenant_id)
    set_db_user_context(db_session, other_user.user_id)
    other_server = db_session.get(MCPServer, other_server.id)
    assert other_server is not None
    db_session.refresh(other_server)
    assert other_server.enabled is True
    assert other_server.status == "connected"
    assert other_server.config["composio_session_ciphertext"] == "other-session"
    assert client.get("/api/v1/admin/providers/composio", headers=_headers(user)).status_code == 404


def test_composio_toolkit_details_accepts_leading_underscore_slug(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    user = seed_user(
        "tenant-composio-leading-underscore",
        "composio-leading-underscore@example.com",
        "StrongPass!1234",
        ("user",),
    )
    toolkit_lookups: list[str] = []
    tool_list_calls: list[dict[str, object]] = []

    def get_toolkit(slug: str) -> dict[str, object]:
        toolkit_lookups.append(slug)
        return {
            "slug": slug,
            "name": "1Password",
            "meta": {"description": "Password manager", "tools_count": 1},
        }

    def list_tools(**kwargs):
        tool_list_calls.append(kwargs)
        return {
            "items": [
                {
                    "slug": "_1PASSWORD_LIST_ITEMS",
                    "description": "List vault items",
                    "input_parameters": {},
                }
            ],
            "next_cursor": None,
        }

    sdk = SimpleNamespace(
        toolkits=SimpleNamespace(get=get_toolkit),
        _client=SimpleNamespace(tools=SimpleNamespace(list=list_tools)),
    )
    monkeypatch.setattr(ComposioService, "_client", lambda *_args, **_kwargs: sdk)

    response = client.get(
        "/api/v1/mcp/composio/toolkits/_1password",
        headers=_headers(user),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["slug"] == "_1password"
    assert payload["logo_url"] == "https://logos.composio.dev/api/_1password"
    assert payload["tools"][0]["name"] == "_1PASSWORD_LIST_ITEMS"
    assert toolkit_lookups == ["_1password"]
    assert tool_list_calls[0]["toolkit_slug"] == "_1password"


def test_marketplace_hides_the_bundled_native_connectors(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    db_session: Session,
) -> None:
    user = seed_user(
        "tenant-composio-marketplace",
        "composio-marketplace@example.com",
        "StrongPass!1234",
        ("user",),
    )
    entry = MCPRegistryEntry(
        source=CURATED_MCP_CATALOG_SOURCE,
        server_name="google-gmail",
        provider_slug="google-gmail",
        publisher_type="official",
        display_name="Google Gmail",
        publisher="Google",
        remote_url="https://gmail.example/mcp",
        transport="streamable_http",
        trust_status="approved",
    )
    db_session.add(entry)
    db_session.commit()

    marketplace = client.get("/api/v1/mcp/marketplace", headers=_headers(user))
    detail = client.get(f"/api/v1/mcp/marketplace/{entry.id}", headers=_headers(user))
    connect = client.post(f"/api/v1/mcp/marketplace/{entry.id}/connect", headers=_headers(user))

    assert marketplace.status_code == 200
    assert all(item["id"] != str(entry.id) for item in marketplace.json()["items"])
    assert detail.status_code == 404
    assert connect.status_code == 404


def test_composio_oauth_uses_user_identity_encrypted_session_and_mcp_approval_policy(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    db_session: Session,
    monkeypatch,
) -> None:
    owner = seed_user(
        "tenant-composio-owner",
        "composio-owner@example.com",
        "StrongPass!1234",
        ("user",),
    )
    other_user = seed_user(
        "tenant-composio-other-owner",
        "composio-other@example.com",
        "StrongPass!1234",
        ("user",),
    )
    settings = get_settings()
    settings.averqel_public_origin = "https://averqel.example"
    created_sessions: list[dict[str, object]] = []
    expected_identity = composio_user_id(owner.tenant_id, owner.user_id)
    resolved_account_owner = expected_identity
    connection_lookups: list[tuple[str, float]] = []

    class FakeSession:
        session_id = "hosted-session-secret"

        @staticmethod
        def authorize(toolkit_slug: str, *, callback_url: str):
            assert toolkit_slug == "gmail"
            assert callback_url == (
                "https://averqel.example/dashboard/mcp/composio/callback?toolkit_slug=gmail"
            )
            return SimpleNamespace(
                id="ca_example_123",
                redirect_url="https://connect.composio.dev/oauth/start?state=single-use",
            )

    def create_session(**kwargs):
        created_sessions.append(kwargs)
        return FakeSession()

    def wait_for_connection(account_id: str, *, timeout: float):
        connection_lookups.append((account_id, timeout))
        return SimpleNamespace(
            id=account_id,
            toolkit=SimpleNamespace(slug="gmail"),
            status="ACTIVE",
            user_id=resolved_account_owner,
        )

    sdk = SimpleNamespace(
        toolkits=SimpleNamespace(
            get=lambda _slug: {
                "slug": "gmail",
                "name": "Google Gmail",
                "auth_schemes": ["oauth2"],
                "meta": {
                    "description": "Email",
                    "categories": [{"name": "Communication"}],
                    "tools_count": 2,
                },
            }
        ),
        sessions=SimpleNamespace(create=create_session),
        connected_accounts=SimpleNamespace(wait_for_connection=wait_for_connection),
    )
    monkeypatch.setattr(ComposioService, "_client", lambda *_args, **_kwargs: sdk)
    monkeypatch.setattr("app.integrations.api.mcp._publish_mcp_event", lambda *_args: None)
    monkeypatch.setattr(
        "app.integrations.api.mcp.refresh_server_catalog.delay",
        lambda *_args: None,
    )

    connect_response = client.post(
        "/api/v1/mcp/composio/toolkits/gmail/connect",
        headers=_headers(owner),
    )

    assert connect_response.status_code == 201
    assert connect_response.json()["authorization_url"].startswith("https://connect.composio.dev/")
    assert created_sessions[0]["user_id"] == expected_identity
    assert created_sessions[0]["toolkits"] == ["gmail"]
    assert "tools" not in created_sessions[0]
    assert created_sessions[0]["session_preset"] == "direct_tools"
    assert created_sessions[0]["mcp"] is True
    public_config = connect_response.json()["server"]["config"]
    assert "composio_session_ciphertext" not in public_config
    assert "composio_session_nonce" not in public_config
    assert "composio_session_id" not in public_config

    server_id = connect_response.json()["server"]["id"]
    set_db_tenant_context(db_session, owner.tenant_id)
    set_db_user_context(db_session, owner.user_id)
    server = db_session.execute(
        select(MCPServer).where(MCPServer.id == uuid.UUID(server_id))
    ).scalar_one()
    policy = db_session.execute(
        select(MCPConnectionPolicy).where(MCPConnectionPolicy.server_id == server.id)
    ).scalar_one()
    assert "hosted-session-secret" not in str(server.config)
    assert server.config["composio_session_ciphertext"]
    assert server.config["composio_pending_connected_account_id"] == "ca_example_123"
    assert (
        ComposioService(db_session, settings)._decrypt_session_id(
            server.config,
            tenant_id=owner.tenant_id,
            user_id=owner.user_id,
            server_id=server.id,
        )
        == "hosted-session-secret"
    )
    assert policy.read_only is False
    assert policy.default_tool_mode == "always_allow"
    assert policy.approval_rules == {
        "write": "needs_approval",
        "delete": "needs_approval",
        "external_message": "needs_approval",
    }

    callback_url = "/api/v1/mcp/composio/oauth/complete"
    callback_headers = _headers(owner)
    forged_callback = client.post(
        callback_url,
        headers=callback_headers,
        json={
            "toolkit_slug": "gmail",
            "connected_account_id": "ca_forged_456",
            "status": "success",
        },
    )
    assert forged_callback.status_code == 409
    assert connection_lookups == []

    resolved_account_owner = composio_user_id(other_user.tenant_id, other_user.user_id)
    callback_response = client.post(
        callback_url,
        headers=callback_headers,
        json={
            "toolkit_slug": "gmail",
            "connected_account_id": "ca_example_123",
            "status": "success",
        },
    )
    assert callback_response.status_code == 409
    assert connection_lookups == [("ca_example_123", 5)]

    resolved_account_owner = expected_identity
    callback_response = client.post(
        callback_url,
        headers=callback_headers,
        json={
            "toolkit_slug": "gmail",
            "connected_account_id": "ca_example_123",
            "status": "success",
        },
    )
    assert callback_response.status_code == 200
    assert callback_response.json() == {"status": "connecting", "server_id": server_id}
    assert connection_lookups == [("ca_example_123", 5), ("ca_example_123", 5)]

    wrong_owner_response = client.post(
        callback_url,
        headers=_headers(other_user),
        json={
            "toolkit_slug": "gmail",
            "connected_account_id": "ca_example_123",
            "status": "success",
        },
    )
    assert wrong_owner_response.status_code == 409
    replay_response = client.post(
        callback_url,
        headers=callback_headers,
        json={
            "toolkit_slug": "gmail",
            "connected_account_id": "ca_example_123",
            "status": "success",
        },
    )
    assert replay_response.status_code == 409


def test_composio_no_auth_toolkit_installs_without_oauth_or_public_origin(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    user = seed_user(
        "tenant-composio-no-auth",
        "composio-no-auth@example.com",
        "StrongPass!1234",
        ("user",),
    )
    settings = get_settings()
    settings.averqel_public_origin = None
    refreshes: list[tuple[str, str]] = []

    class FakeSession:
        session_id = "no-auth-session"

    sdk = SimpleNamespace(
        toolkits=SimpleNamespace(
            get=lambda _slug: {
                "slug": "weather",
                "name": "Weather",
                "no_auth": True,
                "meta": {"description": "Weather data", "tools_count": 1},
            }
        ),
        sessions=SimpleNamespace(create=lambda **_kwargs: FakeSession()),
    )
    monkeypatch.setattr(ComposioService, "_client", lambda *_args, **_kwargs: sdk)
    monkeypatch.setattr("app.integrations.api.mcp._publish_mcp_event", lambda *_args: None)
    monkeypatch.setattr(
        "app.integrations.api.mcp.refresh_server_catalog.delay",
        lambda server_id, tenant_id: refreshes.append((server_id, tenant_id)),
    )

    response = client.post(
        "/api/v1/mcp/composio/toolkits/weather/connect",
        headers=_headers(user),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["authorization_required"] is False
    assert payload["authorization_url"] is None
    assert payload["server"]["status"] == "connecting"
    assert refreshes == [(payload["server"]["id"], str(user.tenant_id))]


def test_deepspace_discovers_and_executes_composio_tool_for_owning_user(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    db_session: Session,
    monkeypatch,
) -> None:
    owner = seed_user(
        "tenant-composio-deepspace",
        "composio-deepspace@example.com",
        "StrongPass!1234",
        ("user",),
    )
    other_user = seed_user(
        "tenant-composio-deepspace-other",
        "composio-deepspace-other@example.com",
        "StrongPass!1234",
        ("user",),
    )
    settings = get_settings()
    set_db_tenant_context(db_session, owner.tenant_id)
    set_db_user_context(db_session, owner.user_id)
    server = MCPServer(
        tenant_id=owner.tenant_id,
        user_id=owner.user_id,
        provider_slug="composio:gmail",
        name="Google Gmail",
        transport="streamable_http",
        config={
            "mcp_catalog_last_sync_at": datetime.now(UTC).isoformat(),
            "mcp_tools_cache": [
                {
                    "name": "GMAIL_GET_MESSAGE",
                    "description": "Read a Gmail message by ID",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"message_id": {"type": "string"}},
                        "required": ["message_id"],
                        "additionalProperties": False,
                    },
                }
            ],
        },
        catalog_revision=1,
        enabled=True,
        status="connected",
    )
    db_session.add(server)
    db_session.flush()
    db_session.add(
        MCPConnectionPolicy(
            tenant_id=owner.tenant_id,
            user_id=owner.user_id,
            server_id=server.id,
            read_only=True,
            risk_ceiling="read",
            default_tool_mode="always_allow",
            default_enabled=True,
        )
    )
    db_session.commit()
    set_db_tenant_context(db_session, owner.tenant_id)
    set_db_user_context(db_session, owner.user_id)

    monkeypatch.setattr(
        ComposioService,
        "mcp_endpoint_config",
        lambda *_args, **_kwargs: {
            "auth_mode": "mcp",
            "credentials": {
                "server_url": "https://backend.composio.dev/mcp/session",
                "transport": "streamable_http",
                "oauth_mode": "none",
                "headers": {"x-api-key": "test-session-key"},
            },
        },
    )
    remote_calls: list[tuple[str, dict[str, str]]] = []

    class RemoteSession:
        async def call_tool(self, name: str, arguments: dict[str, str]) -> SimpleNamespace:
            remote_calls.append((name, arguments))
            return SimpleNamespace(
                isError=False,
                structuredContent={"message_id": arguments["message_id"]},
                content=[SimpleNamespace(type="text", text="Message loaded")],
            )

    @asynccontextmanager
    async def fake_session(_runtime):
        yield RemoteSession()

    monkeypatch.setattr(MCPConnectorRuntime, "session", fake_session)
    auth = SimpleNamespace(tenant_id=owner.tenant_id, user_id=owner.user_id)
    conversation_id = uuid.uuid4()
    bridge = DeepSpaceMCPBridge(db_session, settings)
    bindings = bridge.tools_for_conversation(auth=auth, conversation_id=conversation_id)
    broker = MCPToolBroker()
    search = broker.search(bindings, "get Gmail message")

    assert search["status"] == "ok"
    assert search["matches"][0]["tool"] == "GMAIL_GET_MESSAGE"
    tool_ref = search["matches"][0]["tool_ref"]
    assert broker.get_schema(bindings, tool_ref)["input_schema"]["required"] == ["message_id"]
    binding = broker.resolve(bindings, tool_ref)
    assert binding is not None

    set_db_tenant_context(db_session, other_user.tenant_id)
    set_db_user_context(db_session, other_user.user_id)
    other_bindings = DeepSpaceMCPBridge(
        db_session,
        settings,
    ).tools_for_conversation(
        auth=SimpleNamespace(tenant_id=other_user.tenant_id, user_id=other_user.user_id),
        conversation_id=conversation_id,
    )
    assert other_bindings == {}
    set_db_tenant_context(db_session, owner.tenant_id)
    set_db_user_context(db_session, owner.user_id)

    async def execute() -> dict[str, object]:
        return await bridge.execute(
            auth=auth,
            conversation_id=conversation_id,
            binding=binding,
            arguments={"message_id": "message-123"},
        )

    result = anyio.run(execute)

    assert result["is_error"] is False
    assert "Message loaded" in result["rendered_text"]
    assert remote_calls == [("GMAIL_GET_MESSAGE", {"message_id": "message-123"})]
