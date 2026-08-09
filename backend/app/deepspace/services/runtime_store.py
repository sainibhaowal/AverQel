from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.deepspace.models.agent_runtime import DeepSpaceAgentRun, DeepSpaceAgentStep

DEFAULT_RETAINED_STEPS = 10_000
ACTIVE_RUN_STATUSES = {"running", "awaiting_user", "awaiting_approval", "cancelling"}
WORKER_RUN_STATUSES = {"running", "cancelling"}
DEFAULT_RUN_STALE_AFTER = timedelta(minutes=30)


class DeepSpaceRuntimeStore:
    """Persistence and cancellation boundary for DeepSpace runs."""

    def __init__(self, db: Session, *, retained_steps: int = DEFAULT_RETAINED_STEPS) -> None:
        self.db = db
        self.retained_steps = max(100, min(int(retained_steps), DEFAULT_RETAINED_STEPS))

    def create_run(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        checkpoint: dict[str, object] | None = None,
    ) -> DeepSpaceAgentRun:
        run = DeepSpaceAgentRun(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            status="running",
            checkpoint=dict(checkpoint or {}),
            heartbeat_at=datetime.now(UTC),
        )
        self.db.add(run)
        self.db.flush()
        self.db.commit()
        return run

    def update_checkpoint(
        self,
        *,
        run_id: uuid.UUID,
        status: str | None = None,
        checkpoint: dict[str, object] | None = None,
        last_error: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        values: dict[str, Any] = {"updated_at": now}
        if status is not None:
            values["status"] = status
        if checkpoint is not None:
            values["checkpoint"] = dict(checkpoint)
        if last_error is not None:
            values["last_error"] = last_error[:2000]
        if status in WORKER_RUN_STATUSES or status is None:
            values["heartbeat_at"] = now
        self.db.execute(
            update(DeepSpaceAgentRun).where(DeepSpaceAgentRun.id == run_id).values(**values)
        )
        self.db.commit()

    def heartbeat(self, *, run_id: uuid.UUID) -> bool:
        now = datetime.now(UTC)
        result = self.db.execute(
            update(DeepSpaceAgentRun)
            .where(
                DeepSpaceAgentRun.id == run_id,
                DeepSpaceAgentRun.status.in_(WORKER_RUN_STATUSES),
                DeepSpaceAgentRun.cancel_requested.is_(False),
            )
            .values(heartbeat_at=now, updated_at=now)
        )
        self.db.commit()
        return bool(getattr(result, "rowcount", 0))

    def live_worker_run_for_message(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        stale_after: timedelta = DEFAULT_RUN_STALE_AFTER,
    ) -> DeepSpaceAgentRun | None:
        cutoff = datetime.now(UTC) - stale_after
        return self.db.execute(
            select(DeepSpaceAgentRun)
            .where(
                DeepSpaceAgentRun.tenant_id == tenant_id,
                DeepSpaceAgentRun.user_id == user_id,
                DeepSpaceAgentRun.conversation_id == conversation_id,
                DeepSpaceAgentRun.assistant_message_id == assistant_message_id,
                DeepSpaceAgentRun.status.in_(WORKER_RUN_STATUSES),
                DeepSpaceAgentRun.cancel_requested.is_(False),
                DeepSpaceAgentRun.heartbeat_at.is_not(None),
                DeepSpaceAgentRun.heartbeat_at >= cutoff,
            )
            .order_by(DeepSpaceAgentRun.heartbeat_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def record_step(
        self,
        *,
        run_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        step_type: str,
        status: str,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        input_json: dict[str, object] | None = None,
        result_json: dict[str, object] | None = None,
    ) -> int:
        run = self.db.execute(
            select(DeepSpaceAgentRun).where(DeepSpaceAgentRun.id == run_id)
        ).scalar_one()
        sequence = int(run.last_sequence or 0) + 1
        step = DeepSpaceAgentStep(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            sequence=sequence,
            step_type=step_type[:40],
            tool_name=tool_name[:100] if tool_name else None,
            tool_call_id=tool_call_id[:255] if tool_call_id else None,
            status=status[:40],
            input_json=self._bounded_json(input_json),
            result_json=self._bounded_json(result_json),
        )
        self.db.add(step)
        run.last_sequence = sequence
        run.step_count = int(run.step_count or 0) + 1
        run.updated_at = datetime.now(UTC)
        if run.status in WORKER_RUN_STATUSES and not run.cancel_requested:
            run.heartbeat_at = run.updated_at
        self.db.flush()
        old_step_ids = (
            self.db.execute(
                select(DeepSpaceAgentStep.id)
                .where(DeepSpaceAgentStep.run_id == run_id)
                .order_by(DeepSpaceAgentStep.sequence.desc())
                .offset(self.retained_steps)
            )
            .scalars()
            .all()
        )
        if old_step_ids:
            self.db.execute(
                delete(DeepSpaceAgentStep).where(DeepSpaceAgentStep.id.in_(old_step_ids))
            )
        self.db.commit()
        return sequence

    def is_cancel_requested(self, *, run_id: uuid.UUID) -> bool:
        self.db.expire_all()
        run = self.db.execute(
            select(DeepSpaceAgentRun.cancel_requested).where(DeepSpaceAgentRun.id == run_id)
        ).scalar_one_or_none()
        return bool(run)

    def history_steps_for_message(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> list[dict[str, object]]:
        """Return the durable, UI-safe tool trajectory for one assistant turn."""
        run = self.db.execute(
            select(DeepSpaceAgentRun).where(
                DeepSpaceAgentRun.tenant_id == tenant_id,
                DeepSpaceAgentRun.user_id == user_id,
                DeepSpaceAgentRun.conversation_id == conversation_id,
                DeepSpaceAgentRun.assistant_message_id == assistant_message_id,
            )
        ).scalar_one_or_none()
        if run is None:
            return []
        steps = (
            self.db.execute(
                select(DeepSpaceAgentStep)
                .where(DeepSpaceAgentStep.run_id == run.id)
                .order_by(DeepSpaceAgentStep.sequence.asc())
            )
            .scalars()
            .all()
        )
        result: list[dict[str, object]] = []
        for step in steps:
            if step.step_type not in {"tool_start", "tool_result", "approval_requested"}:
                continue
            payload = dict(step.result_json or {})
            success = bool(payload.get("success", step.status == "completed"))
            result.append(
                {
                    "type": (
                        "tool_start"
                        if step.step_type == "tool_start"
                        else ("tool_result" if success else "tool_error")
                    ),
                    "step_id": f"runtime_{step.sequence}",
                    "tool_id": step.tool_call_id,
                    "tool_name": step.tool_name,
                    "tool_input": dict(step.input_json or {}),
                    "output": str(payload.get("output") or ""),
                    "success": success,
                    "status": step.status,
                    "started_at": step.created_at.isoformat(),
                    "completed_at": (step.completed_at or step.created_at).isoformat(),
                }
            )
        return result

    def get_run_for_approval(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        approval_id: str,
    ) -> DeepSpaceAgentRun | None:
        """Return only a user-owned run containing the requested approval."""
        runs = (
            self.db.execute(
                select(DeepSpaceAgentRun)
                .where(
                    DeepSpaceAgentRun.tenant_id == tenant_id,
                    DeepSpaceAgentRun.user_id == user_id,
                    DeepSpaceAgentRun.conversation_id == conversation_id,
                    DeepSpaceAgentRun.status.in_({"awaiting_approval", "running", "blocked"}),
                )
                .order_by(DeepSpaceAgentRun.updated_at.desc())
                .limit(25)
            )
            .scalars()
            .all()
        )
        for run in runs:
            checkpoint = run.checkpoint if isinstance(run.checkpoint, dict) else {}
            pending = checkpoint.get("pending_approval")
            if isinstance(pending, dict) and str(pending.get("approval_id") or "") == approval_id:
                return run
        return None

    def get_run_for_user_question(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        question_id: str,
    ) -> DeepSpaceAgentRun | None:
        """Return only a user-owned run waiting for this clarification answer."""
        runs = (
            self.db.execute(
                select(DeepSpaceAgentRun)
                .where(
                    DeepSpaceAgentRun.tenant_id == tenant_id,
                    DeepSpaceAgentRun.user_id == user_id,
                    DeepSpaceAgentRun.conversation_id == conversation_id,
                    # A clarification can be answered exactly once.  Once a
                    # worker claims it, the run is switched to ``running``;
                    # rejecting a second answer prevents two workers from
                    # resuming the same provider turn concurrently.
                    DeepSpaceAgentRun.status == "awaiting_user",
                )
                .order_by(DeepSpaceAgentRun.updated_at.desc())
                .limit(25)
            )
            .scalars()
            .all()
        )
        for run in runs:
            checkpoint = run.checkpoint if isinstance(run.checkpoint, dict) else {}
            pending = checkpoint.get("pending_user_question")
            if isinstance(pending, dict) and str(pending.get("question_id") or "") == question_id:
                return run
        return None

    def resolve_approval(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        approval_id: str,
        decision: str,
    ) -> dict[str, object] | None:
        """Persist an approval decision without executing the remote tool."""
        if decision not in {"approved", "denied"}:
            raise ValueError("Approval decision must be approved or denied.")
        run = self.get_run_for_approval(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            approval_id=approval_id,
        )
        if run is None:
            return None
        checkpoint = dict(run.checkpoint) if isinstance(run.checkpoint, dict) else {}
        pending = dict(checkpoint.get("pending_approval") or {})
        current_decision = str(pending.get("decision") or "")
        if current_decision and current_decision != "pending":
            return {**pending, "status": "already_resolved"}
        pending["decision"] = decision
        pending["resolved_at"] = datetime.now(UTC).isoformat()
        checkpoint["pending_approval"] = pending
        checkpoint["phase"] = "approval_resolved"
        run.checkpoint = checkpoint
        run.status = "running" if decision == "approved" else "blocked"
        run.updated_at = datetime.now(UTC)
        self.db.add(run)
        self.db.commit()
        return pending

    def clear_pending_approval(
        self, *, run_id: uuid.UUID, checkpoint: dict[str, object] | None = None
    ) -> None:
        """Remove a consumed approval while retaining the rest of the checkpoint."""
        values = dict(checkpoint or {})
        values.pop("pending_approval", None)
        values["phase"] = "tool"
        self.update_checkpoint(run_id=run_id, status="running", checkpoint=values)

    def request_cancel(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> bool:
        result = self.db.execute(
            update(DeepSpaceAgentRun)
            .where(
                DeepSpaceAgentRun.tenant_id == tenant_id,
                DeepSpaceAgentRun.user_id == user_id,
                DeepSpaceAgentRun.conversation_id == conversation_id,
                DeepSpaceAgentRun.status.in_(ACTIVE_RUN_STATUSES),
            )
            .values(cancel_requested=True, status="cancelling", updated_at=datetime.now(UTC))
        )
        self.db.commit()
        return bool(getattr(result, "rowcount", 0))

    def finish(self, *, run_id: uuid.UUID, status: str, error: str | None = None) -> None:
        values: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(UTC),
            "heartbeat_at": None,
        }
        if error:
            values["last_error"] = error[:2000]
        self.db.execute(
            update(DeepSpaceAgentRun).where(DeepSpaceAgentRun.id == run_id).values(**values)
        )
        self.db.commit()

    @staticmethod
    def _bounded_json(value: dict[str, object] | None) -> dict[str, object]:
        if not isinstance(value, dict):
            return {}
        # Inputs/results are audit data, not a second transcript. Keep step rows
        # bounded even when a provider returns a very large payload.
        encoded = str(value)
        if len(encoded) <= 20_000:
            return value
        return {"truncated": True, "preview": encoded[:19_500]}
