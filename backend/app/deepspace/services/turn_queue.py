"""Durable, ordered dispatch for user-submitted DeepSpace turns."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.deepspace.models.agent_runtime import DeepSpaceAgentRun, DeepSpaceRunEvent
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.message import Message
from app.deepspace.models.queue_control import DeepSpaceQueueControl
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.services.run_events import append_event
from app.realtime.event_bus import publish_event_sync
from app.system.services.cache_service import get_redis_client
from app.system.services.storage_lifecycle import StorageLifecycleService
from app.system.services.storage_quota import StorageQuotaService

QUEUEABLE_STATUSES = {"queued", "running", "cancelling", "awaiting_user", "awaiting_approval"}
# Failed attempts remain visible for an explicit retry, but never block later
# queued work. Running turns are represented by the active SSE/history record.
QUEUE_VISIBLE_STATUSES = {"queued", "awaiting_user", "awaiting_approval", "failed"}
ACTIVE_QUEUE_STATUSES = {"running", "cancelling", "awaiting_user", "awaiting_approval"}
TERMINAL_QUEUE_STATUSES = {"completed", "cancelled", "failed"}
PAUSED_QUEUE_STATUSES = {"awaiting_user", "awaiting_approval"}
MAX_TURNS_PER_CONVERSATION = 100
STALE_DISPATCH_AFTER = timedelta(minutes=10)
logger = logging.getLogger(__name__)


class QueueTurnEditConflictError(ValueError):
    """Raised when the queued prompt changed after the editor was opened."""


class QueueTurnNotEditableError(ValueError):
    """Raised when a worker or terminal transition already owns the turn."""


@dataclass(frozen=True)
class ClaimedTurn:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    client_request_id: str
    regenerate_message_id: uuid.UUID | None
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

    def _close_expired_worker_stream(
        self, *, turn: DeepSpaceQueuedTurn, run: DeepSpaceAgentRun
    ) -> None:
        """Close a browser stream when maintenance expires its worker lease."""
        if run.last_error not in {
            "worker_lease_expired",
            "cancelled_after_worker_lease_expired",
        }:
            return
        cancelled = run.last_error == "cancelled_after_worker_lease_expired"
        message_text = (
            "This DeepSpace run was stopped before it finished. Its saved prompt is available to regenerate."
            if cancelled
            else "The DeepSpace worker stopped before this response finished. The saved prompt is available to retry."
        )
        terminal_exists = self.db.execute(
            select(DeepSpaceRunEvent.id)
            .where(
                DeepSpaceRunEvent.tenant_id == turn.tenant_id,
                DeepSpaceRunEvent.user_id == turn.user_id,
                DeepSpaceRunEvent.conversation_id == turn.conversation_id,
                DeepSpaceRunEvent.client_request_id == turn.client_request_id,
                DeepSpaceRunEvent.event_name.in_({"done", "error"}),
            )
            .limit(1)
        ).scalar_one_or_none()
        if terminal_exists is not None:
            return

        if run.assistant_message_id is not None:
            assistant = self.db.execute(
                select(Message).where(
                    Message.id == run.assistant_message_id,
                    Message.conversation_id == turn.conversation_id,
                    Message.role == "assistant",
                )
            ).scalar_one_or_none()
            if assistant is not None:
                metadata = dict(assistant.metadata_json or {})
                if metadata.get("status") == "streaming":
                    metadata["status"] = "ready" if cancelled else "error"
                    metadata["runtime_active"] = False
                    if not cancelled:
                        metadata["error_code"] = "DEEPSPACE_WORKER_LEASE_EXPIRED"
                        metadata["error_message"] = message_text
                    assistant.metadata_json = metadata
                    self.db.flush()

        event_name = "done" if cancelled else "error"
        event_data = (
            {"conversation_id": str(turn.conversation_id), "status": "cancelled"}
            if cancelled
            else {
                "code": "DEEPSPACE_WORKER_LEASE_EXPIRED",
                "message": message_text,
                "error_category": "runtime",
            }
        )
        frame = f"event: {event_name}\ndata: {json.dumps(event_data, separators=(',', ':'))}\n\n"
        try:
            self.db.commit()
            append_event(
                self.db,
                settings=get_settings(),
                tenant_id=turn.tenant_id,
                user_id=turn.user_id,
                conversation_id=turn.conversation_id,
                client_request_id=turn.client_request_id,
                frame=frame,
                run_id=run.id,
            )
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception(
                "Failed to close an expired DeepSpace worker event stream",
                extra={"conversation_id": str(turn.conversation_id)},
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

    def resume_after_failure(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> bool:
        """Clear a legacy automatic failure pause while preserving the failed turn."""
        # Queue state and queue history are fetched frequently while a chat is
        # active. Check the exact repair condition without taking a row lock so
        # ordinary reads do not contend with the active turn's conversation
        # update. Recheck it under the normal conversation/control lock order
        # below before changing anything.
        recovery_candidate = self.db.execute(
            select(DeepSpaceQueueControl.conversation_id).where(
                DeepSpaceQueueControl.tenant_id == tenant_id,
                DeepSpaceQueueControl.user_id == user_id,
                DeepSpaceQueueControl.conversation_id == conversation_id,
                DeepSpaceQueueControl.paused.is_(True),
                DeepSpaceQueueControl.failed_request_id.is_not(None),
            )
        ).scalar_one_or_none()
        if recovery_candidate is None:
            return False

        self._conversation_for_update(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        control = self.db.execute(
            select(DeepSpaceQueueControl)
            .where(
                DeepSpaceQueueControl.tenant_id == tenant_id,
                DeepSpaceQueueControl.user_id == user_id,
                DeepSpaceQueueControl.conversation_id == conversation_id,
                DeepSpaceQueueControl.paused.is_(True),
                DeepSpaceQueueControl.failed_request_id.is_not(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if control is None:
            return False
        control.paused = False
        control.reason = None
        control.failed_request_id = None
        control.paused_at = None
        control.updated_at = datetime.now(UTC)
        self.db.commit()
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return True

    def enqueue(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_request_id: str,
        prompt: str,
        regenerate_message_id: uuid.UUID | None = None,
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
            regenerate_message_id=regenerate_message_id,
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

    def update_queued_prompt(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_request_id: str,
        expected_prompt: str,
        prompt: str,
    ) -> DeepSpaceQueuedTurn | None:
        """Edit a pending prompt in place without changing its queue position."""
        self._conversation_for_update(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
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
            return None
        if turn.status != "queued":
            raise QueueTurnNotEditableError(
                "This prompt has already started or is no longer pending."
            )
        if turn.regenerate_message_id is not None:
            raise QueueTurnNotEditableError(
                "A queued regeneration can be canceled or retried, but its saved prompt cannot be edited."
            )
        if turn.prompt != expected_prompt:
            raise QueueTurnEditConflictError(
                "This prompt was changed elsewhere. Refresh the queue and try again."
            )

        prior_bytes = StorageQuotaService.estimate_bytes(
            turn.prompt, turn.roles_json, turn.permissions_json, turn.attachment_file_ids_json
        )
        updated_bytes = StorageQuotaService.estimate_bytes(
            prompt[:4000],
            turn.roles_json,
            turn.permissions_json,
            turn.attachment_file_ids_json,
        )
        StorageQuotaService(self.db).ensure_capacity(
            tenant_id=tenant_id,
            user_id=user_id,
            additional_bytes=updated_bytes,
            replacing_bytes=prior_bytes,
        )
        turn.prompt = prompt[:4000]
        self._record_activity(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            kind="queue_turn_edited",
            size_bytes=updated_bytes,
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
        """Create one idempotent attempt linked to a failed turn."""
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
        request_id = str(client_request_id or uuid.uuid4())[:255]
        existing_request = self.db.execute(
            select(DeepSpaceQueuedTurn).where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.client_request_id == request_id,
            )
        ).scalar_one_or_none()
        if existing_request is not None:
            return existing_request

        existing_retry = self.db.execute(
            select(DeepSpaceQueuedTurn)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.resume_from_request_id == failed_request_id,
                # Do not create duplicate work while a retry is pending or
                # after it already succeeded. A failed child may be retried
                # with a new client request ID.
                DeepSpaceQueuedTurn.status.in_(QUEUEABLE_STATUSES | {"completed"}),
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
            regenerate_message_id=failed.regenerate_message_id,
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
                    DeepSpaceQueuedTurn.status.in_(QUEUE_VISIBLE_STATUSES | {"completed"}),
                )
                .order_by(
                    case((DeepSpaceQueuedTurn.status == "failed", 1), else_=0),
                    DeepSpaceQueuedTurn.priority.desc(),
                    DeepSpaceQueuedTurn.sequence.asc(),
                )
            )
            .scalars()
            .all()
        )
        # A retry is a new durable attempt so its lineage is preserved. Show
        # only the latest failed/active item in a retry chain, not every parent.
        retry_parent_ids = {
            str(row.resume_from_request_id) for row in rows if row.resume_from_request_id
        }
        return [
            row
            for row in rows
            if row.status in QUEUE_VISIBLE_STATUSES
            and (row.status != "failed" or str(row.client_request_id) not in retry_parent_ids)
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

        expired_runs: list[tuple[DeepSpaceQueuedTurn, DeepSpaceAgentRun]] = []
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
                expired_runs.append((turn, run))
            elif run.status in {"completed", "cancelled"}:
                turn.status = run.status
                turn.completed_at = datetime.now(UTC)
                if (
                    run.status == "cancelled"
                    and run.last_error == "cancelled_after_worker_lease_expired"
                ):
                    expired_runs.append((turn, run))
            else:
                turn.status = "queued"
                turn.started_at = None
        self.db.commit()
        for turn, run in expired_runs:
            self._close_expired_worker_stream(turn=turn, run=run)
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
        self.resume_after_failure(
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
            regenerate_message_id=turn.regenerate_message_id,
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
        self.db.commit()
        self._publish_queue_event(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )
        return True

    def next_queued_request_id(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        """Return the next FIFO/priority turn ID before asynchronous dispatch."""
        return self.db.execute(
            select(DeepSpaceQueuedTurn.client_request_id)
            .where(
                DeepSpaceQueuedTurn.tenant_id == tenant_id,
                DeepSpaceQueuedTurn.user_id == user_id,
                DeepSpaceQueuedTurn.conversation_id == conversation_id,
                DeepSpaceQueuedTurn.status == "queued",
            )
            .order_by(DeepSpaceQueuedTurn.priority.desc(), DeepSpaceQueuedTurn.sequence.asc())
            .limit(1)
        ).scalar_one_or_none()
