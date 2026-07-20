from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.auth.dependencies import AuthContext
from app.services.deepspace.workspace.workspace_mode import WorkspaceMode
from app.services.deepspace.workspace.workspace_policy import WorkspacePolicy


def test_workspace_policy_enables_code_mode_for_repo_tasks() -> None:
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    policy = WorkspacePolicy()

    mode = policy.resolve_mode(
        auth=auth,
        user_message="Please inspect the repo and fix the failing test in src/app.py",
        note_content=None,
    )

    assert mode.enabled is True
    assert mode.task_kind == "code"
    assert mode.workspace_root is not None
    assert mode.allowed_paths


def test_workspace_policy_keeps_general_tasks_out_of_code_mode() -> None:
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    policy = WorkspacePolicy()

    mode = policy.resolve_mode(
        auth=auth,
        user_message="Summarize this document and explain the findings.",
        note_content=None,
    )

    assert mode.enabled is False
    assert mode.task_kind == "general"


def test_workspace_policy_blocks_paths_outside_workspace_root() -> None:
    policy = WorkspacePolicy()
    root = str(Path("/tmp/workspace-root").resolve())
    workspace_mode = WorkspaceMode(
        enabled=True,
        task_kind="code",
        workspace_root=root,
        allowed_paths=(root,),
        source="test",
    )

    assert policy.is_path_allowed(workspace_mode, "src/app.py") is True
    assert (
        policy.is_path_allowed(workspace_mode, "/tmp/workspace-root/src/app.py") is True
    )
    assert policy.is_path_allowed(workspace_mode, "/etc/passwd") is False
