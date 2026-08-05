from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import anyio
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.deepspace.models.mission_snapshot import DeepSpaceMissionSnapshot
from app.integrations.models.mcp_connection_policy import MCPConnectionPolicy
from app.integrations.models.mcp_server import MCPRegistryEntry, MCPServer
from app.integrations.services import mcp_runtime
from app.integrations.services.mcp_runtime import evaluate_mcp_tool_policy
from app.platform.database.session import set_db_tenant_context
from app.query.models.conversation import Conversation
from tests.conftest import SeededUser


def _server(
    db_session: Session, seeded: SeededUser
) -> tuple[MCPServer, Conversation, DeepSpaceMissionSnapshot]:
    server = MCPServer(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        name="Phase 5 MCP",
        transport="streamable_http",
        config={
            "server_url": "https://example.com/mcp",
            "mcp_catalog_last_sync_at": datetime.now(UTC).isoformat(),
            "mcp_tools_cache": [
                {"name": "read_inbox", "risk_labels": ["read"]},
                {"name": "send_message", "risk_labels": ["external_message"]},
            ],
        },
        catalog_revision=7,
        status="connected",
        enabled=True,
    )
    conversation = Conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Phase 5 conversation",
    )
    db_session.add_all([server, conversation])
    db_session.flush()
    mission = DeepSpaceMissionSnapshot(
        mission_id=uuid4(),
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        status="running",
        payload={},
    )
    policy = MCPConnectionPolicy(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        server_id=server.id,
        allowed_tools=[],
        denied_tools=[],
        read_only=False,
        risk_ceiling="external_message",
        approval_rules={
            "write": "needs_approval",
            "delete": "needs_approval",
            "external_message": "needs_approval",
        },
        tool_modes={"read_inbox": "always_allow", "send_message": "needs_approval"},
        default_enabled=True,
        deepspace_overrides={},
        conversation_overrides={},
    )
    db_session.add_all([mission, policy])
    db_session.commit()
    set_db_tenant_context(db_session, seeded.tenant_id)
    return server, conversation, mission


def test_phase5_policy_matrix_is_deny_first(
    db_session: Session,
    seed_user,
) -> None:
    seeded = seed_user(
        "tenant-phase5-policy", "phase5-policy@example.com", "StrongPass!1234", ("admin",)
    )
    server, conversation, mission = _server(db_session, seeded)
    policy = db_session.query(MCPConnectionPolicy).filter_by(server_id=server.id).one()
    policy.conversation_overrides = {str(conversation.id): True}
    policy.deepspace_overrides = {str(mission.mission_id): True}
    db_session.commit()
    set_db_tenant_context(db_session, seeded.tenant_id)

    read_decision = evaluate_mcp_tool_policy(
        db=db_session,
        server=server,
        tool_name="read_inbox",
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        deepspace_id=mission.mission_id,
        tool={"name": "read_inbox", "risk_labels": ["read"]},
        expected_catalog_revision=7,
        max_age_seconds=300,
    )
    assert read_decision.allowed is True
    assert read_decision.approval_requirement == "auto"
    assert read_decision.risk_level == "read"

    write_decision = evaluate_mcp_tool_policy(
        db=db_session,
        server=server,
        tool_name="send_message",
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        deepspace_id=mission.mission_id,
        tool={"name": "send_message", "risk_labels": ["external_message"]},
        expected_catalog_revision=7,
        max_age_seconds=300,
    )
    assert write_decision.allowed is True
    assert write_decision.requires_approval is True

    policy.denied_tools = ["read_inbox"]
    db_session.commit()
    set_db_tenant_context(db_session, seeded.tenant_id)
    denied_decision = evaluate_mcp_tool_policy(
        db=db_session,
        server=server,
        tool_name="read_inbox",
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        deepspace_id=mission.mission_id,
        tool={"name": "read_inbox", "risk_labels": ["read"]},
        expected_catalog_revision=7,
        max_age_seconds=300,
    )
    assert denied_decision.allowed is False
    assert "explicitly blocked" in denied_decision.reason

    policy.denied_tools = []
    policy.approval_rules = {"external_message": "blocked"}
    policy.tool_modes = {"send_message": "always_allow"}
    db_session.commit()
    set_db_tenant_context(db_session, seeded.tenant_id)
    risk_blocked_decision = evaluate_mcp_tool_policy(
        db=db_session,
        server=server,
        tool_name="send_message",
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        deepspace_id=mission.mission_id,
        tool={"name": "send_message", "risk_labels": ["external_message"]},
        expected_catalog_revision=7,
        max_age_seconds=300,
    )
    assert risk_blocked_decision.allowed is False
    assert "risk-level policy" in risk_blocked_decision.reason


def test_phase5_scope_provider_and_catalog_guards(
    db_session: Session,
    seed_user,
) -> None:
    seeded = seed_user(
        "tenant-phase5-guards", "phase5-guards@example.com", "StrongPass!1234", ("admin",)
    )
    server, conversation, mission = _server(db_session, seeded)
    policy = db_session.query(MCPConnectionPolicy).filter_by(server_id=server.id).one()
    policy.conversation_overrides = {str(conversation.id): True}
    policy.deepspace_overrides = {str(mission.mission_id): True}
    db_session.commit()
    set_db_tenant_context(db_session, seeded.tenant_id)

    stale_revision = evaluate_mcp_tool_policy(
        db=db_session,
        server=server,
        tool_name="read_inbox",
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        deepspace_id=mission.mission_id,
        tool={"name": "read_inbox", "risk_labels": ["read"]},
        expected_catalog_revision=6,
        max_age_seconds=300,
    )
    assert stale_revision.allowed is False
    assert "catalog changed" in stale_revision.reason

    policy.conversation_overrides = {}
    db_session.commit()
    set_db_tenant_context(db_session, seeded.tenant_id)
    missing_scope = evaluate_mcp_tool_policy(
        db=db_session,
        server=server,
        tool_name="read_inbox",
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        deepspace_id=mission.mission_id,
        tool={"name": "read_inbox", "risk_labels": ["read"]},
        expected_catalog_revision=7,
        max_age_seconds=300,
    )
    # Connected accounts are user-scoped and available to every owned
    # conversation by default; no conversation-id override is required.
    assert missing_scope.allowed is True

    entry = MCPRegistryEntry(
        source="phase5-test",
        server_name="phase5-disabled-provider",
        provider_slug="phase5-disabled-provider",
        publisher_type="community",
        display_name="Disabled Provider",
        remote_url="https://example.com/mcp",
        trust_status="rejected",
    )
    db_session.add(entry)
    db_session.flush()
    server.registry_entry_id = entry.id
    db_session.commit()
    set_db_tenant_context(db_session, seeded.tenant_id)
    disabled_provider = evaluate_mcp_tool_policy(
        db=db_session,
        server=server,
        tool_name="read_inbox",
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        conversation_id=conversation.id,
        deepspace_id=mission.mission_id,
        tool={"name": "read_inbox", "risk_labels": ["read"]},
        expected_catalog_revision=7,
        max_age_seconds=300,
    )
    assert disabled_provider.allowed is False
    assert "no longer approved" in disabled_provider.reason


def test_phase5_remote_call_is_blocked_before_runtime(
    db_session: Session,
    seed_user,
    monkeypatch,
) -> None:
    seeded = seed_user(
        "tenant-phase5-boundary", "phase5-boundary@example.com", "StrongPass!1234", ("admin",)
    )
    server, conversation, mission = _server(db_session, seeded)
    policy = db_session.query(MCPConnectionPolicy).filter_by(server_id=server.id).one()
    policy.conversation_overrides = {}
    policy.deepspace_overrides = {str(mission.mission_id): True}
    policy.default_enabled = False
    db_session.commit()
    set_db_tenant_context(db_session, seeded.tenant_id)

    def _must_not_build_runtime(**_kwargs):
        raise AssertionError("remote runtime must not be built for a blocked policy")

    monkeypatch.setattr(mcp_runtime, "build_mcp_server_runtime", _must_not_build_runtime)

    async def _run() -> dict[str, object]:
        return await mcp_runtime.execute_mcp_server_tool(
            db=db_session,
            settings=get_settings(),
            server=server,
            tool_name="read_inbox",
            arguments={},
            conversation_id=conversation.id,
            deepspace_id=mission.mission_id,
        )

    result = anyio.run(_run)
    assert result["error_code"] == "mcp_policy_blocked"
