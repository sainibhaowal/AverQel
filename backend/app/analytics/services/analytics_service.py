from __future__ import annotations

import uuid

from sqlalchemy import Date, case, func, select
from sqlalchemy import cast as sa_cast
from sqlalchemy.orm import Session

from app.analytics.schemas.analytics import (
    AnalyticsDashboardResponse,
    ConfidenceDistribution,
    QueryVolumePoint,
)
from app.query.models.query import Query
from app.system.services.metrics_service import (
    API_REQUEST_LATENCY_SECONDS,
    observe_db_query,
)


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _compute_api_latency_p95_ms() -> float | None:
        """Compute p95 API latency in milliseconds from the in-process Prometheus histogram."""
        bucket_counts: dict[float, float] = {}
        total_count = 0.0

        for metric_family in API_REQUEST_LATENCY_SECONDS.collect():
            for sample in metric_family.samples:
                if sample.name.endswith("_bucket"):
                    le_str = sample.labels.get("le", "")
                    if le_str == "+Inf":
                        continue
                    try:
                        le = float(le_str)
                        bucket_counts[le] = bucket_counts.get(le, 0.0) + sample.value
                    except ValueError:
                        continue
                elif sample.name.endswith("_count"):
                    total_count += sample.value

        if total_count == 0:
            return None

        target = 0.95 * total_count
        for le, cumulative in sorted(bucket_counts.items()):
            if cumulative >= target:
                return round(le * 1000, 1)

        return None

    def get_dashboard_metrics(self, tenant_id: uuid.UUID) -> AnalyticsDashboardResponse:
        with observe_db_query("analytics.total_queries"):
            total_q = (
                select(func.count())
                .select_from(Query)
                .where(Query.tenant_id == tenant_id)
            )
            total_queries = self.db.execute(total_q).scalar() or 0

        with observe_db_query("analytics.avg_confidence"):
            avg_c = select(func.avg(Query.confidence)).where(
                Query.tenant_id == tenant_id
            )
            avg_confidence = self.db.execute(avg_c).scalar() or 0.0

        day_expr = sa_cast(Query.created_at, Date)

        with observe_db_query("analytics.volume_over_time"):
            vol_q = (
                select(day_expr.label("day"), func.count().label("count"))
                .where(Query.tenant_id == tenant_id)
                .group_by(day_expr)
                .order_by(day_expr)
            )
            vol_results = self.db.execute(vol_q).all()

        with observe_db_query("analytics.confidence_distribution"):
            conf_dist_q = select(
                func.sum(case((Query.confidence >= 0.8, 1), else_=0)).label("high"),
                func.sum(
                    case(
                        ((Query.confidence >= 0.5) & (Query.confidence < 0.8), 1),
                        else_=0,
                    )
                ).label("medium"),
                func.sum(case((Query.confidence < 0.5, 1), else_=0)).label("low"),
            ).where(Query.tenant_id == tenant_id)
            conf_row = self.db.execute(conf_dist_q).one()

        high = int(conf_row.high or 0)
        medium = int(conf_row.medium or 0)
        low = int(conf_row.low or 0)

        return AnalyticsDashboardResponse(
            total_queries=int(total_queries),
            avg_confidence=round(float(avg_confidence), 2),
            volume_over_time=[
                QueryVolumePoint(
                    date=str(result.day),
                    count=int(str(result.count)),
                )
                for result in vol_results
            ],
            confidence_distribution=ConfidenceDistribution(
                high=high,
                medium=medium,
                low=low,
            ),
            api_latency_p95_ms=self._compute_api_latency_p95_ms(),
        )
