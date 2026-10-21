from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.deepspace.services.mcp_bridge import DeepSpaceMCPBridge, DeepSpaceMCPTool
from app.deepspace.services.mcp_tool_broker import MCPToolBroker


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
    assert binding.catalog["inputSchema"]["required"] == ["to"]


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


def test_bridge_keeps_stale_catalog_available_and_requests_refresh(monkeypatch) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
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
            "mcp_catalog_last_sync_at": "2020-01-01T00:00:00+00:00",
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
    queued: list[tuple[str, str]] = []

    class _Refresh:
        @staticmethod
        def delay(server_id: str, queued_tenant_id: str) -> None:
            queued.append((server_id, queued_tenant_id))

    monkeypatch.setattr(
        "app.integrations.workers.tasks_mcp.refresh_server_catalog",
        _Refresh,
    )
    bindings = DeepSpaceMCPBridge(
        _Db(server, policy),
        SimpleNamespace(mcp_catalog_max_age_seconds=900),
    ).tools_for_conversation(
        auth=SimpleNamespace(tenant_id=tenant_id, user_id=user_id),
        conversation_id=uuid4(),
    )

    assert len(bindings) == 1
    assert next(iter(bindings.values())).raw_name == "read_mail"
    assert queued == [(str(server.id), str(tenant_id))]


def test_composio_catalog_over_bridge_limit_remains_searchable() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()
    tools = [{"name": f"GOOGLE_DRIVE_ACTION_{index}", "inputSchema": {}} for index in range(1000)]
    tools.append({"name": "GOOGLE_DRIVE_UNIQUE_FINAL_ACTION", "inputSchema": {}})
    server = SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        registry_entry_id=None,
        provider_slug="composio:google_drive",
        name="Google Drive",
        enabled=True,
        status="connected",
        catalog_revision=1,
        created_at=datetime.now(UTC),
        config={
            "mcp_catalog_last_sync_at": datetime.now(UTC).isoformat(),
            "mcp_tools_cache": tools,
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

    search_result = MCPToolBroker().search(bindings, "unique final")

    assert len(bindings) == 1001
    assert search_result["matches"][0]["tool"] == "GOOGLE_DRIVE_UNIQUE_FINAL_ACTION"


def test_bridge_rebinds_a_tool_to_the_latest_cached_catalog() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()
    server_id = uuid4()
    now = datetime.now(UTC).isoformat()
    old_server = SimpleNamespace(id=server_id, name="Gmail")
    stale_binding = DeepSpaceMCPTool(
        exposed_name=f"mcp_{server_id.hex[:10]}_fetch_emails",
        server=old_server,
        raw_name="fetch_emails",
        catalog={"name": "fetch_emails", "inputSchema": {"type": "object", "properties": {}}},
        catalog_revision=4,
        server_name="Gmail",
    )
    current_server = SimpleNamespace(
        id=server_id,
        tenant_id=tenant_id,
        user_id=user_id,
        registry_entry_id=None,
        name="Gmail",
        enabled=True,
        status="connected",
        catalog_revision=5,
        config={
            "mcp_catalog_last_sync_at": now,
            "mcp_tools_cache": [
                {
                    "name": "fetch_emails",
                    "description": "Search recent messages",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                },
                {"name": "send_email", "inputSchema": {"type": "object", "properties": {}}},
            ],
        },
    )
    policy = SimpleNamespace(
        server_id=server_id,
        tenant_id=tenant_id,
        user_id=user_id,
        default_enabled=True,
    )
    bridge = DeepSpaceMCPBridge(
        _Db(current_server, policy),
        SimpleNamespace(mcp_catalog_max_age_seconds=3600),
    )

    refreshed = bridge.refresh_server_bindings(
        auth=SimpleNamespace(tenant_id=tenant_id, user_id=user_id),
        conversation_id=conversation_id,
        binding=stale_binding,
    )

    assert refreshed is not None
    assert set(refreshed) == {
        stale_binding.exposed_name,
        f"mcp_{server_id.hex[:10]}_send_email",
    }
    current_binding = refreshed[stale_binding.exposed_name]
    assert current_binding.catalog_revision == 5
    assert current_binding.catalog["inputSchema"]["properties"] == {"query": {"type": "string"}}
