from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.context import get_trace_id
from app.core.ids import generate_uuid7_with_fallback
from app.system.models.audit_log import AuditLog
from app.system.repositories.audit_logs import AuditLogsRepository

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017

SENSITIVE_DETAIL_KEY_TOKENS = frozenset(
    {
        "api_key",
        "answer",
        "authorization",
        "chat",
        "content",
        "content_html",
        "document_text",
        "html_content",
        "message_content",
        "normalized_query",
        "oauth",
        "password",
        "prompt",
        "query_text",
        "refresh_token",
        "secret",
        "session_token",
        "storage_bucket",
        "storage_object_key",
        "token",
    }
)


def redact_audit_details(details: Mapping[str, object] | None) -> dict[str, str]:
    if not details:
        return {}
    redacted: dict[str, str] = {}
    for key, value in details.items():
        normalized_key = str(key)
        lowered = normalized_key.lower()
        if any(token in lowered for token in SENSITIVE_DETAIL_KEY_TOKENS):
            redacted[normalized_key] = "[redacted]"
            continue
        redacted[normalized_key] = str(value)
    return redacted


@dataclass(slots=True)
class AuditPage:
    items: list[AuditLog]
    next_cursor: str | None
    has_more: bool


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditLogsRepository(db)

    def write_event(
        self,
        *,
        tenant_id: uuid.UUID,
        action: str,
        resource_type: str,
        actor_user_id: uuid.UUID | None,
        resource_id: str | None = None,
        status: str = "success",
        ip_address: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> AuditLog:
        trace_id = get_trace_id() or f"trc_{generate_uuid7_with_fallback()}"
        event = AuditLog(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            ip_address=ip_address,
            trace_id=trace_id,
            details=redact_audit_details(details),
        )
        return self.repo.create(event=event)

    def list_events(
        self,
        *,
        tenant_id: uuid.UUID,
        limit: int,
        cursor: str | None,
        action: str | None,
    ) -> AuditPage:
        safe_limit = max(1, min(limit, 200))

        cursor_created_at: datetime | None = None
        cursor_id: uuid.UUID | None = None
        if cursor:
            try:
                parts = cursor.split("|", maxsplit=1)
                if len(parts) == 2:
                    cursor_created_at = datetime.fromisoformat(parts[0])
                    cursor_id = uuid.UUID(parts[1])
            except (ValueError, TypeError):
                cursor_created_at = None
                cursor_id = None

        rows = self.repo.list_page(
            tenant_id=tenant_id,
            limit=safe_limit + 1,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
            action=action,
        )
        has_more = len(rows) > safe_limit
        page_rows = rows[:safe_limit]
        next_cursor: str | None = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = f"{last.created_at.isoformat()}|{last.id}"
        return AuditPage(items=page_rows, next_cursor=next_cursor, has_more=has_more)

    def purge_old_events(self, *, tenant_id: uuid.UUID, retention_days: int) -> int:
        safe_retention_days = max(0, retention_days)
        cutoff = datetime.now(tz=UTC) - timedelta(days=safe_retention_days)
        return self.repo.delete_older_than(tenant_id=tenant_id, cutoff=cutoff)
