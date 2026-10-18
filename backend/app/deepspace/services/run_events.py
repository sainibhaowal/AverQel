"""Durable event log and live fan-out for detached DeepSpace runs."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

import redis
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.deepspace.models.agent_runtime import DeepSpaceRunEvent
from app.deepspace.services.reasoning_privacy import redact_reasoning_text
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.system.services.storage_quota import StorageQuotaService, ensure_capacity_if_supported
from app.system.services.user_notifications import add_user_notification

logger = logging.getLogger(__name__)


def channel_name(client_request_id: str) -> str:
    return f"deepspace:run:{client_request_id}"


def cancellation_key(tenant_id: uuid.UUID, user_id: uuid.UUID, client_request_id: str) -> str:
    return f"deepspace:cancel:{tenant_id}:{user_id}:{client_request_id}"


def event_name_from_frame(frame: str) -> str:
    for line in frame.splitlines():
        if line.startswith("event:"):
            return line.partition(":")[2].strip() or "message"
    return "message"


def is_terminal_event(event_name: str) -> bool:
    return event_name in {"done", "error"}


@dataclass(frozen=True, slots=True)
class PendingRunEvent:
    """A sequenced frame waiting for durable storage and live fan-out."""

    sequence: int
    frame: str
    run_id: uuid.UUID | None = None


def _live_event_payload(event: PendingRunEvent) -> str:
    return json.dumps(
        {"sequence": event.sequence, "frame": event.frame},
        separators=(",", ":"),
    )


def _publish_live_event(
    client: Any,
    *,
    client_request_id: str,
    event: PendingRunEvent,
) -> None:
    client.publish(channel_name(client_request_id), _live_event_payload(event))


def append_event_batch(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_request_id: str,
    events: Iterable[PendingRunEvent],
) -> list[DeepSpaceRunEvent]:
    """Persist an already-sequenced batch in one transaction.

    The worker assigns sequences before it queues frames. This keeps ordering
    stable while allowing database work to happen off the provider-consumer
    path. The explicit sequence is safe because the worker lock permits only
    one active writer for a client request id.
    """
    pending = list(events)
    if not pending:
        return []

    normalized_id = str(client_request_id).strip()
    db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )

    run_id = next((event.run_id for event in pending if event.run_id is not None), None)
    if run_id is not None:
        # The run metadata can arrive after the first lifecycle frames. Keep
        # the existing backfill behavior, but do it once per batch rather than
        # once on the provider-consumer path.
        db.execute(
            update(DeepSpaceRunEvent)
            .where(
                DeepSpaceRunEvent.tenant_id == tenant_id,
                DeepSpaceRunEvent.user_id == user_id,
                DeepSpaceRunEvent.conversation_id == conversation_id,
                DeepSpaceRunEvent.client_request_id == normalized_id,
                DeepSpaceRunEvent.run_id.is_(None),
            )
            .values(run_id=run_id)
        )

    ensure_capacity_if_supported(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        additional_bytes=sum(StorageQuotaService.estimate_bytes(event.frame) for event in pending),
    )
    persisted = [
        DeepSpaceRunEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=event.run_id,
            client_request_id=normalized_id,
            sequence=event.sequence,
            frame=event.frame,
            event_name=event_name_from_frame(event.frame),
        )
        for event in pending
    ]
    db.add_all(persisted)
    for event in persisted:
        if event.event_name not in {"done", "error"}:
            continue
        succeeded = event.event_name == "done"
        run_reference = event.run_id or normalized_id
        add_user_notification(
            db,
            tenant_id=tenant_id,
            recipient_user_id=user_id,
            event_domain="deepspace",
            event_type="run_completed" if succeeded else "run_failed",
            title="DeepSpace run completed" if succeeded else "DeepSpace run needs attention",
            message=(
                "Your DeepSpace run has finished. Open the conversation to review its response."
                if succeeded
                else "Your DeepSpace run stopped with an error. Open the conversation to review it and retry."
            ),
            href=f"/dashboard/deepspace?conversation={conversation_id}",
            resource_id=run_reference,
            idempotency_key=f"deepspace:{run_reference}:{event.event_name}",
        )
    db.commit()
    return persisted


def append_event(
    db: Session,
    *,
    settings: Settings,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_request_id: str,
    frame: str,
    run_id: uuid.UUID | None = None,
) -> DeepSpaceRunEvent:
    """Commit one frame before publishing it, so reconnects never miss it."""
    normalized_id = str(client_request_id).strip()
    latest = latest_sequence(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=normalized_id,
    )
    event = PendingRunEvent(sequence=latest + 1, frame=frame, run_id=run_id)
    persisted = append_event_batch(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=normalized_id,
        events=[event],
    )
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _publish_live_event(client, client_request_id=normalized_id, event=event)
        # redis-py does not ship complete typing for the dynamically-created
        # client; closing it is still the same runtime operation.
        cast(Any, client).close()
    except Exception:  # noqa: BLE001
        # PostgreSQL is authoritative. A reconnect will replay this event even
        # if Redis is temporarily unavailable.
        logger.warning("DeepSpace live event publish failed", exc_info=True)
    return persisted[0]


class AsyncRunEventFanout:
    """Keep provider consumption independent from per-frame persistence.

    PostgreSQL remains authoritative. A bounded durable queue limits memory
    growth and applies backpressure only when the database cannot keep up for
    a sustained period. Redis fan-out uses one client and a separate queue so
    a database commit does not sit between two provider chunks.
    """

    _MAX_BATCH_SIZE = 64
    _BATCH_FLUSH_SECONDS = 0.02
    _QUEUE_SIZE = 512

    def __init__(
        self,
        *,
        settings: Settings,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        client_request_id: str,
        initial_sequence: int,
    ) -> None:
        self.settings = settings
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.client_request_id = str(client_request_id).strip()
        self._next_sequence = max(0, int(initial_sequence)) + 1
        self._durable_queue: asyncio.Queue[PendingRunEvent | None] = asyncio.Queue(
            maxsize=self._QUEUE_SIZE
        )
        self._live_queue: asyncio.Queue[PendingRunEvent | None] = asyncio.Queue(
            maxsize=self._QUEUE_SIZE
        )
        self._durable_task: asyncio.Task[None] | None = None
        self._live_task: asyncio.Task[None] | None = None
        self._durable_error: BaseException | None = None

    async def start(self) -> None:
        self._durable_task = asyncio.create_task(self._persist_loop())
        self._live_task = asyncio.create_task(self._publish_loop())

    def _next_event(self, frame: str, run_id: uuid.UUID | None) -> PendingRunEvent:
        event = PendingRunEvent(
            sequence=self._next_sequence,
            frame=frame,
            run_id=run_id,
        )
        self._next_sequence += 1
        return event

    def _raise_if_durable_failed(self) -> None:
        if self._durable_error is not None:
            raise RuntimeError("DeepSpace durable event writer failed") from self._durable_error

    async def submit(self, *, frame: str, run_id: uuid.UUID | None) -> None:
        self._raise_if_durable_failed()
        event = self._next_event(frame, run_id)
        await self._durable_queue.put(event)
        self._raise_if_durable_failed()
        if is_terminal_event(event_name_from_frame(frame)):
            # A terminal event is published only after every preceding frame,
            # including itself, is durable. This preserves reconnect order.
            await self._durable_queue.join()
            self._raise_if_durable_failed()
        await self._live_queue.put(event)

    async def close(self) -> None:
        durable_error: BaseException | None = None
        try:
            await self._durable_queue.join()
            if self._durable_task is not None:
                await self._durable_queue.put(None)
                await self._durable_task
        except BaseException as exc:  # noqa: BLE001
            durable_error = exc

        try:
            await self._live_queue.join()
            if self._live_task is not None:
                await self._live_queue.put(None)
                await self._live_task
        except BaseException as exc:  # noqa: BLE001
            if durable_error is None:
                durable_error = exc

        self._raise_if_durable_failed()
        if durable_error is not None:
            raise durable_error

    async def _persist_loop(self) -> None:
        batch: list[PendingRunEvent] = []
        try:
            while True:
                first = await self._durable_queue.get()
                if first is None:
                    self._durable_queue.task_done()
                    return
                batch = [first]
                stop_after_batch = False
                deadline = asyncio.get_running_loop().time() + self._BATCH_FLUSH_SECONDS
                while len(batch) < self._MAX_BATCH_SIZE:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        next_event = await asyncio.wait_for(
                            self._durable_queue.get(), timeout=remaining
                        )
                    except TimeoutError:
                        break
                    if next_event is None:
                        self._durable_queue.task_done()
                        stop_after_batch = True
                        break
                    batch.append(next_event)

                await asyncio.to_thread(self._persist_batch, batch)
                for _ in batch:
                    self._durable_queue.task_done()
                if stop_after_batch:
                    return
        except BaseException as exc:  # noqa: BLE001
            self._durable_error = exc
            for _ in batch:
                self._durable_queue.task_done()
            while True:
                try:
                    self._durable_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self._durable_queue.task_done()

    def _persist_batch(self, events: list[PendingRunEvent]) -> None:
        db = get_session_factory()()
        try:
            db.execute(text("SET ROLE aks_app"))
            set_db_tenant_context(db, self.tenant_id)
            append_event_batch(
                db,
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                conversation_id=self.conversation_id,
                client_request_id=self.client_request_id,
                events=events,
            )
        except Exception:
            db.rollback()
            raise
        finally:
            try:
                db.rollback()
                db.execute(text("RESET ROLE"))
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            cast(Any, db).close()

    async def _publish_loop(self) -> None:
        client: Any | None = None
        try:
            client = redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
            while True:
                event = await self._live_queue.get()
                if event is None:
                    self._live_queue.task_done()
                    return
                try:
                    await asyncio.to_thread(
                        _publish_live_event,
                        client,
                        client_request_id=self.client_request_id,
                        event=event,
                    )
                except Exception:  # noqa: BLE001
                    # PostgreSQL is authoritative. A reconnect will replay
                    # the event even if Redis is temporarily unavailable.
                    logger.warning("DeepSpace live event publish failed", exc_info=True)
                finally:
                    self._live_queue.task_done()
        except BaseException:  # noqa: BLE001
            while True:
                try:
                    self._live_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self._live_queue.task_done()
            raise
        finally:
            if client is not None:
                try:
                    await asyncio.to_thread(cast(Any, client).close)
                except Exception:  # noqa: BLE001
                    logger.debug("DeepSpace live Redis cleanup failed", exc_info=True)


def load_events(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_request_id: str,
    after_sequence: int = 0,
) -> list[DeepSpaceRunEvent]:
    db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )
    return list(
        db.execute(
            select(DeepSpaceRunEvent)
            .where(
                DeepSpaceRunEvent.tenant_id == tenant_id,
                DeepSpaceRunEvent.user_id == user_id,
                DeepSpaceRunEvent.conversation_id == conversation_id,
                DeepSpaceRunEvent.client_request_id == str(client_request_id).strip(),
                DeepSpaceRunEvent.sequence > max(0, int(after_sequence)),
            )
            .order_by(DeepSpaceRunEvent.sequence.asc())
        )
        .scalars()
        .all()
    )


def latest_sequence(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_request_id: str,
) -> int:
    """Return the durable replay cursor for one authorized run stream."""
    db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )
    value = db.execute(
        select(func.max(DeepSpaceRunEvent.sequence)).where(
            DeepSpaceRunEvent.tenant_id == tenant_id,
            DeepSpaceRunEvent.user_id == user_id,
            DeepSpaceRunEvent.conversation_id == conversation_id,
            DeepSpaceRunEvent.client_request_id == str(client_request_id).strip(),
        )
    ).scalar_one()
    return int(value or 0)


def decode_live_event(payload: str) -> tuple[int, str] | None:
    try:
        data: dict[str, Any] = json.loads(payload)
        return int(data["sequence"]), str(data["frame"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


def frames_after(
    events: Iterable[DeepSpaceRunEvent], *, after_sequence: int = 0
) -> list[tuple[int, str]]:
    return [(event.sequence, event.frame) for event in events if event.sequence > after_sequence]


_TIMELINE_EVENT_NAMES = {
    "agent_plan",
    "thinking",
    "model_message",
    "lane_thinking",
    "lane_agent_thinking",
    "agent_thinking",
    "tool_start",
    "tool_result",
    "tool_error",
    "research_status",
    "ask_user_question",
    "permission_request",
    "permission_granted",
    "permission_denied",
    "agent_testing",
    "agent_verifying",
    "agent_self_correct",
}
_THINKING_EVENT_NAMES = {
    "thinking",
    "lane_thinking",
    "lane_agent_thinking",
    "agent_thinking",
}


def timeline_events(
    events: Iterable[DeepSpaceRunEvent],
) -> list[dict[str, Any]]:
    """Return a compact, ordered replay of meaningful UI activity events.

    The full SSE log remains the reconnect source of truth. History only needs
    semantic timeline events: adjacent thinking frames are coalesced, while
    tool and approval boundaries are retained so the original order survives
    a page reload without duplicating every token delta in the history API.
    """

    result: list[dict[str, Any]] = []
    for event in events:
        event_name = event.event_name or event_name_from_frame(event.frame)
        if event_name not in _TIMELINE_EVENT_NAMES:
            continue
        data_line = next(
            (
                line.partition(":")[2].strip()
                for line in event.frame.splitlines()
                if line.startswith("data:")
            ),
            "{}",
        )
        try:
            payload = json.loads(data_line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        if event_name in _THINKING_EVENT_NAMES and isinstance(payload.get("text"), str):
            # Event rows are durable and can be replayed long after the live
            # stream. Apply the same privacy boundary during replay so a
            # reload never exposes a raw provider reasoning fragment.
            payload["text"] = redact_reasoning_text(payload["text"])
        payload.setdefault("timestamp", event.created_at.isoformat())
        if event_name in _THINKING_EVENT_NAMES and result:
            previous = result[-1]
            if previous.get("event") in _THINKING_EVENT_NAMES:
                previous_data = dict(previous.get("data") or {})
                previous_data["text"] = (
                    f"{previous_data.get('text') or ''}{payload.get('text') or ''}"
                )
                previous["data"] = previous_data
                previous["sequence_end"] = event.sequence
                continue
        result.append(
            {
                "event": event_name,
                "data": payload,
                "sequence": event.sequence,
                "sequence_end": event.sequence,
            }
        )
    return result
