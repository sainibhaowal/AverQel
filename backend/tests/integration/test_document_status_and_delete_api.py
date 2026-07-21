from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.auth.dependencies import create_access_token
from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.auth.roles import canonicalize_role_name
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.ingestion.models.ingestion_job import IngestionJob
from app.platform.database.session import get_session_factory, set_db_tenant_context
from tests.conftest import SeededUser, _generate_test_collection_code


def _login(
    *,
    client: TestClient,
    tenant_id: str,
    email: str,
    password: str,
) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": tenant_id},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _auth_headers(seeded: SeededUser, *, roles: tuple[str, ...]) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles),
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def _add_user_to_existing_tenant(
    *, tenant_id: uuid.UUID, email: str, password: str, role_name: str
) -> SeededUser:
    session = get_session_factory()()
    try:
        set_db_tenant_context(session, tenant_id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            email=email,
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(user)
        session.flush()
        role = session.execute(
            select(Role).where(Role.name == canonicalize_role_name(role_name))
        ).scalar_one()
        session.add(
            UserRole(
                id=generate_uuid7_with_fallback(),
                tenant_id=tenant_id,
                user_id=user.id,
                role_id=role.id,
            )
        )
        session.commit()
        return SeededUser(
            tenant_id=tenant_id,
            user_id=user.id,
            collection_code=user.collection_code,
            email=email,
            password=password,
        )
    finally:
        session.rollback()
        session.close()


def _seed_document_with_embeddings(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    provider: str,
    model: str,
) -> uuid.UUID:
    settings = get_settings()
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, tenant_id)

        document_id = generate_uuid7_with_fallback()
        chunk_id = generate_uuid7_with_fallback()
        document = Document(
            id=document_id,
            tenant_id=tenant_id,
            uploaded_by_user_id=user_id,
            filename="status-source.pdf",
            content_type="application/pdf",
            size_bytes=2048,
            sha256_hash="a" * 64,
            storage_bucket="tenant-bucket",
            storage_object_key=f"{document_id}/status-source.pdf",
            status="embedding",
            processing_progress=70,
            extraction_method="native",
            extraction_coverage_score=0.92,
            extraction_ocr_used=False,
            extraction_vision_used=False,
            extraction_warnings=[],
        )
        chunk = DocumentChunk(
            id=chunk_id,
            tenant_id=tenant_id,
            document_id=document_id,
            chunk_index=0,
            content="Seeded content chunk for status inspection.",
            char_start=0,
            char_end=40,
            chunk_metadata={"mode": "text", "page_number": 1},
        )
        job = IngestionJob(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            document_id=document_id,
            status="embedding",
            attempt_count=1,
            max_attempts=3,
        )
        session.add_all([document, chunk, job])
        session.flush()
        embedding = ChunkEmbedding(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            document_id=document_id,
            chunk_id=chunk_id,
            embedding=[0.0] * settings.embedding_dimension,
            provider=provider,
            model=model,
        )
        session.add(embedding)
        session.commit()
        return document_id
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_document_status_returns_embedding_runtime_metadata(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-doc-status",
        "admin@tenant-status.example",
        "StrongPass!1234",
        ("admin",),
    )
    document_id = _seed_document_with_embeddings(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        provider="sentence-transformers",
        model="BAAI/bge-small-en-v1.5",
    )
    token = _login(
        client=client,
        tenant_id=str(seeded.tenant_id),
        email=seeded.email,
        password=seeded.password,
    )

    response = client.get(
        f"/api/v1/documents/{document_id}/status",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "embedding"
    assert payload["processing_progress"] == 70
    assert payload["active_stage"] == "embedding"
    assert payload["stage_progress"] > 0
    assert payload["embedding_provider"] == "sentence-transformers"
    assert payload["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert payload["embedded_chunk_count"] == 1


def test_editor_can_delete_document_and_purge_chunks(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-doc-delete",
        "editor@tenant-delete.example",
        "StrongPass!1234",
        ("editor",),
    )
    document_id = _seed_document_with_embeddings(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        provider="sentence-transformers",
        model="BAAI/bge-small-en-v1.5",
    )
    token = _login(
        client=client,
        tenant_id=str(seeded.tenant_id),
        email=seeded.email,
        password=seeded.password,
    )

    delete_response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert delete_response.status_code == 204

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)

        document = session.execute(
            select(Document).where(
                Document.tenant_id == seeded.tenant_id,
                Document.id == document_id,
            )
        ).scalar_one()
        assert document.is_deleted is True

        chunk_count = session.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(
                DocumentChunk.tenant_id == seeded.tenant_id,
                DocumentChunk.document_id == document_id,
            )
        ).scalar_one()
        embedding_count = session.execute(
            select(func.count())
            .select_from(ChunkEmbedding)
            .where(
                ChunkEmbedding.tenant_id == seeded.tenant_id,
                ChunkEmbedding.document_id == document_id,
            )
        ).scalar_one()
        assert chunk_count == 0
        assert embedding_count == 0
    finally:
        session.execute(text("RESET ROLE"))
        session.close()


def test_documents_are_private_between_users_in_same_tenant(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    owner = seed_user(
        "tenant-doc-private",
        "owner@tenant-doc-private.example",
        "StrongPass!1234",
        ("editor",),
    )
    other = _add_user_to_existing_tenant(
        tenant_id=owner.tenant_id,
        email="other@tenant-doc-private.example",
        password="StrongPass!1234",
        role_name="editor",
    )
    document_id = _seed_document_with_embeddings(
        tenant_id=owner.tenant_id,
        user_id=owner.user_id,
        provider="sentence-transformers",
        model="BAAI/bge-small-en-v1.5",
    )
    owner_headers = _auth_headers(owner, roles=("editor",))
    other_headers = _auth_headers(other, roles=("editor",))

    list_response = client.get("/api/v1/documents", headers=other_headers)
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []

    for path in (
        f"/api/v1/documents/{document_id}",
        f"/api/v1/documents/{document_id}/status",
        f"/api/v1/documents/{document_id}/chunks",
        f"/api/v1/documents/{document_id}/view",
        f"/api/v1/documents/{document_id}/versions",
    ):
        assert client.get(path, headers=other_headers).status_code == 404

    assert (
        client.delete(
            f"/api/v1/documents/{document_id}",
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/documents/{document_id}/reingest",
            headers=other_headers,
        ).status_code
        == 404
    )

    assert (
        client.get(
            f"/api/v1/documents/{document_id}/status",
            headers=owner_headers,
        ).status_code
        == 200
    )
