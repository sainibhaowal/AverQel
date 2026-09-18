from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deepspace.models.request_metric import DeepSpaceRequestMetric


class DeepSpaceRequestMetricsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(self, row: DeepSpaceRequestMetric) -> None:
        self.db.add(row)
        self.db.flush()

    def summary(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, limit: int = 1000
    ) -> dict[str, object]:
        rows: Sequence[DeepSpaceRequestMetric] = (
            self.db.execute(
                select(DeepSpaceRequestMetric)
                .where(
                    DeepSpaceRequestMetric.tenant_id == tenant_id,
                    DeepSpaceRequestMetric.user_id == user_id,
                )
                .order_by(DeepSpaceRequestMetric.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        completed = [
            row
            for row in rows
            if row.outcome in {"ready", "cancelled", "awaiting_user", "awaiting_approval"}
        ]
        failed = [row for row in rows if row.outcome == "failed"]
        provider_rows: dict[str, list[DeepSpaceRequestMetric]] = {}
        for row in rows:
            provider_rows.setdefault(f"{row.provider_type}:{row.model_name}", []).append(row)
        return {
            "sample_size": len(rows),
            "failure_rate": (len(failed) / len(rows)) if rows else 0.0,
            "p50_latency_ms": _percentile([row.total_latency_ms for row in completed], 0.50),
            "p95_latency_ms": _percentile([row.total_latency_ms for row in completed], 0.95),
            "providers": [
                {
                    "provider": key,
                    "sample_size": len(values),
                    "failure_rate": sum(item.outcome == "failed" for item in values) / len(values),
                    "p50_latency_ms": _percentile([item.total_latency_ms for item in values], 0.50),
                    "p95_latency_ms": _percentile([item.total_latency_ms for item in values], 0.95),
                }
                for key, values in provider_rows.items()
            ],
        }


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentile))]
