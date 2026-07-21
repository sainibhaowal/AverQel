from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class WorkspaceMode:
    enabled: bool = False
    task_kind: str = "general"
    workspace_root: str | None = None
    allowed_paths: tuple[str, ...] = ()
    read_only_paths: tuple[str, ...] = ()
    repo_detected: bool = False
    source: str = "default"
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "task_kind": self.task_kind,
            "workspace_root": self.workspace_root,
            "allowed_paths": list(self.allowed_paths),
            "read_only_paths": list(self.read_only_paths),
            "repo_detected": self.repo_detected,
            "source": self.source,
            "reasons": list(self.reasons),
        }

    def instruction_block(self) -> str:
        if not self.enabled:
            return ""
        roots = ", ".join(self.allowed_paths) or "(workspace root only)"
        return (
            "WORKSPACE-AWARE CODE MODE:\n"
            f"- Treat the active workspace root as the only valid filesystem scope: {roots}\n"
            "- Prefer relative paths inside the workspace.\n"
            "- Do not read, write, or reference files outside the allowed workspace scope.\n"
            "- If the task appears to require files outside the workspace, stop and ask for clarification."
        )
