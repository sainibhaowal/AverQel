from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.system.models.usage_record import UsageRecord
from app.system.services.metrics_service import observe_db_query


class BillingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_usage(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        model_name: str,
        query_id: uuid.UUID | None = None,
    ) -> UsageRecord:
        safe_input_tokens = max(0, input_tokens)
        safe_output_tokens = max(0, output_tokens)

        record = UsageRecord(
            tenant_id=tenant_id,
            user_id=user_id,
            query_id=query_id,
            operation=operation,
            input_tokens=safe_input_tokens,
            output_tokens=safe_output_tokens,
            total_tokens=safe_input_tokens + safe_output_tokens,
            model_name=model_name,
        )
        with observe_db_query("billing.record_usage"):
            self.db.add(record)
            self.db.flush()
        return record

    def get_tenant_usage(self, *, tenant_id: uuid.UUID) -> int:
        query = select(func.sum(UsageRecord.total_tokens)).where(
            UsageRecord.tenant_id == tenant_id
        )
        with observe_db_query("billing.get_tenant_usage"):
            return self.db.execute(query).scalar() or 0

    def check_quota(self, *, tenant_id: uuid.UUID, limit: int = 500000) -> bool:
        safe_limit = max(0, limit)
        usage = self.get_tenant_usage(tenant_id=tenant_id)
        return usage < safe_limit
