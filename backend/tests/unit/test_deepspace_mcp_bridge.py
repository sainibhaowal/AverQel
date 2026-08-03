from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.deepspace.services.mcp_bridge import DeepSpaceMCPBridge


class _Result:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.values

    def scalar_one_or_none(self) -> object | None:
        return self.values[0] if self.values else None


class _Db:
    def __init__(self, server: object, policy: object) -> None:
        self.server = server
        self.policy = policy
        self.calls = 0

    def execute(self, _statement: object) -> _Result:
        self.calls += 1
        return _Result([self.server] if self.calls == 1 else [self.policy])


def test_bridge_exposes_only_attached_fresh_mcp_tools() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()
    server_id = uuid4()
    server = SimpleNamespace(
        id=server_id,
        tenant_id=tenant_id,
        user_id=user_id,
        registry_entry_id=None,
        name="Google Workspace",
        enabled=True,
        status="connected",
        catalog_revision=4,
        created_at=datetime.now(UTC),
        config={
            "mcp_catalog_last_sync_at": datetime.now(UTC).isoformat(),
            "mcp_tools_cache": [
                {
                    "name": "send_mail",
                    "description": "Send an email",
                    "risk_labels": ["external_message"],
                    "inputSchema": {
                        "type": "object",
                        "properties": {"to": {"type": "string"}},
                        "required": ["to"],
                    },
                }
            ],
        },
    )
    policy = SimpleNamespace(
        server_id=server_id,
        tenant_id=tenant_id,
        user_id=user_id,
        default_enabled=True,
        conversation_overrides={str(conversation_id): True},
    )
    bridge = DeepSpaceMCPBridge(
        _Db(server, policy),
        SimpleNamespace(mcp_catalog_max_age_seconds=3600),
    )

    bindings = bridge.tools_for_conversation(
        auth=SimpleNamespace(tenant_id=tenant_id, user_id=user_id),
        conversation_id=conversation_id,
    )

    assert len(bindings) == 1
    binding = next(iter(bindings.values()))
    assert binding.raw_name == "send_mail"
    assert binding.exposed_name.startswith("mcp_")
    assert binding.definition["function"]["parameters"]["required"] == ["to"]


def test_bridge_exposes_connected_mcp_tools_without_manual_scope_override() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()
    server = SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        registry_entry_id=None,
        name="Google Workspace",
        enabled=True,
        status="connected",
        catalog_revision=1,
        created_at=datetime.now(UTC),
        config={
            "mcp_catalog_last_sync_at": datetime.now(UTC).isoformat(),
            "mcp_tools_cache": [{"name": "read_mail", "inputSchema": {}}],
        },
    )
    policy = SimpleNamespace(
        server_id=server.id,
        tenant_id=tenant_id,
        user_id=user_id,
        default_enabled=True,
        conversation_overrides={},
    )
    bindings = DeepSpaceMCPBridge(
        _Db(server, policy),
        SimpleNamespace(mcp_catalog_max_age_seconds=3600),
    ).tools_for_conversation(
        auth=SimpleNamespace(tenant_id=tenant_id, user_id=user_id),
        conversation_id=conversation_id,
    )

    assert len(bindings) == 1
    assert next(iter(bindings.values())).raw_name == "read_mail"
