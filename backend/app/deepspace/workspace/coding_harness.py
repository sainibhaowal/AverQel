from __future__ import annotations

import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class CodingMissionContract:
    """The explicit boundary for an autonomous coding session."""

    objective: str
    repository: str | None = None
    branch: str | None = None
    allowed_paths: tuple[str, ...] = ()
    verification_commands: tuple[str, ...] = ()
    network_enabled: bool = False
    max_seconds: int = 1800
    max_tool_calls: int = 48
    definition_of_done: tuple[str, ...] = ()
    max_tokens: int = 120_000
    max_cost_usd: float = 10.0
    output_max_chars: int = 12_000
    secret_scopes: tuple[str, ...] = ()
    isolation_mode: str = "git_worktree"
    container_image: str | None = None


@dataclass(slots=True)
class CodingHarness:
    """Command and evidence boundary used by coding missions.

    Isolation is supplied by the configured workspace root/container. This
    object makes the contract explicit and prevents an agent from silently
    widening commands or network access during a run.
    """

    contract: CodingMissionContract
    tool_calls: int = 0
    changed_files: set[str] = field(default_factory=set)
    verification: list[dict[str, Any]] = field(default_factory=list)
    review_summary: str = ""
    remaining_risks: list[str] = field(default_factory=list)
    worktree: Path | None = None
    container_id: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    tokens_used: int = 0
    cost_usd: float = 0.0

    _ALLOWED_COMMANDS = frozenset(
        {
            "bash", "cat", "cp", "find", "git", "grep", "head", "ls", "make",
            "mypy", "npm", "node", "poetry", "pytest", "python", "python3", "rg",
            "ruff", "sed", "tail", "uv", "which",
        }
    )
    _NETWORK_COMMANDS = frozenset({"curl", "wget", "nc", "ssh", "scp", "ftp"})

    def validate_command(self, command: str) -> tuple[bool, str | None]:
        if time.monotonic() - self.started_at > self.contract.max_seconds:
            return False, "coding time budget exhausted"
        if self.tokens_used >= self.contract.max_tokens:
            return False, "coding token budget exhausted"
        if self.cost_usd >= self.contract.max_cost_usd:
            return False, "coding cost budget exhausted"
        self.tool_calls += 1
        if self.tool_calls > self.contract.max_tool_calls:
            return False, "coding tool-call budget exhausted"
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            return False, f"invalid shell syntax: {exc}"
        if not tokens:
            return False, "empty command"
        executable = Path(tokens[0]).name
        if executable in {"bash", "sh", "python", "python3", "node"} and any(
            token in {"-c", "-e", "--eval"} for token in tokens[1:]
        ):
            return False, "inline script execution is disabled; use a reviewed file"
        if executable in self._NETWORK_COMMANDS and not self.contract.network_enabled:
            return False, f"network command '{executable}' is disabled for this coding mission"
        if executable not in self._ALLOWED_COMMANDS and executable not in self._NETWORK_COMMANDS:
            return False, f"command '{executable}' is not in the coding allowlist"
        if executable == "git" and len(tokens) > 1 and tokens[1] in {
            "push",
            "reset",
            "clean",
            "checkout",
            "restore",
            "commit",
            "merge",
            "rebase",
        }:
            return False, f"git side effect '{tokens[1]}' requires an explicit release gate"
        if not self.contract.network_enabled and any(
            token in self._NETWORK_COMMANDS for token in tokens[1:]
        ):
            return False, "network access is disabled for this coding mission"
        if any(token in {"/", "~", ".."} for token in tokens[1:]):
            return False, "command contains an unrestricted filesystem target"
        return True, None

    def record_usage(self, *, tokens: int = 0, cost_usd: float = 0.0) -> None:
        self.tokens_used += max(0, int(tokens))
        self.cost_usd += max(0.0, float(cost_usd))

    def validate_path(self, path: str) -> tuple[bool, str | None]:
        """Keep writes inside the workspace and optional mission allowlist."""
        candidate = Path(str(path or ""))
        if not str(path).strip() or candidate.is_absolute() or ".." in candidate.parts:
            return False, "path escapes the restricted workspace"
        if self.contract.allowed_paths and not any(
            candidate == Path(allowed) or Path(allowed) in candidate.parents
            for allowed in self.contract.allowed_paths
        ):
            return False, "path is outside the coding mission allowlist"
        return True, None

    def prepare_worktree(self, *, root: Path) -> Path:
        """Create an isolated detached worktree when a repository is supplied.

        The operation is opt-in (``contract.repository``) and never mutates the
        caller's checked-out branch. Callers should remove the returned path
        after publishing a reviewed diff.
        """
        if not self.contract.repository:
            raise ValueError("coding mission has no repository configured")
        repository = Path(self.contract.repository).resolve()
        root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        destination = root / f"mission-{uuid.uuid4().hex[:12]}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        branch = self.contract.branch or f"deepspace/mission-{uuid.uuid4().hex[:10]}"
        if any(char in branch for char in ".. ~^:?*[\\\\"):
            raise ValueError("invalid coding branch name")
        subprocess.run(
            ["git", "-C", str(repository), "worktree", "add", "-b", branch, str(destination), "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.contract = CodingMissionContract(
            objective=self.contract.objective,
            definition_of_done=self.contract.definition_of_done,
            repository=self.contract.repository,
            branch=branch,
            allowed_paths=self.contract.allowed_paths,
            verification_commands=self.contract.verification_commands,
            network_enabled=self.contract.network_enabled,
            secret_scopes=self.contract.secret_scopes,
            isolation_mode=self.contract.isolation_mode,
            container_image=self.contract.container_image,
            max_seconds=self.contract.max_seconds,
            max_tool_calls=self.contract.max_tool_calls,
            max_tokens=self.contract.max_tokens,
            max_cost_usd=self.contract.max_cost_usd,
            output_max_chars=self.contract.output_max_chars,
        )
        self.worktree = destination
        return destination

    def prepare_container(self) -> str:
        """Start an optional network-disabled disposable container over the worktree."""
        if self.contract.isolation_mode != "container":
            raise ValueError("container isolation is not selected")
        if not self.worktree:
            raise ValueError("prepare the Git worktree before starting a container")
        image = self.contract.container_image or "python:3.12-slim"
        result = subprocess.run(
            [
                "docker", "run", "-d", "--rm", "--network", "none",
                "-v", f"{self.worktree}:/workspace:rw",
                "-w", "/workspace", image, "sleep", str(self.contract.max_seconds),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.container_id = result.stdout.strip()
        return self.container_id

    def stop_container(self) -> None:
        if not self.container_id:
            return
        subprocess.run(
            ["docker", "rm", "-f", self.container_id],
            check=False,
            capture_output=True,
            text=True,
        )
        self.container_id = None

    def discard_worktree(self) -> None:
        """Compensate failed coding work by deleting the isolated branch/worktree."""
        if self.container_id:
            self.stop_container()
        if not self.worktree or not self.contract.repository:
            return
        subprocess.run(
            ["git", "-C", self.contract.repository, "worktree", "remove", "--force", str(self.worktree)],
            check=False,
            capture_output=True,
            text=True,
        )
        if self.contract.branch:
            subprocess.run(
                ["git", "-C", self.contract.repository, "branch", "-D", self.contract.branch],
                check=False,
                capture_output=True,
                text=True,
            )
        self.worktree = None

    def record_tool_result(self, *, data: dict[str, Any], output: str, success: bool) -> None:
        files = data.get("changed_files") or data.get("files_changed") or []
        if isinstance(files, list):
            self.changed_files.update(str(path) for path in files)
        if data.get("verification"):
            self.verification.append(
                {
                    "success": bool(success and data.get("verification_pass", success)),
                    "output": str(output)[:4000],
                }
            )
        if data.get("review_summary"):
            self.review_summary = str(data["review_summary"])[:4000]
        risks = data.get("remaining_risks")
        if isinstance(risks, list):
            self.remaining_risks = [str(item)[:500] for item in risks[:20]]

    def publishable_output(self) -> dict[str, Any]:
        """Return the contract-shaped result; callers must still approve release."""
        patch = ""
        if self.worktree:
            diff = subprocess.run(
                ["git", "-C", str(self.worktree), "diff", "--binary"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            patch = diff.stdout[: self.contract.output_max_chars]
        return {
            "patch_or_commit": self.contract.branch or (str(self.worktree) if self.worktree else None),
            "patch": patch,
            "changed_files": sorted(self.changed_files),
            "verification": list(self.verification),
            "review_summary": self.review_summary,
            "remaining_risks": list(self.remaining_risks),
            "ready_to_publish": bool(
                self.changed_files and self.verification and self.review_summary
            ),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "repository": self.contract.repository,
            "branch": self.contract.branch,
            "changed_files": sorted(self.changed_files),
            "verification": list(self.verification),
            "tool_calls": self.tool_calls,
            "network_enabled": self.contract.network_enabled,
            "secret_scopes": list(self.contract.secret_scopes),
            "isolation_mode": self.contract.isolation_mode,
            "container_image": self.contract.container_image,
            "worktree": str(self.worktree) if self.worktree else None,
            "container_id": self.container_id,
            "definition_of_done": list(self.contract.definition_of_done),
            "ready_to_publish": bool(self.changed_files and self.verification and self.review_summary),
            "review_summary": self.review_summary,
            "remaining_risks": list(self.remaining_risks),
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "elapsed_seconds": round(time.monotonic() - self.started_at, 3),
        }
