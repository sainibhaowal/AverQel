from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from app.core.auth import AuthContext
from app.services.deepspace.workspace.workspace_mode import WorkspaceMode
from app.services.deepspace.workspace.workspace_service import WorkspaceService


class WorkspacePolicy:
    """Derive workspace-aware coding scope and validate file reach."""

    _CODE_PATTERNS = (
        r"\bcode\b",
        r"\bcoding\b",
        r"\brepo\b",
        r"\brepository\b",
        r"\bproject\b",
        r"\bworkspace\b",
        r"\bfile\b",
        r"\bfiles\b",
        r"\bfix\b",
        r"\bimplement\b",
        r"\bpatch\b",
        r"\bedit\b",
        r"\brefactor\b",
        r"\bdebug\b",
        r"\btest\b",
        r"\bpytest\b",
        r"\bnpm\b",
        r"\btsconfig\b",
        r"\bpackage\.json\b",
        r"\bmain\.py\b",
        r"\bapp\.py\b",
        r"\bsrc/\b",
    )
    _REPO_MARKERS = (
        ".git",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "Cargo.toml",
        "go.mod",
        "tsconfig.json",
        "setup.py",
        "manage.py",
    )
    _PATH_ARG_KEYS = (
        "path",
        "directory",
        "file_path",
        "input_path",
        "output_path",
        "source_path",
        "destination_path",
        "old_path",
        "new_path",
    )
    _SCOPED_TOOLS = {
        "read_file",
        "edit_file",
        "write_file",
        "notebook_edit",
        "glob",
        "grep",
        "bash",
        "file_read",
        "file_write",
        "file_edit",
        "file_list",
    }

    def resolve_mode(
        self,
        *,
        auth: AuthContext,
        user_message: str,
        note_content: str | None = None,
    ) -> WorkspaceMode:
        text = " ".join(
            part for part in [str(user_message or ""), str(note_content or "")] if part
        ).strip()
        if not self._looks_like_code_task(text):
            return WorkspaceMode()

        workspace = WorkspaceService(
            tenant_id=str(auth.tenant_id),
            user_id=str(auth.user_id),
        )
        workspace_root = str(workspace.workspace_root.resolve())
        repo_detected = any(
            (workspace.workspace_root / marker).exists()
            for marker in self._REPO_MARKERS
        )
        reasons = ["code_or_repo_task_detected"]
        if repo_detected:
            reasons.append("repo_markers_found")
        return WorkspaceMode(
            enabled=True,
            task_kind="code",
            workspace_root=workspace_root,
            allowed_paths=(workspace_root,),
            read_only_paths=(),
            repo_detected=repo_detected,
            source="workspace_policy",
            reasons=tuple(reasons),
        )

    def tool_is_scoped(self, tool_name: str) -> bool:
        return tool_name in self._SCOPED_TOOLS

    def extract_candidate_paths(
        self,
        tool_name: str,
        args: dict[str, Any] | None,
    ) -> list[str]:
        if not args or tool_name not in self._SCOPED_TOOLS:
            return []
        if tool_name == "bash":
            return self._extract_paths_from_command(str(args.get("command") or ""))
        candidates: list[str] = []
        for key in self._PATH_ARG_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
        return candidates

    def is_path_allowed(self, workspace_mode: WorkspaceMode, raw_path: str) -> bool:
        if not workspace_mode.enabled:
            return True
        try:
            path = Path(raw_path)
            if not path.is_absolute() and workspace_mode.workspace_root:
                path = Path(workspace_mode.workspace_root) / path
            path_obj = path.resolve()
            for allowed in workspace_mode.allowed_paths:
                allowed_obj = Path(allowed).resolve()
                if allowed_obj in path_obj.parents or allowed_obj == path_obj:
                    return True
            return False
        except Exception:
            return False

    def out_of_scope_paths(
        self,
        *,
        workspace_mode: WorkspaceMode,
        tool_name: str,
        args: dict[str, Any] | None,
    ) -> list[str]:
        return [
            path
            for path in self.extract_candidate_paths(tool_name, args)
            if not self.is_path_allowed(workspace_mode, path)
        ]

    def _looks_like_code_task(self, text: str) -> bool:
        normalized = str(text or "").lower()
        return any(re.search(pattern, normalized) for pattern in self._CODE_PATTERNS)

    def _extract_paths_from_command(self, command: str) -> list[str]:
        if not command.strip():
            return []
        candidates: list[str] = []
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        skip_next = {
            "-c",
            "--command",
            "--eval",
            "-e",
            "--grep",
            "--pattern",
            "-m",
            "--message",
        }
        previous = ""
        for token in tokens:
            cleaned = token.strip().strip(",;")
            if not cleaned:
                previous = token
                continue
            if previous in skip_next:
                previous = token
                continue
            if cleaned.startswith("-"):
                previous = token
                continue
            if (
                cleaned.startswith("/")
                or cleaned.startswith("./")
                or cleaned.startswith("../")
            ):
                candidates.append(cleaned)
            previous = token
        return candidates
