from __future__ import annotations

from app.deepspace.policy.execution_policy import ExecutionPolicy
from app.deepspace.workspace.workspace_mode import WorkspaceMode


def test_execution_policy_auto_review_requires_approval_for_writes() -> None:
    decision = ExecutionPolicy.assess(
        mode="auto_review",
        tool_name="write_file",
        tier=2,
    )
    assert decision.requires_human_approval is True
    assert decision.should_block is False


def test_execution_policy_full_access_allows_non_destructive_execution() -> None:
    decision = ExecutionPolicy.assess(
        mode="full_access",
        tool_name="bash",
        tier=3,
    )
    assert decision.requires_human_approval is False
    assert decision.should_block is False


def test_execution_policy_full_access_blocks_destructive_tools() -> None:
    decision = ExecutionPolicy.assess(
        mode="full_access",
        tool_name="delete_file",
        tier=4,
    )
    assert decision.requires_human_approval is False
    assert decision.should_block is True


def test_execution_policy_full_access_allows_task_spawn() -> None:
    decision = ExecutionPolicy.assess(
        mode="full_access",
        tool_name="task",
        tier=5,
    )

    assert decision.requires_human_approval is False
    assert decision.should_block is False


def test_execution_policy_blocks_package_install() -> None:
    # Test Node package manager block
    decision = ExecutionPolicy.assess(
        mode="auto_review",
        tool_name="bash",
        tier=3,
        args={"command": "npm install lodash"},
    )
    assert decision.should_block is True
    assert "restricted hybrid workspace" in decision.reason

    # Test Python package manager block
    decision = ExecutionPolicy.assess(
        mode="auto_review",
        tool_name="bash",
        tier=3,
        args={"command": "pip install requests"},
    )
    assert decision.should_block is True
    assert "restricted hybrid workspace" in decision.reason

    # Test VS Code extension installation block
    decision = ExecutionPolicy.assess(
        mode="auto_review",
        tool_name="bash",
        tier=3,
        args={"command": "code --install-extension egomet.kotlin-formatter"},
    )
    assert decision.should_block is True
    assert "restricted hybrid workspace" in decision.reason


def test_execution_policy_blocks_code_compiling_and_runs() -> None:
    # Test script execution block
    decision = ExecutionPolicy.assess(
        mode="auto_review",
        tool_name="bash",
        tier=3,
        args={"command": "python script.py"},
    )
    assert decision.should_block is True
    assert "Compiling or running user code scripts is blocked" in decision.reason


def test_execution_policy_blocks_out_of_scope_workspace_file_access() -> None:
    workspace_mode = WorkspaceMode(
        enabled=True,
        task_kind="code",
        workspace_root="/tmp/workspace-root",
        allowed_paths=("/tmp/workspace-root",),
        source="test",
    )

    decision = ExecutionPolicy.assess(
        mode="full_access",
        tool_name="read_file",
        tier=1,
        args={"path": "/etc/passwd"},
        workspace_mode=workspace_mode,
    )

    assert decision.should_block is True
    assert "workspace scope" in decision.reason


def test_execution_policy_allows_in_scope_workspace_file_access() -> None:
    workspace_mode = WorkspaceMode(
        enabled=True,
        task_kind="code",
        workspace_root="/tmp/workspace-root",
        allowed_paths=("/tmp/workspace-root",),
        source="test",
    )

    decision = ExecutionPolicy.assess(
        mode="auto_review",
        tool_name="read_file",
        tier=1,
        args={"path": "src/app.py"},
        workspace_mode=workspace_mode,
    )

    assert decision.should_block is False

    # Test binary compilation block
    decision = ExecutionPolicy.assess(
        mode="auto_review",
        tool_name="bash",
        tier=3,
        args={"command": "gcc -o main main.c && ./main"},
    )
    assert decision.should_block is True
    assert "Compiling or running user code scripts is blocked" in decision.reason
