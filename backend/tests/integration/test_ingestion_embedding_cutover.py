from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.session import get_session_factory, set_db_tenant_context
from app.models.documents.chunk_embedding import ChunkEmbedding
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.services.system.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser


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


def test_ingestion_cutover_uses_assigned_embedding_provider_and_persists_metadata(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    settings: Settings,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    monkeypatch.setenv("AKS_EMBEDDING_MODEL", "env-hash-fallback")

    in_memory_objects: dict[tuple[str, str], bytes] = {}

    def fake_put(
        self: StorageService,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> StoredObject:
        object_key = f"{tenant_id}/{document_id}/{filename}"
        in_memory_objects[(self.settings.minio_bucket, object_key)] = payload
        return StoredObject(
            bucket=self.settings.minio_bucket,
            object_key=object_key,
            etag="fake-etag",
            size_bytes=len(payload),
            content_type=content_type,
        )

    def fake_get(self: StorageService, *, bucket: str, object_key: str) -> bytes:
        return in_memory_objects[(bucket, object_key)]

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)

    seeded = seed_user(
        "Phase7 Ingestion Tenant",
        "phase7-ingestion@example.com",
        "StrongPass!1234",
        ("editor",),
    )

    session = get_session_factory()()
    try:
        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        provider = configs.create(
            ProviderConfig(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Assigned Embedding Provider",
                api_base_url="https://embedding-cutover.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=False,
                supports_embeddings=True,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model=None,
                default_embedding_model="embed-default",
                timeout_seconds=30,
                priority=1,
                metadata_json={},
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                feature_scope="embeddings",
                provider_config_id=provider.id,
                model_name="embed-assigned-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()
    finally:
        session.close()

    def _fake_embed_many(self, request):  # type: ignore[no-untyped-def]
        return type(
            "EmbedResponse", (), {"vectors": [[0.1] * settings.embedding_dimension]}
        )()

    monkeypatch.setattr(OpenAICompatibleProvider, "embed_many", _fake_embed_many)

    token = _login(
        client=client,
        tenant_id=str(seeded.tenant_id),
        email=seeded.email,
        password=seeded.password,
    )

    upload = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "phase7-ingestion-cutover",
        },
        files={
            "file": ("phase7.txt", b"provider metadata content\n" * 16, "text/plain")
        },
    )
    assert upload.status_code == 200

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        embeddings = (
            session.execute(
                select(ChunkEmbedding).where(
                    ChunkEmbedding.tenant_id == seeded.tenant_id
                )
            )
            .scalars()
            .all()
        )
        assert embeddings
        assert all(row.provider == "openai" for row in embeddings)
        assert all(row.model == "embed-assigned-model" for row in embeddings)
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
