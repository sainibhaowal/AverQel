from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.documents.document import Document
from app.models.system.audit_log import AuditLog
from app.repositories.documents.collections import CollectionsRepository
from app.repositories.documents.documents import DocumentsRepository
from app.repositories.ingestion.ingestion_jobs import IngestionJobsRepository
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.repositories.provider_health_checks import (
    ProviderHealthChecksRepository,
)
from app.schemas.analytics.dashboard import (
    DashboardActivityItemResponse,
    DashboardCollectionSummaryResponse,
    DashboardDocumentBreakdownResponse,
    DashboardOverviewResponse,
    DashboardProviderRuntimeResponse,
    DashboardRecentDocumentResponse,
    DashboardStatsResponse,
)
from app.providers.services.selection_service import ProviderSelectionService
from app.services.system.metrics_service import observe_db_query

_QUEUED_STATUSES = {"queued", "uploaded", "pending"}
_FAILED_STATUSES = {"failed", "dead_lettered"}
_INDEXED_STATUSES = {"indexed"}
_NOISY_DASHBOARD_ACTIONS = {
    "admin.audit_logs.read",
    "provider.selection.resolve",
    "documents.read",
    "dashboard.read",
}


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.documents = DocumentsRepository(db)
        self.collections = CollectionsRepository(db)
        self.jobs = IngestionJobsRepository(db)
        self.provider_configs = ProviderConfigsRepository(db)
        self.provider_health = ProviderHealthChecksRepository(db)
        self.provider_selection = ProviderSelectionService(
            db=db, settings=get_settings()
        )

    def get_stats(self, *, tenant_id: uuid.UUID) -> DashboardStatsResponse:
        total_docs = self.documents.count_by_tenant(tenant_id=tenant_id)
        total_queries = self._get_total_queries(tenant_id=tenant_id)
        storage_bytes = self.documents.sum_storage_by_tenant(tenant_id=tenant_id)
        active_jobs = self.jobs.count_active_by_tenant(tenant_id=tenant_id)

        return DashboardStatsResponse(
            total_documents=int(total_docs),
            total_queries=int(total_queries),
            storage_used_bytes=int(storage_bytes),
            active_jobs=int(active_jobs),
        )

    def get_overview(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DashboardOverviewResponse:
        stats = self.get_stats(tenant_id=tenant_id)
        recent_documents = self.documents.list_by_tenant(tenant_id=tenant_id, limit=5)
        collection_names = self.collections.get_document_collection_names(
            tenant_id=tenant_id,
            document_ids=[document.id for document in recent_documents],
        )

        return DashboardOverviewResponse(
            stats=stats,
            document_breakdown=self._get_document_breakdown(tenant_id=tenant_id),
            recent_documents=[
                DashboardRecentDocumentResponse(
                    document_id=document.id,
                    filename=document.filename,
                    status=document.status,
                    processing_progress=document.processing_progress,
                    size_bytes=document.size_bytes,
                    created_at=document.created_at,
                    extraction_method=document.extraction_method,
                    collection_names=collection_names.get(document.id, []),
                )
                for document in recent_documents
            ],
            provider_runtimes=self._get_provider_runtimes(tenant_id=tenant_id),
            collections=self._get_collection_summaries(
                tenant_id=tenant_id, user_id=user_id
            ),
            recent_activity=self._get_recent_activity(tenant_id=tenant_id),
        )

    def _get_total_queries(self, *, tenant_id: uuid.UUID) -> int:
        with observe_db_query("dashboard.total_queries"):
            query = select(func.count(AuditLog.id)).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action == "queries.create",
            )
            return int(self.db.execute(query).scalar() or 0)

    def _get_document_breakdown(
        self, *, tenant_id: uuid.UUID
    ) -> DashboardDocumentBreakdownResponse:
        with observe_db_query("dashboard.document_breakdown"):
            rows = self.db.execute(
                select(Document.status, func.count(Document.id))
                .where(
                    Document.tenant_id == tenant_id,
                    Document.is_deleted.is_(False),
                )
                .group_by(Document.status)
            ).all()

        indexed = processing = failed = queued = 0
        for status, count in rows:
            normalized = (status or "").lower()
            bucket_count = int(count or 0)
            if normalized in _INDEXED_STATUSES:
                indexed += bucket_count
            elif normalized in _FAILED_STATUSES:
                failed += bucket_count
            elif normalized in _QUEUED_STATUSES:
                queued += bucket_count
            else:
                processing += bucket_count

        with observe_db_query("dashboard.document_quarantined"):
            quarantined = int(
                self.db.execute(
                    select(func.count(Document.id)).where(
                        Document.tenant_id == tenant_id,
                        Document.is_deleted.is_(False),
                        Document.quarantined.is_(True),
                    )
                ).scalar()
                or 0
            )

        return DashboardDocumentBreakdownResponse(
            indexed=indexed,
            processing=processing,
            failed=failed,
            queued=queued,
            quarantined=quarantined,
        )

    def _get_provider_runtimes(
        self, *, tenant_id: uuid.UUID
    ) -> list[DashboardProviderRuntimeResponse]:
        runtimes: list[DashboardProviderRuntimeResponse] = []

        for scope in ("chat", "embeddings", "reranking", "web_search"):
            if scope == "chat":
                selection = self.provider_selection.resolve_chat(tenant_id=tenant_id)
            elif scope == "embeddings":
                selection = self.provider_selection.resolve_embeddings(
                    tenant_id=tenant_id
                )
            elif scope == "reranking":
                selection = self.provider_selection.resolve_reranking(
                    tenant_id=tenant_id
                )
            else:
                selection = self.provider_selection.resolve_web_search(
                    tenant_id=tenant_id
                )

            candidate = selection.candidates[0] if selection.candidates else None
            if candidate is None:
                runtimes.append(
                    DashboardProviderRuntimeResponse(
                        feature_scope=scope,
                        provider_display_name="No active provider",
                        provider_type="unconfigured",
                        model_name="Not configured",
                    )
                )
                continue

            config = None
            latest_health = None
            if candidate.provider_config_id:
                config = self.provider_configs.get_by_id(
                    tenant_id=tenant_id,
                    provider_config_id=candidate.provider_config_id,
                )
                latest_health = self.provider_health.get_latest_check(
                    tenant_id=tenant_id,
                    provider_config_id=candidate.provider_config_id,
                )
            runtimes.append(
                DashboardProviderRuntimeResponse(
                    feature_scope=scope,
                    provider_display_name=(
                        config.display_name if config else candidate.provider_type
                    ),
                    provider_type=candidate.provider_type,
                    model_name=candidate.model_name,
                    health_status=latest_health.status if latest_health else None,
                    latency_ms=latest_health.latency_ms if latest_health else None,
                )
            )

        return runtimes

    def _get_collection_summaries(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[DashboardCollectionSummaryResponse]:
        collections = self.collections.list_accessible_for_user_global(user_id=user_id)[
            :4
        ]
        collection_ids = [collection.id for collection in collections]
        doc_counts = self.collections.get_collection_document_counts(
            collection_ids=collection_ids,
            user_id=user_id,
        )
        summaries: list[DashboardCollectionSummaryResponse] = []
        for collection in collections:
            doc_count = doc_counts.get(collection.id, 0)
            summaries.append(
                DashboardCollectionSummaryResponse(
                    collection_id=collection.id,
                    name=collection.name,
                    document_count=doc_count,
                    updated_at=collection.updated_at,
                )
            )
        return summaries

    def _get_recent_activity(
        self, *, tenant_id: uuid.UUID
    ) -> list[DashboardActivityItemResponse]:
        with observe_db_query("dashboard.recent_activity"):
            rows = (
                self.db.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.tenant_id == tenant_id,
                        AuditLog.action.not_in(_NOISY_DASHBOARD_ACTIONS),
                    )
                    .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                    .limit(6)
                )
                .scalars()
                .all()
            )

        return [
            DashboardActivityItemResponse(
                id=row.id,
                action=row.action,
                status=row.status,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                created_at=row.created_at,
            )
            for row in rows
        ]
