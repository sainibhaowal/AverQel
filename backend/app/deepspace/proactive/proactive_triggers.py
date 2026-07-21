from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deepspace.models.agent_activity import AgentActivity


@dataclass(frozen=True, slots=True)
class ProactiveTrigger:
    name: str
    source: str
    version: str
    query: str
    cooldown: timedelta

    def with_cooldown(self, cooldown: timedelta) -> ProactiveTrigger:
        return ProactiveTrigger(
            name=self.name,
            source=self.source,
            version=self.version,
            query=self.query,
            cooldown=cooldown,
        )

    def idempotency_key(
        self, *, connector_id: str, external_id: str, tenant_id: object
    ) -> str:
        raw = "|".join(
            [
                str(tenant_id),
                connector_id,
                self.source,
                self.name,
                self.version,
                external_id,
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ProactiveTriggerRegistry:
    """Proactive trigger policy and idempotency checks."""

    GMAIL_URGENT = ProactiveTrigger(
        name="urgent_message",
        source="gmail",
        version="gmail-urgent-v1",
        query="is:unread (urgent OR recruiter OR 'action required')",
        cooldown=timedelta(days=14),
    )

    def __init__(self, db: Session):
        self.db = db

    def already_processed(
        self,
        *,
        trigger: ProactiveTrigger,
        tenant_id: object,
        connector_id: str,
        external_id: str,
    ) -> bool:
        idempotency_key = trigger.idempotency_key(
            tenant_id=tenant_id,
            connector_id=connector_id,
            external_id=external_id,
        )
        cutoff = datetime.now(UTC) - trigger.cooldown
        rows = self.db.execute(
            select(AgentActivity.metadata_json)
            .where(
                AgentActivity.tenant_id == tenant_id,
                AgentActivity.source == trigger.source,
                AgentActivity.activity_type.in_(("match", "draft", "notify")),
                AgentActivity.created_at >= cutoff,
            )
            .order_by(AgentActivity.created_at.desc())
            .limit(1000)
        ).scalars()
        for metadata in rows:
            if not isinstance(metadata, dict):
                continue
            if metadata.get("idempotency_key") == idempotency_key:
                return True
            if (
                str(metadata.get("connector_id") or "") == connector_id
                and str(metadata.get("message_id") or metadata.get("external_id") or "")
                == external_id
                and str(metadata.get("trigger_version") or "") == trigger.version
            ):
                return True
        return False

    def metadata(
        self,
        *,
        trigger: ProactiveTrigger,
        tenant_id: object,
        connector_id: str,
        external_id: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        return {
            **dict(extra or {}),
            "source": trigger.source,
            "trigger_name": trigger.name,
            "trigger_query": trigger.query,
            "trigger_version": trigger.version,
            "trigger_cooldown_seconds": int(trigger.cooldown.total_seconds()),
            "trigger_cooldown_until": (now + trigger.cooldown)
            .isoformat()
            .replace("+00:00", "Z"),
            "idempotency_key": trigger.idempotency_key(
                tenant_id=tenant_id,
                connector_id=connector_id,
                external_id=external_id,
            ),
            "connector_id": connector_id,
            "external_id": external_id,
        }
