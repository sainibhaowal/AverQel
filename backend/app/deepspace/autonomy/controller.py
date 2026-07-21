from __future__ import annotations

from collections import Counter
from typing import Any

from app.deepspace.autonomy.contracts import (
    AutonomyDecision,
    CompletionEvidence,
    DecisionKind,
    GoalContract,
)


class AutonomyController:
    """Deterministic supervisor for the model/tool loop.

    The controller never invents completion. It only authorizes completion when
    observed tool evidence satisfies the current goal contract.
    """

    _TEST_MARKERS = ("pytest", "test", "lint", "typecheck", "mypy", "ruff", "build", "compile")
    _PASS_MARKERS = ("passed", "pass", "success", "successful", "verified", "ok")
    _FAIL_MARKERS = ("failed", "failure", "error", "traceback", "assertionerror", "invalid")

    def __init__(self, goal: GoalContract, *, max_repairs: int = 2) -> None:
        self.goal = goal
        self.max_repairs = max(0, int(max_repairs))
        self._events: list[dict[str, Any]] = []
        self._action_counts: Counter[str] = Counter()
        self._repairs = 0
        self._isolation_ready = not goal.isolation_required
        self._observed_verification_commands: set[str] = set()

    def set_isolation_ready(self, ready: bool) -> None:
        self._isolation_ready = bool(ready)

    def evaluate_goal(self) -> CompletionEvidence:
        """Evaluate observed evidence against the current goal contract."""
        return self._evidence()

    def evaluate_trajectory(self) -> dict[str, Any]:
        """Return bounded progress signals used by the supervisor."""
        evidence = self._evidence()
        return {
            "tool_successes": evidence.tool_successes,
            "tool_failures": evidence.tool_failures,
            "repeated_actions": evidence.repeated_actions,
            "artifact_changes": evidence.artifact_changes,
            "no_progress": bool(
                evidence.repeated_actions >= 2 and evidence.artifact_changes == 0
            ),
        }

    @property
    def events(self) -> list[dict[str, Any]]:
        return [dict(event) for event in self._events]

    def observe(self, event: dict[str, Any]) -> AutonomyDecision:
        """Record one tool observation and choose the next bounded action."""
        payload = dict(event)
        self._events.append(payload)
        name = str(payload.get("tool_name") or payload.get("name") or "unknown")
        self._action_counts[name] += 1
        output = str(payload.get("output") or payload.get("text") or "")
        normalized = output.lower()
        success = bool(payload.get("success"))
        tool_input = str(payload.get("tool_input") or payload.get("command") or "").lower()
        verification_text = f"{normalized} {tool_input}"
        is_verification = name == "bash" and any(marker in verification_text for marker in self._TEST_MARKERS)
        if name == "bash":
            for command in self.goal.verification_commands:
                if command.lower() in tool_input:
                    self._observed_verification_commands.add(command)
        is_review = name in {"git", "bash"} and "diff" in f"{tool_input} {normalized}"
        review_pass = is_review and success and not any(marker in normalized for marker in self._FAIL_MARKERS)
        verification_pass = bool(payload.get("verification_pass")) or (
            is_verification
            and any(marker in normalized for marker in self._PASS_MARKERS)
            and not any(marker in normalized for marker in self._FAIL_MARKERS)
        )
        verification_failure = bool(payload.get("verification_failure")) or (
            is_verification and any(marker in normalized for marker in self._FAIL_MARKERS)
        )
        changed = payload.get("changed_files") or payload.get("files_changed") or payload.get("artifact_changed")
        evidence = self._evidence(
            verification_pass=verification_pass,
            verification_failure=verification_failure,
            changed=changed,
            unsafe=payload.get("error_kind") in {"security_block", "unsafe_action"},
            review_pass=review_pass,
        )
        if evidence.unsafe_actions:
            return AutonomyDecision(DecisionKind.ASK_HUMAN, "unsafe execution evidence requires operator review", evidence)
        if verification_failure or (not success and self._repairs < self.max_repairs):
            self._repairs += 1
            return AutonomyDecision(DecisionKind.REPAIR, "the latest tool evidence failed; repair the root cause and verify again", evidence, {"repair_attempt": self._repairs})
        if not success and self._repairs >= self.max_repairs:
            return AutonomyDecision(DecisionKind.STOP, "repair budget exhausted without verified progress", evidence)
        if self._repeated_action(name):
            return AutonomyDecision(DecisionKind.REPLAN, "the same action repeated without sufficient new evidence", evidence)
        return AutonomyDecision(DecisionKind.CONTINUE, "bounded progress is still possible", evidence)

    def completion(self, *, final_text: str = "") -> AutonomyDecision:
        evidence = self.evaluate_goal()
        if evidence.unsafe_actions:
            return AutonomyDecision(DecisionKind.ASK_HUMAN, "unsafe evidence prevents automatic completion", evidence)
        if self.goal.requires_artifact_change and evidence.artifact_changes == 0:
            return AutonomyDecision(DecisionKind.CONTINUE, "coding task has no observed artifact change", evidence)
        if self.goal.requires_verification and evidence.verification_passes == 0:
            return AutonomyDecision(DecisionKind.CONTINUE, "coding task has no passing verification evidence", evidence)
        if self.goal.verification_commands and not set(self.goal.verification_commands).issubset(
            self._observed_verification_commands
        ):
            return AutonomyDecision(DecisionKind.CONTINUE, "declared verification commands have not all run", evidence)
        if evidence.verification_failures:
            return AutonomyDecision(DecisionKind.REPAIR, "verification evidence still contains failures", evidence)
        if self.goal.coding_task and evidence.review_passes == 0:
            return AutonomyDecision(DecisionKind.CONTINUE, "the change has no observed diff-review evidence", evidence)
        if self.goal.isolation_required and not self._isolation_ready:
            return AutonomyDecision(DecisionKind.ASK_HUMAN, "coding isolation was not provisioned", evidence)
        if not final_text.strip() and not evidence.tool_successes:
            return AutonomyDecision(DecisionKind.STOP, "no result or execution evidence was produced", evidence)
        return AutonomyDecision(DecisionKind.FINISH, "completion contract is satisfied by observed evidence", evidence)

    def _repeated_action(self, name: str) -> bool:
        return self._action_counts[name] >= 3 and not any(
            event.get("changed_files") or event.get("files_changed") or event.get("artifact_changed")
            for event in self._events[-3:]
        )

    def _evidence(
        self,
        *,
        verification_pass: bool = False,
        verification_failure: bool = False,
        changed: Any = None,
        unsafe: bool = False,
        review_pass: bool = False,
    ) -> CompletionEvidence:
        passes = sum(1 for event in self._events if event.get("verification_pass")) + int(verification_pass)
        failures = sum(1 for event in self._events if event.get("verification_failure")) + int(verification_failure)
        reviews = sum(bool(event.get("review_pass")) for event in self._events) + int(review_pass)
        for event in self._events[-1:]:
            event.setdefault("verification_pass", verification_pass)
            event.setdefault("verification_failure", verification_failure)
            event.setdefault("review_pass", review_pass)
        artifacts = sum(
            len(event.get("changed_files") or event.get("files_changed"))
            if isinstance(event.get("changed_files") or event.get("files_changed"), list)
            else int(bool(event.get("changed_files") or event.get("files_changed") or event.get("artifact_changed")))
            for event in self._events
        ) + (len(changed) if isinstance(changed, list) else int(bool(changed)))
        return CompletionEvidence(
            tool_successes=sum(bool(event.get("success")) for event in self._events),
            tool_failures=sum(not bool(event.get("success")) for event in self._events),
            verification_passes=passes,
            verification_failures=failures,
            review_passes=reviews,
            artifact_changes=artifacts,
            evidence_count=sum(bool(str(event.get("output") or event.get("text") or "").strip()) for event in self._events),
            repeated_actions=sum(max(0, count - 1) for count in self._action_counts.values()),
            unsafe_actions=sum(bool(event.get("error_kind") in {"security_block", "unsafe_action"}) for event in self._events) + int(unsafe),
            isolation_ready=self._isolation_ready,
        )
