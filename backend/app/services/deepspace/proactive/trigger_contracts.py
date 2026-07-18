from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class TriggerActivityRecord:
    activity_type: str
    description: str
    source: str
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TriggerTodoRecord:
    content: str
    active_form: str
    status: str
    priority: int
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TriggerNotificationRecord:
    recipient_user_id: Any
    message: str
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class TriggerExecutionContext:
    tenant_id: Any
    user_id: Any
    cycle_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecurringRuleRunResult:
    status: str
    next_run_at: datetime
    last_run_at: datetime
    activities: tuple[TriggerActivityRecord, ...] = ()
    notifications: tuple[TriggerNotificationRecord, ...] = ()
    todos: tuple[TriggerTodoRecord, ...] = ()
    mission_id: str | None = None
    final_output: str | None = None


@dataclass(frozen=True, slots=True)
class GmailTriggerCandidate:
    connector_id: str
    connector_name: str
    message_id: str
    subject: str
    trigger_name: str
    trigger_version: str
