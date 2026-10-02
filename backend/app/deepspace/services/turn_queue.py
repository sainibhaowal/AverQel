"""Durable, ordered dispatch for user-submitted DeepSpace turns."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deepspace.models.agent_runtime import DeepSpaceAgentRun
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.message import Message
from app.deepspace.models.queue_control import DeepSpaceQueueControl
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.realtime.event_bus import publish_event_sync
from app.system.services.cache_service import get_redis_client
from app.system.services.storage_lifecycle import StorageLifecycleService
from app.system.services.storage_quota import StorageQuotaService

QUEUEABLE_STATUSES = {"queued", "running", "cancelling", "awaiting_user", "awaiting_approval"}
# Failed attempts and the currently running turn remain durable runtime/history
# state, not pending queue messages. The queue UI/API represents only work that
# is waiting to be sent or waiting for an explicit user/approval response.
QUEUE_VISIBLE_STATUSES = {"queued", "awaiting_user", "awaiting_approval"}
ACTIVE_QUEUE_STATUSES = {"running", "cancelling", "awaiting_user", "awaiting_approval"}
TERMINAL_QUEUE_STATUSES = {"completed", "cancelled", "failed"}
PAUSED_QUEUE_STATUSES = {"awaiting_user", "awaiting_approval"}
MAX_TURNS_PER_CONVERSATION = 100
STALE_DISPATCH_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class ClaimedTurn:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    client_request_id: str
    resume_from_request_id: str | None
    prompt: str
    thinking_enabled: bool
    reasoning_effort: str | None
    roles: list[str]
    permissions: list[str]
    attachment_file_ids: list[str]


@dataclass(frozen=True)
class QueueState:
    paused: bool
    reason: str | None = None
    failed_request_id: str | None = None
    paused_at: datetime | None = None


class DeepSpaceTurnQueueStore:
    """Transactional queue operations, always scoped to one tenant and user."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _publish_queue_event(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        event_type: str = "queue.changed",
    ) -> None:
        """Notify the authenticated owner after a committed queue transition."""
        try:
            state = self.state(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
            )
            visible_count = int(
                self.db.execute(
                    select(func.count())
                    .select_from(DeepSpaceQueuedTurn)
                    .where(
                        DeepSpaceQueuedTurn.tenant_id == tenant_id,
                        DeepSpaceQueuedTurn.user_id == user_id,
                        DeepSpaceQueuedTurn.conversation_id == conversation_id,
                        DeepSpaceQueuedTurn.status.in_(QUEUE_VISIBLE_STATUSES),
                    )
                ).scalar_one()
                or 0
            )
            publish_event_sync(
                get_redis_client(),
                tenant_id=tenant_id,
                user_id=user_id,
                event_type=event_type,
                resource="queues",
                data={
                    "conversation_id": str(conversation_id),
                    "paused": state.paused,
                    "reason": state.reason,
                    "failed_request_id": state.failed_request_id,
                    "visible_count": visible_count,
                },
            )
        except Exception:  # noqa: BLE001
            # Realtime delivery is advisory; queue durability is already committed.
            return

    def _record_activity(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        kind: str,
        size_bytes: int = 0,
    ) -> None:
        StorageLifecycleService(self.db).record_activity(
            tenant_id=tenant_id,
            owner_user_id=user_id,
            category="queues_and_tasks",
            source_type="conversation",
            source_id=str(conversation_id),
            activity_kind=kind,
            size_bytes=size_bytes,
        )

    def _conversation_for_update(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation:
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
        return conversation

    def state(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> QueueState:
        row = self.db.execute(
            select(DeepSpaceQueueControl).where(
                DeepSpaceQueueControl.tenant_id == tenant_id,
                DeepSpaceQueueControl.user_id == user_id,
                DeepSpaceQueueControl.conversation_id == conversation_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return QueueState(paused=False)
        return QueueState(
            paused=bool(row.paused),
            reason=row.reason,
            failed_request_id=row.failed_request_id,
            paused_at=row.paused_at,
        )

    def _set_paused_locked(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        paused: bool,
        reason: str | None = None,
        failed_request_id: str | None = None,
    ) -> None:
        control = self.db.execute(
            select(DeepSpaceQueueControl)
            .where(
                DeepSpaceQueueControl.tenant_id == tenant_id,
                DeepSpaceQueueControl.user_id == user_id,
                DeepSpaceQueueControl.conversation_id == conversation_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if control is None:
            control = DeepSpaceQueueControl(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                paused=paused,
                reason=reason[:2000] if reason else None,
                failed_request_id=failed_request_id,
                paused_at=now if paused else None,
                updated_at=now,
            )
            self.db.add(control)
            return
        control.paused = paused
        control.reason = reason[:2000] if reason else None
        control.failed_request_id = failed_request_id
        control.paused_at = now if paused else None
        control.updated_at = now

    def pause(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reason: str = "Queue paused by user.",
        failed_request_id: str | None = None,
    ) -> QueueState:
        self._conversation_for_update(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        self._set_paused_locked(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            paused=True,
            reason=reason,
            failed_request_id=failed_request_id,
        )
        self._record_activity(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            kind="queue_paused",
        )
        self.db.commit()
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return self.state(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)

    def resume(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> QueueState:
        self._conversation_for_update(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        self._set_paused_locked(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            paused=False,
        )
        self._record_activity(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            kind="queue_resumed",
        )
        self.db.commit()
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return self.state(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)

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
        attachment_file_ids: list[str] | None = None,
        steer: bool = False,
        resume_from_request_id: str | None = None,
    ) -> DeepSpaceQueuedTurn:
        self._conversation_for_update(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )

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
            resume_from_request_id=(
                resume_from_request_id[:255] if resume_from_request_id else None
            ),
            prompt=prompt[:4000],
            priority=1 if steer else 0,
            sequence=next_sequence,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            roles_json=sorted({str(role) for role in roles}),
            permissions_json=sorted({str(permission) for permission in permissions}),
            attachment_file_ids_json=sorted(
                {str(file_id) for file_id in (attachment_file_ids or [])}
            ),
            status="queued",
        )
        StorageQuotaService(self.db).ensure_capacity(
            tenant_id=tenant_id,
            user_id=user_id,
            additional_bytes=StorageQuotaService.estimate_bytes(
                turn.prompt, turn.roles_json, turn.permissions_json, turn.attachment_file_ids_json
            ),
        )
        self.db.add(turn)
        self._record_activity(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            kind="queue_turn_added",
            size_bytes=StorageQuotaService.estimate_bytes(
                turn.prompt, turn.roles_json, turn.permissions_json, turn.attachment_file_ids_json
            ),
        )
        self.db.commit()
        self.db.refresh(turn)
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return turn

    def retry_failed(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        failed_request_id: str,
        client_request_id: str | None = None,
    ) -> DeepSpaceQueuedTurn:
        """Create a new durable attempt that resumes a failed run checkpoint."""
        self._conversation_for_update(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        failed = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.client_request_id == failed_request_id,
                DeepSpaceQueuedTurn.status == "failed",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if failed is None:
            raise ValueError("Failed DeepSpace queue item not found")
        existing_retry = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.resume_from_request_id == failed_request_id,
                # Retrying the same failed checkpoint is idempotent. A later
                # retry may target the returned failed child directly, but
                # repeated clicks on its parent must not create duplicates.
                DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES | {"completed", "failed"}),
            )
            .order_by(DeepSpaceQueuedTurn.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing_retry is not None:
            return existing_retry
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
        request_id = str(client_request_id or uuid.uuid4())[:255]
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
        retry = DeepSpaceQueuedTurn(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            client_request_id=request_id,
            resume_from_request_id=failed_request_id,
            prompt=failed.prompt,
            priority=max(1, int(failed.priority or 0) + 1),
            sequence=next_sequence,
            thinking_enabled=failed.thinking_enabled,
            reasoning_effort=failed.reasoning_effort,
            roles_json=list(failed.roles_json or []),
            permissions_json=list(failed.permissions_json or []),
            attachment_file_ids_json=list(failed.attachment_file_ids_json or []),
            status="queued",
        )
        StorageQuotaService(self.db).ensure_capacity(
            tenant_id=tenant_id,
            user_id=user_id,
            additional_bytes=StorageQuotaService.estimate_bytes(
                retry.prompt,
                retry.roles_json,
                retry.permissions_json,
                retry.attachment_file_ids_json,
            ),
        )
        self.db.add(retry)
        self._record_activity(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            kind="queue_turn_retried",
            size_bytes=StorageQuotaService.estimate_bytes(
                retry.prompt,
                retry.roles_json,
                retry.permissions_json,
                retry.attachment_file_ids_json,
            ),
        )
        self.db.commit()
        self.db.refresh(retry)
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return retry

    def list_open(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[DeepSpaceQueuedTurn]:
        self.recover_stale_claims(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        rows = list(
            self.db.execute(
                select(DeepSpaceQueuedTurn)
                .where(
                    DeepSpaceQueuedTurn.tenant_id == tenant_id,
                    DeepSpaceQueuedTurn.user_id == user_id,
                    DeepSpaceQueuedTurn.conversation_id == conversation_id,
                    DeepSpaceQueuedTurn.status.in_(QUEUE_VISIBLE_STATUSES),
                )
                .order_by(DeepSpaceQueuedTurn.priority.desc(), DeepSpaceQueuedTurn.sequence.asc())
            )
            .scalars()
            .all()
        )
        # A retry is a new durable attempt so the checkpoint lineage is
        # preserved. The UI should nevertheless show one visible item per
        # retry chain, not the original failure plus every historical child.
        retry_parent_ids = {
            str(row.resume_from_request_id) for row in rows if row.resume_from_request_id
        }
        return [
            row
            for row in rows
            if row.status != "failed" or str(row.client_request_id) not in retry_parent_ids
        ]

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
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=turn.conversation_id
        )
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
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=turn.conversation_id
        )
        return True

    def conversation_id_for_request_id(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, client_request_id: str
    ) -> uuid.UUID | None:
        """Find a cancellable queued request without exposing another tenant's row."""
        return self.db.execute(
            select(DeepSpaceQueuedTurn.conversation_id)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.client_request_id == client_request_id,
                DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES),
            )
            .limit(1)
        ).scalar_one_or_none()

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
            self._publish_queue_event(
                tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
            )
        return len(turns)

    def clear_for_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        commit: bool = True,
    ) -> int:
        """Clear visible queue work while preserving chat/checkpoint history.

        Failed attempts are terminal checkpoint records, not queue messages, but
        they are included here so an explicit user "clear queue" action also
        clears a previously paused queue's retry state. Nothing is deleted.
        Active work is marked cancelling so the worker can finish safely.
        """
        turns = list(
            self.db.execute(
                select(DeepSpaceQueuedTurn)
                .where(
                    DeepSpaceQueuedTurn.tenant_id == tenant_id,
                    DeepSpaceQueuedTurn.user_id == user_id,
                    DeepSpaceQueuedTurn.conversation_id == conversation_id,
                    DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES | {"failed"}),
                )
                .with_for_update()
            )
            .scalars()
            .all()
        )
        now = datetime.now(UTC)
        for turn in turns:
            if turn.status in ACTIVE_QUEUE_STATUSES:
                turn.status = "cancelling"
            else:
                turn.status = "cancelled"
                turn.completed_at = now

        control = self.db.execute(
            select(DeepSpaceQueueControl)
            .where(
                DeepSpaceQueueControl.tenant_id == tenant_id,
                DeepSpaceQueueControl.user_id == user_id,
                DeepSpaceQueueControl.conversation_id == conversation_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if control is not None:
            control.paused = False
            control.reason = None
            control.failed_request_id = None
            control.paused_at = None
        if commit:
            self.db.commit()
            self._publish_queue_event(
                tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
            )
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
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return turn

    def release_claim(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_request_id: str,
    ) -> bool:
        """Return a claimed turn to the queue if Celery dispatch failed."""
        turn = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.client_request_id == client_request_id,
                DeepSpaceQueuedTurn.status == "running",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if turn is None:
            return False
        turn.status = "queued"
        turn.started_at = None
        self.db.commit()
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return True

    def recover_stale_claims(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        stale_after: timedelta = STALE_DISPATCH_AFTER,
    ) -> int:
        """Recover dispatcher claims that never created a worker run.

        A normal active worker has a live agent-run row. A claimed queue row
        without that row after the grace period means the dispatcher died
        between the queue commit and Celery submission. Re-queue it instead
        of leaving the conversation blocked forever.
        """
        cutoff = datetime.now(UTC) - stale_after
        turns = list(
            self.db.execute(
                select(DeepSpaceQueuedTurn)
                .where(
                    DeepSpaceQueuedTurn.tenant_id == tenant_id,
                    DeepSpaceQueuedTurn.user_id == user_id,
                    DeepSpaceQueuedTurn.conversation_id == conversation_id,
                    DeepSpaceQueuedTurn.status == "running",
                    DeepSpaceQueuedTurn.started_at.is_not(None),
                    DeepSpaceQueuedTurn.started_at < cutoff,
                )
                .with_for_update()
            )
            .scalars()
            .all()
        )
        if not turns:
            return 0

        active_run = (
            self.db.execute(
                select(DeepSpaceAgentRun.id).where(
                    DeepSpaceAgentRun.tenant_id == tenant_id,
                    DeepSpaceAgentRun.user_id == user_id,
                    DeepSpaceAgentRun.conversation_id == conversation_id,
                    DeepSpaceAgentRun.status.in_(ACTIVE_QUEUE_STATUSES),
                )
            )
            .scalars()
            .first()
        )
        if active_run is not None:
            return 0

        for turn in turns:
            # If a worker did start and completed before the process died in
            # its final queue update, preserve that durable outcome. Only a
            # claim with no matching runtime is the dispatcher gap and may be
            # safely returned to ``queued``.
            run = self.db.execute(
                select(DeepSpaceAgentRun)
                .join(Message, Message.id == DeepSpaceAgentRun.assistant_message_id)
                .where(
                    DeepSpaceAgentRun.tenant_id == tenant_id,
                    DeepSpaceAgentRun.user_id == user_id,
                    DeepSpaceAgentRun.conversation_id == conversation_id,
                    Message.conversation_id == conversation_id,
                    Message.metadata_json["client_request_id"].astext == turn.client_request_id,
                )
                .order_by(DeepSpaceAgentRun.updated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if run is None:
                turn.status = "queued"
                turn.started_at = None
                continue
            if run.status in {"failed", "blocked"}:
                turn.status = "failed"
                turn.error = (run.last_error or "DeepSpace agent run failed.")[:2000]
                turn.completed_at = datetime.now(UTC)
                self._set_paused_locked(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    paused=True,
                    reason=turn.error,
                    failed_request_id=turn.client_request_id,
                )
            elif run.status in {"completed", "cancelled"}:
                turn.status = run.status
                turn.completed_at = datetime.now(UTC)
            else:
                turn.status = "queued"
                turn.started_at = None
        self.db.commit()
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return len(turns)

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
            self._publish_queue_event(
                tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
            )
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
        self.recover_stale_claims(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
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
        if self.state(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id).paused:
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
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return ClaimedTurn(
            tenant_id=turn.tenant_id,
            user_id=turn.user_id,
            conversation_id=turn.conversation_id,
            client_request_id=turn.client_request_id,
            resume_from_request_id=turn.resume_from_request_id,
            prompt=turn.prompt,
            thinking_enabled=turn.thinking_enabled,
            reasoning_effort=turn.reasoning_effort,
            roles=[str(role) for role in turn.roles_json],
            permissions=[str(permission) for permission in turn.permissions_json],
            attachment_file_ids=[str(file_id) for file_id in (turn.attachment_file_ids_json or [])],
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
    ) -> bool:
        failed = status in {"failed", "blocked"}
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
            return False
        turn.status = status
        turn.error = error[:2000] if error else None
        turn.completed_at = datetime.now(UTC) if status in TERMINAL_QUEUE_STATUSES else None
        if failed:
            self._set_paused_locked(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                paused=True,
                reason=error
                or "DeepSpace turn failed. Review the error before resuming the queue.",
                failed_request_id=client_request_id,
            )
        self.db.commit()
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return True
