from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from app.analytics.schemas.analytics import (
    AnalyticsDashboardResponse,
    ConfidenceDistribution,
    QueryVolumePoint,
)
from app.query.models.query import Query
from app.system.services.metrics_service import observe_db_query

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017
MINIMUM_ANALYTICS_CONTRIBUTORS = 5
ANALYTICS_WINDOW = timedelta(days=30)


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_dashboard_metrics(self, tenant_id: uuid.UUID) -> AnalyticsDashboardResponse:
        cutoff = datetime.now(UTC) - ANALYTICS_WINDOW
        tenant_window = (Query.tenant_id == tenant_id, Query.created_at >= cutoff)

        with observe_db_query("analytics.active_contributors"):
            contributors = int(
                self.db.execute(
                    select(func.count(func.distinct(Query.user_id))).where(*tenant_window)
                ).scalar_one()
                or 0
            )

        if contributors < MINIMUM_ANALYTICS_CONTRIBUTORS:
            return AnalyticsDashboardResponse(
                suppressed=True,
                total_queries=None,
                avg_confidence=None,
                volume_over_time=[],
                confidence_distribution=None,
            )

        with observe_db_query("analytics.total_queries_30d"):
            total_queries = int(
                self.db.execute(
                    select(func.count()).select_from(Query).where(*tenant_window)
                ).scalar_one()
                or 0
            )

        with observe_db_query("analytics.avg_confidence_30d"):
            avg_confidence = float(
                self.db.execute(
                    select(func.avg(Query.confidence)).where(*tenant_window)
                ).scalar_one()
                or 0.0
            )

        day_expr = cast(Query.created_at, Date)
        day_contributors = func.count(func.distinct(Query.user_id))
        with observe_db_query("analytics.volume_over_time_30d"):
            volume_rows = self.db.execute(
                select(
                    day_expr.label("day"),
                    func.count().label("count"),
                )
                .where(*tenant_window)
                .group_by(day_expr)
                .having(day_contributors >= MINIMUM_ANALYTICS_CONTRIBUTORS)
                .order_by(day_expr)
            ).all()

        with observe_db_query("analytics.confidence_distribution_30d"):
            confidence_row = self.db.execute(
                select(
                    func.sum(case((Query.confidence >= 0.8, 1), else_=0)).label("high"),
                    func.sum(
                        case(
                            ((Query.confidence >= 0.5) & (Query.confidence < 0.8), 1),
                            else_=0,
                        )
                    ).label("medium"),
                    func.sum(case((Query.confidence < 0.5, 1), else_=0)).label("low"),
                ).where(*tenant_window)
            ).one()

        return AnalyticsDashboardResponse(
            suppressed=False,
            total_queries=total_queries,
            avg_confidence=round(avg_confidence, 2),
            volume_over_time=[
                QueryVolumePoint(
                    date=str(row._mapping["day"]),
                    count=int(row._mapping["count"]),
                )
                for row in volume_rows
            ],
            confidence_distribution=ConfidenceDistribution(
                high=int(confidence_row.high or 0),
                medium=int(confidence_row.medium or 0),
                low=int(confidence_row.low or 0),
            ),
        )
