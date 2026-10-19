from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import anyio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.deepspace.services.mcp_bridge import DeepSpaceMCPBridge
from app.deepspace.services.mcp_tool_broker import MCPToolBroker
from app.integrations.models.composio_credential import ComposioCredential
from app.integrations.models.mcp_connection_policy import MCPConnectionPolicy
from app.integrations.models.mcp_server import MCPServer
from app.integrations.services.composio_service import (
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


def test_composio_status_is_user_visible_but_key_management_is_admin_only(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "tenant-composio-status",
        "composio-user@example.com",
        "StrongPass!1234",
        ("user",),
    )

    status_response = client.get("/api/v1/mcp/composio/status", headers=_headers(user))
    key_response = client.get("/api/v1/admin/providers/composio", headers=_headers(user))

    assert status_response.status_code == 200
    assert status_response.json()["configured"] is False
    assert "api_key" not in status_response.text
    assert key_response.status_code == 403


def test_allowlisted_admin_can_store_encrypted_composio_key_without_returning_it(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    db_session: Session,
    monkeypatch,
) -> None:
    admin = seed_user(
        "tenant-composio-key-admin",
        "composio-admin@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    settings = get_settings()
    settings.bootstrap_super_admin_emails = [admin.email]
    monkeypatch.setattr(
        "app.integrations.services.composio_service._sdk",
        lambda _api_key: SimpleNamespace(
            _client=SimpleNamespace(
                toolkits=SimpleNamespace(list=lambda **_kwargs: SimpleNamespace(items=[]))
            )
        ),
    )
    project_key = "composio-test-project-key-123"

    response = client.put(
        "/api/v1/admin/providers/composio",
        headers=_headers(admin, role="admin"),
        json={"api_key": project_key},
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert project_key not in response.text
    set_db_tenant_context(db_session, "bypass")
    credential = db_session.execute(
        select(ComposioCredential).where(ComposioCredential.id == 1)
    ).scalar_one()
    assert project_key.encode() not in credential.secret_ciphertext
    assert credential.secret_nonce
    assert credential.secret_kid

    read_response = client.get(
        "/api/v1/admin/providers/composio",
        headers=_headers(admin, role="admin"),
    )
    assert read_response.status_code == 200
    assert read_response.json()["configured"] is True
    assert project_key not in read_response.text

    remove_response = client.delete(
        "/api/v1/admin/providers/composio",
        headers=_headers(admin, role="admin"),
    )
    assert remove_response.status_code == 204
    set_db_tenant_context(db_session, "bypass")
    assert (
        db_session.execute(
            select(ComposioCredential).where(ComposioCredential.id == 1)
        ).scalar_one_or_none()
        is None
    )


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
    settings.composio_callback_verifier_enabled = True
    settings.averqel_public_origin = "https://averqel.example"
    created_sessions: list[dict[str, object]] = []
    expected_identity = composio_user_id(owner.tenant_id, owner.user_id)

    class FakeSession:
        session_id = "hosted-session-secret"

        @staticmethod
        def authorize(toolkit_slug: str, *, callback_url: str):
            assert toolkit_slug == "gmail"
            assert callback_url == "https://averqel.example/dashboard/mcp/composio/callback"
            return SimpleNamespace(
                redirect_url="https://connect.composio.dev/oauth/start?state=single-use"
            )

    def create_session(**kwargs):
        created_sessions.append(kwargs)
        return FakeSession()

    def complete_auth(*, user_id: str, session_uri: str):
        assert (
            session_uri
            == "https://backend.composio.dev/api/v3.1/connected_accounts/complete?state=once"
        )
        if user_id != expected_identity:
            raise ValueError("session owner mismatch")
        return SimpleNamespace(toolkit_slug="gmail", connected_account_id="ca_example_123")

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
        connected_accounts=SimpleNamespace(complete_auth=complete_auth),
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

    session_uri = "https://backend.composio.dev/api/v3.1/connected_accounts/complete?state=once"
    callback_response = client.post(
        "/api/v1/mcp/composio/oauth/complete",
        headers=_headers(owner),
        json={"session_uri": session_uri},
    )
    assert callback_response.status_code == 200
    assert callback_response.json() == {"status": "connecting", "server_id": server_id}
    assert session_uri not in callback_response.text

    wrong_owner_response = client.post(
        "/api/v1/mcp/composio/oauth/complete",
        headers=_headers(other_user),
        json={"session_uri": session_uri},
    )
    assert wrong_owner_response.status_code == 409
    assert session_uri not in wrong_owner_response.text


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
    settings.composio_callback_verifier_enabled = False
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
