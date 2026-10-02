from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deepspace.models.conversation_context_summary import DeepSpaceConversationContextSummary
from app.system.services.storage_quota import StorageQuotaService


class DeepSpaceContextSummaryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> DeepSpaceConversationContextSummary | None:
        return self.db.execute(
            select(DeepSpaceConversationContextSummary).where(
                DeepSpaceConversationContextSummary.tenant_id == tenant_id,
                DeepSpaceConversationContextSummary.user_id == user_id,
                DeepSpaceConversationContextSummary.conversation_id == conversation_id,
            )
        ).scalar_one_or_none()

    def upsert(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        source_message_count: int,
        summary_text: str,
        summary_json: dict[str, Any],
    ) -> DeepSpaceConversationContextSummary:
        row = self.get(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)
        new_bytes = StorageQuotaService.estimate_bytes(summary_text, summary_json)
        if row is None:
            StorageQuotaService(self.db).ensure_capacity(
                tenant_id=tenant_id,
                user_id=user_id,
                additional_bytes=new_bytes,
            )
            row = DeepSpaceConversationContextSummary(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                source_message_count=source_message_count,
                summary_text=summary_text,
                summary_json=summary_json,
            )
            self.db.add(row)
        else:
            StorageQuotaService(self.db).ensure_capacity(
                tenant_id=tenant_id,
                user_id=user_id,
                additional_bytes=new_bytes,
                replacing_bytes=StorageQuotaService.estimate_bytes(
                    row.summary_text, row.summary_json
                ),
            )
            row.source_message_count = source_message_count
            row.summary_text = summary_text
            row.summary_json = summary_json
        self.db.flush()
        return row
