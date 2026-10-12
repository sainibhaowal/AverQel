"""Background table indexing for explicitly attached Grounded Query files."""

from __future__ import annotations

import logging
import uuid

from celery import Task
from sqlalchemy import text

from app.core.config import get_settings
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app
from app.query.services.dataset_indexing import QueryDatasetIndexService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="queries.index_dataset",
    queue="grounded_query_datasets",
)  # type: ignore[misc]
def index_grounded_query_dataset(self: Task, *, document_id: str, tenant_id: str) -> str:
    """Index one already scanned and stored Documents Hub CSV or TSV file."""
    del self
    settings = get_settings()
    parsed_tenant_id = uuid.UUID(tenant_id)
    parsed_document_id = uuid.UUID(document_id)
    db = get_session_factory()()
    try:
        db.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(db, parsed_tenant_id)
        QueryDatasetIndexService(db=db, settings=settings).index_document(
            tenant_id=parsed_tenant_id,
            document_id=parsed_document_id,
        )
        row = QueryDatasetIndexService(db=db, settings=settings).get_index(
            tenant_id=parsed_tenant_id,
            document_id=parsed_document_id,
        )
        return row.status if row else "not-found"
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception(
            "Grounded Query table indexing task failed.",
            extra={"tenant_id": tenant_id, "document_id": document_id},
        )
        raise
    finally:
        try:
            db.rollback()
            db.execute(text("RESET ROLE"))
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        db.close()
