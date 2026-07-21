from __future__ import annotations

import pytest

from app.deepspace.execution.agent_permissions import PermissionLevel
from app.deepspace.execution.agent_tools import ALL_TOOLS, build_dynamic_mcp_tool
from app.deepspace.policy.execution_policy import ExecutionPolicy
from app.deepspace.execution.tool_contracts import ToolContract, infer_tool_contract
from app.deepspace.workspace.workspace_mode import WorkspaceMode


@pytest.mark.unit_no_db
def test_every_builtin_tool_has_a_complete_explicit_contract() -> None:
    assert ALL_TOOLS
    for tool in ALL_TOOLS:
        contract = tool.contract
        assert isinstance(contract, ToolContract)
        assert contract.risk_class
        assert contract.capabilities
        assert contract.tenant_scope in {"tenant", "tenant_user", "auth_context"}
        assert contract.timeout_seconds > 0
        assert contract.retry_policy.max_retries >= 0
        assert contract.approval_requirement in {"auto", "human", "block"}
        assert isinstance(contract.to_dict(), dict)


@pytest.mark.unit_no_db
def test_contracts_distinguish_safe_reads_writes_external_and_destructive_tools() -> None:
    read = infer_tool_contract(name="read_file", permission_level=PermissionLevel.TIER1_AUTO)
    write = infer_tool_contract(name="write_file", permission_level=PermissionLevel.TIER2_CONFIRM)
    external = infer_tool_contract(name="gmail_send", permission_level=PermissionLevel.TIER2_CONFIRM)
    destructive = infer_tool_contract(name="github_delete_file", permission_level=PermissionLevel.TIER2_CONFIRM)

    assert read.risk_class == "read_only"
    assert read.approval_requirement == "auto"
    assert read.idempotency_support is True
    assert write.risk_class == "internal_write"
    assert write.approval_requirement == "human"
    assert external.risk_class == "external_side_effect"
    assert external.compensation_required is True
    assert external.idempotency_support is False
    assert destructive.risk_class == "destructive"
    assert destructive.approval_requirement == "human"


@pytest.mark.unit_no_db
def test_dynamic_mcp_tools_are_untrusted_and_require_human_approval() -> None:
    tool = build_dynamic_mcp_tool(
        connector_id="00000000-0000-0000-0000-000000000001",
        mcp_tool_def={"name": "send_message", "inputSchema": {"type": "object"}},
    )
    assert tool.contract is not None
    assert tool.contract.untrusted is True
    assert tool.contract.approval_requirement == "human"
    assert tool.contract.idempotency_support is False


@pytest.mark.unit_no_db
def test_dynamic_mcp_tools_are_namespaced_by_server() -> None:
    first = build_dynamic_mcp_tool(
        connector_id="00000000-0000-0000-0000-000000000001",
        server_name="github",
        mcp_tool_def={"name": "search", "inputSchema": {"type": "object"}},
    )
    second = build_dynamic_mcp_tool(
        connector_id="00000000-0000-0000-0000-000000000002",
        server_name="notion",
        mcp_tool_def={"name": "search", "inputSchema": {"type": "object"}},
    )
    assert first.name == "mcp_github_search"
    assert second.name == "mcp_notion_search"
    assert first.name != second.name
    assert first.metadata["mcp_original_name"] == "search"


@pytest.mark.unit_no_db
def test_external_side_effects_pause_even_in_full_access_mode() -> None:
    decision = ExecutionPolicy.assess(
        mode="full_access",
        tool_name="gmail_send",
        tier=2,
        tool_contract=infer_tool_contract(name="gmail_send", permission_level=PermissionLevel.TIER2_CONFIRM),
    )
    assert decision.requires_human_approval is True
    assert decision.should_block is False
    assert decision.tool_contract is not None
    assert decision.tool_contract.risk_class == "external_side_effect"


@pytest.mark.unit_no_db
def test_internal_writes_pause_even_in_full_access_mode() -> None:
    decision = ExecutionPolicy.assess(
        mode="full_access",
        tool_name="write_file",
        tier=2,
        tool_contract=infer_tool_contract(name="write_file", permission_level=PermissionLevel.TIER2_CONFIRM),
        workspace_mode=WorkspaceMode(enabled=True, task_kind="code", workspace_root="/tmp/workspace", allowed_paths=("/tmp/workspace",), source="test"),
    )
    assert decision.requires_human_approval is True
    assert decision.should_block is False


@pytest.mark.unit_no_db
def test_invalid_scope_contract_is_blocked() -> None:
    contract = ToolContract(
        risk_class="read_only",
        capabilities=("read",),
        idempotency_support=True,
        retry_policy=infer_tool_contract(name="read_file", permission_level=PermissionLevel.TIER1_AUTO).retry_policy,
        timeout_seconds=30,
        compensation_required=False,
        approval_requirement="auto",
        tenant_scope="global",
        workspace_scope="optional",
    )
    decision = ExecutionPolicy.assess(mode="auto_review", tool_name="read_file", tier=1, tool_contract=contract)
    assert decision.should_block is True
