from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DecisionKind(StrEnum):
    CONTINUE = "continue"
    FINISH = "finish"
    REPAIR = "repair"
    REPLAN = "replan"
    ASK_HUMAN = "ask_human"
    STOP = "stop"


@dataclass(slots=True, frozen=True)
class GoalContract:
    """Explicit completion contract; the model cannot satisfy it by assertion alone."""

    objective: str
    coding_task: bool = False
    requires_artifact_change: bool = False
    requires_verification: bool = False
    verification_commands: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    isolation_required: bool = False
    acceptance_criteria: tuple[str, ...] = ()

    @classmethod
    def from_request(
        cls,
        objective: str,
        *,
        verification_commands: list[str] | tuple[str, ...] = (),
    ) -> GoalContract:
        text = str(objective or "").lower()
        coding = any(
            marker in text
            for marker in (
                "code",
                "file",
                "repository",
                "repo",
                "implement",
                "refactor",
                "fix",
                "test",
                "bug",
                "function",
                "module",
                "script",
            )
        )
        commands = tuple(str(item).strip() for item in verification_commands if str(item).strip())
        return cls(
            objective=str(objective or "").strip(),
            acceptance_criteria=(
                ("artifact_changed", "verification_pass", "diff_review", "isolation_ready")
                if coding
                else ("answer_or_tool_evidence",)
            ),
            coding_task=coding,
            requires_artifact_change=coding,
            requires_verification=coding,
            verification_commands=commands,
            required_evidence=("tool_result", "diff_review") if coding else (),
            isolation_required=coding,
        )


@dataclass(slots=True, frozen=True)
class CompletionEvidence:
    tool_successes: int = 0
    tool_failures: int = 0
    verification_passes: int = 0
    verification_failures: int = 0
    review_passes: int = 0
    isolation_ready: bool = False
    artifact_changes: int = 0
    evidence_count: int = 0
    repeated_actions: int = 0
    unsafe_actions: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures,
            "verification_passes": self.verification_passes,
            "verification_failures": self.verification_failures,
            "review_passes": self.review_passes,
            "isolation_ready": self.isolation_ready,
            "artifact_changes": self.artifact_changes,
            "evidence_count": self.evidence_count,
            "repeated_actions": self.repeated_actions,
            "unsafe_actions": self.unsafe_actions,
        }


@dataclass(slots=True, frozen=True)
class AutonomyDecision:
    kind: DecisionKind
    reason: str
    evidence: CompletionEvidence
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "reason": self.reason,
            "evidence": self.evidence.to_dict(),
            "metadata": dict(self.metadata),
        }
