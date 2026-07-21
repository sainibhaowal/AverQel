from __future__ import annotations

from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.collection import (
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
)
from app.documents.models.document import Document
from app.documents.repositories.collections import CollectionsRepository


def test_get_collection_document_counts(
    db_session,
    seed_user,
) -> None:
    seeded = seed_user(
        "tenant-coll-repo-test",
        "coll-repo@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )

    repo = CollectionsRepository(db_session)

    import secrets

    # 1. Create a collection
    collection = DocumentCollection(
        id=generate_uuid7_with_fallback(),
        tenant_id=seeded.tenant_id,
        name="Test Collection",
        connection_code="".join(
            secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(8)
        ),
        description="Testing doc counting",
    )
    repo.create(collection)

    # Add owner permission
    permission = CollectionPermission(
        collection_id=collection.id,
        user_id=seeded.user_id,
        role="owner",
    )
    db_session.add(permission)
    db_session.flush()

    # 2. Add some documents
    doc1 = Document(
        id=generate_uuid7_with_fallback(),
        tenant_id=seeded.tenant_id,
        uploaded_by_user_id=seeded.user_id,
        filename="doc1.txt",
        content_type="text/plain",
        size_bytes=10,
        sha256_hash="c" * 64,
        storage_bucket="averqel",
        storage_object_key=f"{seeded.tenant_id}/doc1.txt",
        status="indexed",
    )
    doc2 = Document(
        id=generate_uuid7_with_fallback(),
        tenant_id=seeded.tenant_id,
        uploaded_by_user_id=seeded.user_id,
        filename="doc2.txt",
        content_type="text/plain",
        size_bytes=15,
        sha256_hash="d" * 64,
        storage_bucket="averqel",
        storage_object_key=f"{seeded.tenant_id}/doc2.txt",
        status="indexed",
    )
    doc_deleted = Document(
        id=generate_uuid7_with_fallback(),
        tenant_id=seeded.tenant_id,
        uploaded_by_user_id=seeded.user_id,
        filename="deleted.txt",
        content_type="text/plain",
        size_bytes=20,
        sha256_hash="e" * 64,
        storage_bucket="averqel",
        storage_object_key=f"{seeded.tenant_id}/deleted.txt",
        status="indexed",
        is_deleted=True,
    )
    db_session.add_all([doc1, doc2, doc_deleted])
    db_session.flush()

    # Associate docs with collection
    cd1 = CollectionDocument(collection_id=collection.id, document_id=doc1.id)
    cd2 = CollectionDocument(collection_id=collection.id, document_id=doc2.id)
    cd_deleted = CollectionDocument(
        collection_id=collection.id, document_id=doc_deleted.id
    )
    db_session.add_all([cd1, cd2, cd_deleted])
    db_session.commit()

    # 3. Call get_collection_document_counts
    counts = repo.get_collection_document_counts(
        collection_ids=[collection.id],
        user_id=seeded.user_id,
    )

    # 4. Assertions (deleted document should be excluded, so count is 2)
    assert counts.get(collection.id) == 2
