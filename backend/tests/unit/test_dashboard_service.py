from __future__ import annotations

import secrets

from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.collection import (
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
)
from app.documents.models.document import Document
from app.analytics.services.dashboard_service import DashboardService


def test_dashboard_service_get_overview(
    db_session,
    seed_user,
) -> None:
    seeded = seed_user(
        "tenant-dash-service-test",
        "dash-service@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )

    # 1. Setup Collection
    from app.documents.repositories.collections import CollectionsRepository

    repo = CollectionsRepository(db_session)
    collection = DocumentCollection(
        id=generate_uuid7_with_fallback(),
        tenant_id=seeded.tenant_id,
        name="Service Test Collection",
        connection_code="".join(
            secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(8)
        ),
        description="Testing service doc counting",
    )
    repo.create(collection)

    permission = CollectionPermission(
        collection_id=collection.id,
        user_id=seeded.user_id,
        role="owner",
    )
    db_session.add(permission)
    db_session.flush()

    # 2. Add Documents
    doc1 = Document(
        id=generate_uuid7_with_fallback(),
        tenant_id=seeded.tenant_id,
        uploaded_by_user_id=seeded.user_id,
        filename="service-doc1.txt",
        content_type="text/plain",
        size_bytes=10,
        sha256_hash="f" * 64,
        storage_bucket="averqel",
        storage_object_key=f"{seeded.tenant_id}/service-doc1.txt",
        status="indexed",
    )
    doc_deleted = Document(
        id=generate_uuid7_with_fallback(),
        tenant_id=seeded.tenant_id,
        uploaded_by_user_id=seeded.user_id,
        filename="service-deleted.txt",
        content_type="text/plain",
        size_bytes=20,
        sha256_hash="9" * 64,
        storage_bucket="averqel",
        storage_object_key=f"{seeded.tenant_id}/service-deleted.txt",
        status="indexed",
        is_deleted=True,
    )
    db_session.add_all([doc1, doc_deleted])
    db_session.flush()

    cd1 = CollectionDocument(collection_id=collection.id, document_id=doc1.id)
    cd_deleted = CollectionDocument(
        collection_id=collection.id, document_id=doc_deleted.id
    )
    db_session.add_all([cd1, cd_deleted])
    db_session.commit()

    # 3. Call DashboardService.get_overview
    service = DashboardService(db_session)
    overview = service.get_overview(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
    )

    # 4. Verify collection count and document count inside collections
    assert len(overview.collections) == 1
    assert overview.collections[0].collection_id == collection.id
    assert overview.collections[0].document_count == 1
