from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import get_session_factory
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.system.services.storage_service import StorageService, StoredObject
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


def test_embedding_provider_routing_prefers_assignment(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    settings: Settings,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    monkeypatch.setenv("AKS_EMBEDDING_MODEL", "env-fallback")

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
        "Routing Embed Tenant",
        "routing-embed@example.com",
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
                api_base_url="https://routing-embed.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=False,
                supports_embeddings=True,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model=None,
                default_embedding_model="embed-routing-model",
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
                model_name="embed-routing-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()
    finally:
        session.close()

    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "embed_many",
        lambda self, request: type(
            "EmbedResponse",
            (),
            {"vectors": [[0.2] * settings.embedding_dimension]},
        )(),
    )

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
            "Idempotency-Key": "phase10-embedding-routing",
        },
        files={
            "file": ("phase10.txt", b"embedding routing content\n" * 8, "text/plain")
        },
    )
    assert upload.status_code == 200
