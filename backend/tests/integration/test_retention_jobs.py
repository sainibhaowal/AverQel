from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.documents.models.data_deletion import DataDeletion
from app.system.models.idempotency_key import IdempotencyKey
from app.system.workers.tasks_maintenance import retention_cleanup
from tests.conftest import SeededUser

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def test_retention_cleanup_removes_old_transient_records(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-retention",
        "admin-retention@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    old_timestamp = datetime.now(tz=UTC) - timedelta(days=120)

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)

        session.add(
            IdempotencyKey(
                id=generate_uuid7_with_fallback(),
                tenant_id=seeded.tenant_id,
                idempotency_key="old-key",
                request_fingerprint="a" * 64,
                resource_type="document_upload",
                resource_id=generate_uuid7_with_fallback(),
                status_code=200,
                response_body={"ok": True},
                created_at=old_timestamp,
            )
        )
        session.add(
            DataDeletion(
                id=generate_uuid7_with_fallback(),
                tenant_id=seeded.tenant_id,
                requested_by_user_id=seeded.user_id,
                status="completed",
                scope="tenant_data",
                reason="old-record",
                result_counts={},
                requested_at=old_timestamp,
                completed_at=old_timestamp,
            )
        )
        session.commit()
    finally:
        session.execute(text("RESET ROLE"))
        session.close()

    report = retention_cleanup()
    assert report["transient_records_deleted"] >= 2

    verify = get_session_factory()()
    try:
        verify.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(verify, seeded.tenant_id)
        remaining_idempotency = verify.execute(
            select(func.count())
            .select_from(IdempotencyKey)
            .where(IdempotencyKey.tenant_id == seeded.tenant_id)
        ).scalar_one()
        remaining_deletions = verify.execute(
            select(func.count())
            .select_from(DataDeletion)
            .where(DataDeletion.tenant_id == seeded.tenant_id)
        ).scalar_one()
        assert remaining_idempotency == 0
        assert remaining_deletions == 0
    finally:
        verify.execute(text("RESET ROLE"))
        verify.close()
