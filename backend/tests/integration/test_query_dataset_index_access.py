from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.auth.models.user import User
from app.core.config import get_settings
from app.documents.models.document import Document
from app.documents.repositories.documents import DocumentsRepository
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.query.models.dataset_index import QueryDatasetIndex
from app.query.services.dataset_indexing import QueryDatasetIndexService, execute_dataset_plan
from app.query.workers.dataset_indexing import index_grounded_query_dataset
from app.system.services.storage_service import StorageService
from tests.conftest import SeededUser


def _seed_indexed_table(
    owner: SeededUser,
    sha256: str,
    *,
    index_status: str = "ready",
    index_updated_at: datetime | None = None,
) -> tuple[object, object]:
    document_id = uuid4()
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, owner.tenant_id)
        document = Document(
            id=document_id,
            tenant_id=owner.tenant_id,
            uploaded_by_user_id=owner.user_id,
            filename="private-sales.csv",
            content_type="text/csv",
            size_bytes=128,
            sha256_hash=sha256,
            storage_bucket="private-documents",
            storage_object_key=f"{owner.tenant_id}/{document_id}/private-sales.csv",
            security_scan_result="passed",
            status="indexed",
            processing_progress=100,
        )
        session.add(document)
        session.flush()
        session.add(
            QueryDatasetIndex(
                tenant_id=owner.tenant_id,
                document_id=document_id,
                source_sha256=sha256,
                status=index_status,
                stage=index_status,
                progress=100 if index_status == "ready" else 20,
                row_count=1,
                column_count=1,
                columns=[{"name": "amount", "type": "BIGINT"}],
                derivative_bucket="private-documents",
                derivative_object_key=f"{owner.tenant_id}/{document_id}/_grounded_query_dataset.parquet",
                updated_at=index_updated_at,
            )
        )
        session.commit()
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()
    return owner.tenant_id, document_id


def test_hash_reuse_and_table_indexes_do_not_cross_tenant(seed_user) -> None:
    first = seed_user(
        "Dataset Owner A", "dataset-owner-a@example.com", "StrongPass!1234", ("admin",)
    )
    second = seed_user(
        "Dataset Owner B", "dataset-owner-b@example.com", "StrongPass!1234", ("admin",)
    )
    sha256 = "a" * 64
    tenant_b, document_b = _seed_indexed_table(second, sha256)

    unauthorized_user_id = uuid4()
    seed_session = get_session_factory()()
    try:
        seed_session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(seed_session, tenant_b)
        seed_session.add(
            User(
                id=unauthorized_user_id,
                tenant_id=tenant_b,
                email="dataset-outsider@example.com",
                collection_code=f"GQ{uuid4().hex[:10].upper()}",
                password_hash="unused-in-this-test",
            )
        )
        seed_session.commit()
    finally:
        seed_session.rollback()
        seed_session.execute(text("RESET ROLE"))
        seed_session.close()

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, first.tenant_id)
        assert (
            DocumentsRepository(session).find_accessible_by_hash(
                tenant_id=first.tenant_id,
                user_id=first.user_id,
                sha256_hash=sha256,
            )
            is None
        )
        assert (
            QueryDatasetIndexService(db=session, settings=get_settings()).get_index(
                tenant_id=first.tenant_id,
                document_id=document_b,
            )
            is None
        )
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()

    other_session = get_session_factory()()
    try:
        other_session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(other_session, tenant_b)
        match = DocumentsRepository(other_session).find_accessible_by_hash(
            tenant_id=tenant_b,
            user_id=second.user_id,
            sha256_hash=sha256,
        )
        assert match is not None and match.id == document_b
        index = QueryDatasetIndexService(
            db=other_session,
            settings=get_settings(),
        ).get_index(tenant_id=tenant_b, document_id=document_b)
        assert index is not None and index.status == "ready"

        assert (
            DocumentsRepository(other_session).find_accessible_by_hash(
                tenant_id=tenant_b,
                user_id=unauthorized_user_id,
                sha256_hash=sha256,
            )
            is None
        )
    finally:
        other_session.rollback()
        other_session.execute(text("RESET ROLE"))
        other_session.close()


def test_abandoned_table_job_becomes_failed_and_can_be_retried(seed_user) -> None:
    owner = seed_user(
        "Dataset Retry Owner", "dataset-retry@example.com", "StrongPass!1234", ("admin",)
    )
    tenant_id, document_id = _seed_indexed_table(
        owner,
        "b" * 64,
        index_status="processing",
        index_updated_at=datetime.now(UTC) - timedelta(minutes=11),
    )
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, tenant_id)
        service = QueryDatasetIndexService(db=session, settings=get_settings())
        failed = service.fail_stale_processing(tenant_id=tenant_id, document_id=document_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error_code == "DATASET_INDEX_FAILED"

        document = session.get(Document, document_id)
        assert document is not None
        retried = service.request_index(tenant_id=tenant_id, document=document, retry=True)
        assert retried.status == "queued"
        assert retried.stage == "queued"
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_saved_documents_hub_table_runs_through_worker_and_exact_query(seed_user) -> None:
    owner = seed_user(
        "Dataset Worker Owner", "dataset-worker@example.com", "StrongPass!1234", ("admin",)
    )
    document_id = uuid4()
    payload = b"id,amount,region\n1,10,west\n2,25,east\n3,15,west\n"
    settings = get_settings()
    stored = StorageService(settings).put_bytes(
        tenant_id=owner.tenant_id,
        document_id=document_id,
        filename="sales.csv",
        content_type="text/csv",
        payload=payload,
    )
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, owner.tenant_id)
        document = Document(
            id=document_id,
            tenant_id=owner.tenant_id,
            uploaded_by_user_id=owner.user_id,
            filename="sales.csv",
            content_type="text/csv",
            size_bytes=len(payload),
            sha256_hash=hashlib.sha256(payload).hexdigest(),
            storage_bucket=stored.bucket,
            storage_object_key=stored.object_key,
            security_scan_result="passed",
            status="indexed",
            processing_progress=100,
        )
        session.add(document)
        session.commit()

        queued = QueryDatasetIndexService(db=session, settings=settings).request_index(
            tenant_id=owner.tenant_id,
            document=document,
            retry=False,
        )
        assert queued.status == "queued"

        task_result = index_grounded_query_dataset.apply(
            kwargs={"document_id": str(document_id), "tenant_id": str(owner.tenant_id)},
            throw=True,
        )
        assert task_result.result == "ready"

        session.expire_all()
        service = QueryDatasetIndexService(db=session, settings=settings)
        profile, derivative = service.derivative_profile(
            tenant_id=owner.tenant_id,
            document_id=document_id,
        )
        result = execute_dataset_plan(
            derivative_payload=derivative,
            profile=profile,
            plan={
                "action": "aggregate",
                "filters": [{"column": "region", "op": "eq", "value": "west"}],
                "aggregations": [
                    {"function": "count", "column": "*"},
                    {"function": "sum", "column": "amount"},
                ],
            },
        )
        assert result["matched_row_count"] == 2
        assert result["rows"] == [{"calculation_1": 2, "calculation_2": 25}]
        assert result["source_row_numbers"] == [2, 4]
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()
