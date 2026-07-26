from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.deepspace.models.agent_runtime import DeepSpaceAgentRun, DeepSpaceAgentStep

DEFAULT_RETAINED_STEPS = 10_000
ACTIVE_RUN_STATUSES = {"running", "awaiting_user", "cancelling"}


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
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if status is not None:
            values["status"] = status
        if checkpoint is not None:
            values["checkpoint"] = dict(checkpoint)
        if last_error is not None:
            values["last_error"] = last_error[:2000]
        self.db.execute(
            update(DeepSpaceAgentRun).where(DeepSpaceAgentRun.id == run_id).values(**values)
        )
        self.db.commit()

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
        values: dict[str, Any] = {"status": status, "updated_at": datetime.now(UTC)}
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
