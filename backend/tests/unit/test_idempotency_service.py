from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.session import get_session_factory
from app.auth.models.tenant import Tenant
from app.system.repositories.idempotency_keys import IdempotencyKeysRepository
from app.system.services.idempotency_service import IdempotencyService


def _service(session: Session) -> IdempotencyService:
    return IdempotencyService(IdempotencyKeysRepository(session))


def test_idempotency_replay_and_conflict() -> None:
    session = get_session_factory()()
    try:
        service = _service(session)
        tenant_id = generate_uuid7_with_fallback()
        session.add(Tenant(id=tenant_id, name="tenant-idempotency-unit"))
        session.flush()
        key = "idem-unit-1"
        fingerprint_a = service.compute_fingerprint(
            payload_sha256="a" * 64,
            filename="doc.txt",
            content_type="text/plain",
            size_bytes=12,
        )
        service.persist_result(
            tenant_id=tenant_id,
            idempotency_key=key,
            request_fingerprint=fingerprint_a,
            resource_type="document_upload",
            resource_id=UUID("22222222-2222-7222-8222-222222222222"),
            status_code=200,
            response_body={
                "document_id": "22222222-2222-7222-8222-222222222222",
                "status": "queued",
                "ingestion_job_id": "33333333-3333-7333-8333-333333333333",
            },
        )
        session.commit()

        replay = service.check_replay_or_conflict(
            tenant_id=tenant_id,
            idempotency_key=key,
            request_fingerprint=fingerprint_a,
        )
        assert replay is not None
        assert replay.status_code == 200

        fingerprint_b = service.compute_fingerprint(
            payload_sha256="b" * 64,
            filename="doc.txt",
            content_type="text/plain",
            size_bytes=12,
        )
        with pytest.raises(ApiError) as exc_info:
            service.check_replay_or_conflict(
                tenant_id=tenant_id,
                idempotency_key=key,
                request_fingerprint=fingerprint_b,
            )
        assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"
    finally:
        session.rollback()
        session.close()


def test_idempotency_persists_hashed_fingerprint_shape() -> None:
    session = get_session_factory()()
    try:
        service = _service(session)
        fingerprint = service.compute_fingerprint(
            payload_sha256="c" * 64,
            filename="doc.md",
            content_type="text/markdown",
            size_bytes=100,
        )
        assert len(fingerprint) == 64
        int(fingerprint, 16)
    finally:
        session.close()
