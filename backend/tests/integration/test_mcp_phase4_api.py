from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.deepspace.models.mission_snapshot import DeepSpaceMissionSnapshot
from app.integrations.api.mcp import _marketplace_connectability
from app.integrations.models.mcp_server import MCPRegistryEntry, MCPServer
from app.query.models.conversation import Conversation
from tests.conftest import SeededUser


def _headers(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"admin"},
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def _server(db_session: Session, seeded: SeededUser) -> MCPServer:
    server = MCPServer(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        name="Phase 4 MCP",
        transport="streamable_http",
        config={
            "server_url": "https://example.com/mcp",
            "oauth_mode": "mcp_oauth",
            "auth_type": "oauth",
            "access_token": "must-not-leak",
            "client_secret": "must-not-leak",
            "endpoint_probe_error": "must-not-leak",
            "mcp_tools_cache": [
                {
                    "name": "read_inbox",
                    "description": "Read inbox messages.",
                    "inputSchema": {"type": "object"},
                },
                {
                    "name": "send_message",
                    "description": "Send a message.",
                    "inputSchema": {"type": "object"},
                },
            ],
        },
        status="connected",
        last_error="https://10.0.0.8:8443 failed with secret=must-not-leak",
    )
    db_session.add(server)
    db_session.commit()
    db_session.refresh(server)
    return server


def test_phase4_policy_tools_and_scoped_overrides_are_tenant_user_owned(
    client: TestClient,
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    owner = seed_user(
        "tenant-phase4-owner", "phase4-owner@example.com", "StrongPass!1234", ("admin",)
    )
    other = seed_user(
        "tenant-phase4-other", "phase4-other@example.com", "StrongPass!1234", ("admin",)
    )
    server = _server(db_session, owner)
    conversation = Conversation(tenant_id=owner.tenant_id, user_id=owner.user_id, title="Phase 4")
    mission = DeepSpaceMissionSnapshot(
        mission_id=server.id,
        tenant_id=owner.tenant_id,
        user_id=owner.user_id,
        conversation_id=conversation.id,
        status="running",
        payload={},
    )
    db_session.add_all([conversation, mission])
    db_session.commit()

    owner_headers = _headers(owner)
    other_headers = _headers(other)
    base = "/api/v1/mcp"

    server_response = client.get(f"{base}/servers/{server.id}", headers=owner_headers)
    assert server_response.status_code == 200
    assert "config" in server_response.json()
    assert "access_token" not in str(server_response.json())
    assert "client_secret" not in str(server_response.json())
    assert "must-not-leak" not in str(server_response.json())
    assert server_response.json()["last_error"] == "MCP connection failed"

    policy_response = client.get(f"{base}/servers/{server.id}/policy", headers=owner_headers)
    assert policy_response.status_code == 200
    assert policy_response.json()["read_only"] is True
    assert policy_response.json()["default_enabled"] is True

    update_response = client.put(
        f"{base}/servers/{server.id}/policy",
        headers=owner_headers,
        json={
            "allowed_tools": ["read_inbox"],
            "denied_tools": [],
            "read_only": True,
            "risk_ceiling": "read",
            "approval_rules": {"write": "needs_approval"},
            "tool_modes": {},
            "default_enabled": False,
            "deepspace_overrides": {},
            "conversation_overrides": {},
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["allowed_tools"] == ["read_inbox"]

    tools_response = client.get(f"{base}/servers/{server.id}/tools", headers=owner_headers)
    assert tools_response.status_code == 200
    assert {item["name"] for item in tools_response.json()["tools"]} == {
        "read_inbox",
        "send_message",
    }
    tool_response = client.put(
        f"{base}/servers/{server.id}/tools/send_message/policy",
        headers=owner_headers,
        json={"mode": "needs_approval"},
    )
    assert tool_response.status_code == 200
    assert tool_response.json()["mode"] == "needs_approval"

    conversation_list = client.get(
        f"{base}/conversations/{conversation.id}/connections",
        headers=owner_headers,
    )
    assert conversation_list.status_code == 200
    # The explicit policy update above disables the account; a conversation
    # remains disabled until the user enables that scope explicitly below.
    assert conversation_list.json()["connections"][0]["enabled"] is False
    conversation_update = client.put(
        f"{base}/conversations/{conversation.id}/connections/{server.id}",
        headers=owner_headers,
        json={"enabled": True},
    )
    assert conversation_update.status_code == 200
    assert conversation_update.json()["enabled"] is True

    deepspace_update = client.put(
        f"{base}/deepspaces/{server.id}/connections/{server.id}",
        headers=owner_headers,
        json={"enabled": True},
    )
    assert deepspace_update.status_code == 200
    deepspace_list = client.get(
        f"{base}/deepspaces/{server.id}/connections",
        headers=owner_headers,
    )
    assert deepspace_list.status_code == 200
    assert deepspace_list.json()["connections"][0]["enabled"] is True

    assert client.get(f"{base}/servers/{server.id}", headers=other_headers).status_code == 404
    assert (
        client.get(
            f"{base}/conversations/{conversation.id}/connections",
            headers=other_headers,
        ).status_code
        == 404
    )


def test_phase4_missing_scope_owner_cannot_change_override(
    client: TestClient,
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    owner = seed_user(
        "tenant-phase4-owner-2",
        "phase4-owner-2@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    server = _server(db_session, owner)
    unknown_id = server.id
    response = client.put(
        f"/api/v1/mcp/conversations/{unknown_id}/connections/{server.id}",
        headers=_headers(owner),
        json={"enabled": True},
    )
    assert response.status_code == 404


def test_approved_community_entry_is_connection_eligible() -> None:
    entry = MCPRegistryEntry(
        source="averqel-reviewed-community",
        server_name="community-example",
        provider_slug="community-example",
        publisher_type="community",
        display_name="Community Example",
        publisher="Example Community",
        remote_url="https://community.example/mcp",
        transport="streamable_http",
        trust_status="approved",
        oauth_requirements={"type": "anonymous"},
        raw_metadata={"catalog": {"connection_ready": True}},
    )

    assert _marketplace_connectability(entry) == (True, None)
