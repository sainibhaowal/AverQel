"""Durable, ordered dispatch for user-submitted DeepSpace turns."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deepspace.models.agent_runtime import DeepSpaceAgentRun
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn

QUEUEABLE_STATUSES = {"queued", "running", "cancelling", "awaiting_user", "awaiting_approval"}
ACTIVE_QUEUE_STATUSES = {"running", "cancelling", "awaiting_user", "awaiting_approval"}
TERMINAL_QUEUE_STATUSES = {"completed", "cancelled", "failed"}
PAUSED_QUEUE_STATUSES = {"awaiting_user", "awaiting_approval"}
MAX_TURNS_PER_CONVERSATION = 100


@dataclass(frozen=True)
class ClaimedTurn:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    client_request_id: str
    prompt: str
    thinking_enabled: bool
    reasoning_effort: str | None
    roles: list[str]
    permissions: list[str]


class DeepSpaceTurnQueueStore:
    """Transactional queue operations, always scoped to one tenant and user."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_request_id: str,
        prompt: str,
        thinking_enabled: bool,
        reasoning_effort: str | None = None,
        roles: list[str],
        permissions: list[str],
        steer: bool = False,
    ) -> DeepSpaceQueuedTurn:
        conversation = self.db.execute(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.kind == "deepspace",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if conversation is None:
            raise ValueError("DeepSpace conversation not found")

        existing = self.db.execute(
            select(DeepSpaceQueuedTurn).where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.client_request_id == client_request_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        queued_count = self.db.execute(
            select(func.count())
            .select_from(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES),
            )
        ).scalar_one()
        if int(queued_count or 0) >= MAX_TURNS_PER_CONVERSATION:
            raise OverflowError("DeepSpace queue is full for this conversation")

        next_sequence = (
            int(
                self.db.execute(
                    select(func.coalesce(func.max(DeepSpaceQueuedTurn.sequence), 0)).where(
                        DeepSpaceQueuedTurn.tenant_id == tenant_id,
                        DeepSpaceQueuedTurn.user_id == user_id,
                        DeepSpaceQueuedTurn.conversation_id == conversation_id,
                    )
                ).scalar_one()
                or 0
            )
            + 1
        )
        turn = DeepSpaceQueuedTurn(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            client_request_id=client_request_id[:255],
            prompt=prompt[:4000],
            priority=1 if steer else 0,
            sequence=next_sequence,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            roles_json=sorted({str(role) for role in roles}),
            permissions_json=sorted({str(permission) for permission in permissions}),
            status="queued",
        )
        self.db.add(turn)
        self.db.commit()
        self.db.refresh(turn)
        return turn

    def list_open(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[DeepSpaceQueuedTurn]:
        return list(
            self.db.execute(
                select(DeepSpaceQueuedTurn)
                .where(
                    DeepSpaceQueuedTurn.tenant_id == tenant_id,
                    DeepSpaceQueuedTurn.user_id == user_id,
                    DeepSpaceQueuedTurn.conversation_id == conversation_id,
                    DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES),
                )
                .order_by(DeepSpaceQueuedTurn.priority.desc(), DeepSpaceQueuedTurn.sequence.asc())
            )
            .scalars()
            .all()
        )

    def request_cancel(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_request_id: str,
    ) -> bool:
        turn = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.client_request_id == client_request_id,
                DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if turn is None:
            return False
        if turn.status == "queued" or turn.status in PAUSED_QUEUE_STATUSES:
            turn.status = "cancelled"
            turn.completed_at = datetime.now(UTC)
        else:
            turn.status = "cancelling"
        self.db.commit()
        return True

    def request_cancel_by_request_id(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, client_request_id: str
    ) -> bool:
        turn = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.client_request_id == client_request_id,
                DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if turn is None:
            return False
        if turn.status == "queued" or turn.status in PAUSED_QUEUE_STATUSES:
            turn.status = "cancelled"
            turn.completed_at = datetime.now(UTC)
        else:
            turn.status = "cancelling"
        self.db.commit()
        return True

    def cancel_all_for_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        commit: bool = True,
    ) -> int:
        """Cancel all pending, paused, or running queued turns for a conversation."""
        turns = list(
            self.db.execute(
                select(DeepSpaceQueuedTurn)
                .where(
                    DeepSpaceQueuedTurn.tenant_id == tenant_id,
                    DeepSpaceQueuedTurn.user_id == user_id,
                    DeepSpaceQueuedTurn.conversation_id == conversation_id,
                    DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES),
                )
                .with_for_update()
            )
            .scalars()
            .all()
        )
        if not turns:
            return 0
        now = datetime.now(UTC)
        for turn in turns:
            if turn.status == "queued" or turn.status in PAUSED_QUEUE_STATUSES:
                turn.status = "cancelled"
                turn.completed_at = now
            else:
                turn.status = "cancelling"
        if commit:
            self.db.commit()
        return len(turns)

    def promote(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_request_id: str,
    ) -> DeepSpaceQueuedTurn | None:
        """Move one still-pending follow-up ahead of other queued turns."""
        turn = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.client_request_id == client_request_id,
                DeepSpaceQueuedTurn.status == "queued",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if turn is None:
            return None
        priority = self.db.execute(
            select(func.coalesce(func.max(DeepSpaceQueuedTurn.priority), 0)).where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.status == "queued",
            )
        ).scalar_one()
        turn.priority = int(priority or 0) + 1
        self.db.commit()
        self.db.refresh(turn)
        return turn

    def resume_paused(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        commit: bool = True,
    ) -> str | None:
        """Claim the one paused turn that an approval or answer is resuming.

        A resumed run must keep the original request id.  It is both the
        durable event stream key and the queue record that prevents another
        turn from starting while the user decision is outstanding.
        """
        conversation = self.db.execute(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.kind == "deepspace",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if conversation is None:
            return None
        turn = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.status.in_(PAUSED_QUEUE_STATUSES),
            )
            .order_by(DeepSpaceQueuedTurn.sequence.asc())
            .with_for_update()
            .limit(1)
        ).scalar_one_or_none()
        if turn is None:
            return None
        turn.status = "running"
        turn.error = None
        if commit:
            self.db.commit()
        return turn.client_request_id

    def active_request_id(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        """Return the stream key for the active turn without changing its state."""
        return self.db.execute(
            select(DeepSpaceQueuedTurn.client_request_id)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.status.in_(ACTIVE_QUEUE_STATUSES),
            )
            .order_by(DeepSpaceQueuedTurn.sequence.asc())
            .limit(1)
        ).scalar_one_or_none()

    def claim_next(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ClaimedTurn | None:
        # Serialize dispatch per conversation. Without this row lock, two
        # Celery wake-ups could each observe an empty active slot and claim
        # different queued turns at the same time.
        conversation = self.db.execute(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.kind == "deepspace",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if conversation is None:
            return None
        # A user has one active turn per conversation. Paused runs keep the
        # queue intact until the user answers/approves or cancels them.
        active_queue_turn = self.db.execute(
            select(DeepSpaceQueuedTurn.id)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.status.in_(ACTIVE_QUEUE_STATUSES),
            )
            .limit(1)
        ).scalar_one_or_none()
        if active_queue_turn is not None:
            return None

        active_run = self.db.execute(
            select(DeepSpaceAgentRun.id)
            .where(
                DeepSpaceAgentRun.tenant_id == tenant_id,
                DeepSpaceAgentRun.user_id == user_id,
                DeepSpaceAgentRun.conversation_id == conversation_id,
                DeepSpaceAgentRun.status.in_(
                    {"running", "awaiting_user", "awaiting_approval", "cancelling"}
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        if active_run is not None:
            return None

        turn = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.status == "queued",
            )
            .order_by(DeepSpaceQueuedTurn.priority.desc(), DeepSpaceQueuedTurn.sequence.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if turn is None:
            return None
        turn.status = "running"
        turn.started_at = datetime.now(UTC)
        self.db.commit()
        return ClaimedTurn(
            tenant_id=turn.tenant_id,
            user_id=turn.user_id,
            conversation_id=turn.conversation_id,
            client_request_id=turn.client_request_id,
            prompt=turn.prompt,
            thinking_enabled=turn.thinking_enabled,
            reasoning_effort=turn.reasoning_effort,
            roles=[str(role) for role in turn.roles_json],
            permissions=[str(permission) for permission in turn.permissions_json],
        )

    def finish(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_request_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        if status not in TERMINAL_QUEUE_STATUSES | PAUSED_QUEUE_STATUSES:
            status = "failed"
        turn = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.client_request_id == client_request_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if turn is None:
            return
        turn.status = status
        turn.error = error[:2000] if error else None
        turn.completed_at = datetime.now(UTC) if status in TERMINAL_QUEUE_STATUSES else None
        self.db.commit()
