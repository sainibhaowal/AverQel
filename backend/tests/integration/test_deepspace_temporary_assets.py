from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.deepspace.api import library as library_api
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.deepspace.services.temporary_assets import cleanup_expired_temporary_assets
from app.platform.database.session import set_db_tenant_context
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.services.storage_service import StoredObject


def _headers(seeded) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"editor"},
        settings=get_settings(),
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}


def test_temporary_gallery_asset_is_private_and_can_be_retained(
    client: TestClient, seed_user, monkeypatch
) -> None:
    seeded = seed_user("Temp Asset Tenant", "temp-assets@example.com", "password123", ("editor",))
    from app.platform.database.session import get_session_factory

    db = get_session_factory()()
    try:
        set_db_tenant_context(db, seeded.tenant_id)
        conversation = DeepSpaceChatRepository(db).create_conversation(
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            title="Gallery asset chat",
            kind="deepspace",
        )
        db.commit()
    finally:
        db.close()

    image_bytes = b"\x89PNG\r\n\x1a\nvalid-png-header"

    class FakeResponse:
        headers = {"content-type": "image/png"}
        status_code = 200
        url = "https://images.example.test/research.png"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def aiter_bytes(self, chunk_size: int):
            yield image_bytes

        @staticmethod
        def raise_for_status() -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(library_api.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(library_api, "_validate_remote_asset_url", lambda value: value)
    monkeypatch.setattr(library_api, "_ensure_storage_capacity", lambda **kwargs: None)
    monkeypatch.setattr(
        library_api.LibraryStorageService,
        "store",
        lambda self, **kwargs: StoredObject(
            bucket="test-library",
            object_key=f"test/{kwargs['file_id']}",
            etag="etag",
            size_bytes=len(kwargs["payload"]),
            content_type=kwargs["content_type"],
        ),
    )

    base = f"/api/v1/deepspace/library/{conversation.id}"
    imported = client.post(
        f"{base}/assets/import",
        headers=_headers(seeded),
        json={"url": "https://images.example.test/research.png", "retention": "temporary"},
    )
    assert imported.status_code == 200
    asset = imported.json()
    assert asset["source"] == "temporary_asset"
    assert asset["content_type"] == "image/png"
    assert asset["download_url"].endswith(f"/{asset['id']}/content")

    entries = client.get(f"{base}/entries", headers=_headers(seeded))
    assert entries.status_code == 200
    assert all(item["id"] != asset["id"] for item in entries.json()["files"])

    other_account = seed_user(
        "Separate Asset Tenant", "other-temp-assets@example.com", "password123", ("editor",)
    )
    private_read = client.get(
        f"{base}/files/{asset['id']}/content",
        headers=_headers(other_account),
    )
    assert private_read.status_code == 404

    retained = client.post(
        f"{base}/assets/{asset['id']}/retain",
        headers=_headers(seeded),
        json={},
    )
    assert retained.status_code == 200
    assert retained.json()["source"] == "remote_asset"
    visible = client.get(f"{base}/entries", headers=_headers(seeded))
    assert any(item["id"] == asset["id"] for item in visible.json()["files"])


def test_expired_temporary_assets_are_removed_and_object_deletion_is_queued(
    db_session: Session, seed_user
) -> None:
    seeded = seed_user(
        "Expired Asset Tenant", "expired-assets@example.com", "password123", ("editor",)
    )
    set_db_tenant_context(db_session, seeded.tenant_id)
    conversation = DeepSpaceChatRepository(db_session).create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Expired gallery asset chat",
        kind="deepspace",
    )
    now = datetime.now(UTC)
    expired_id = uuid.uuid4()
    active_id = uuid.uuid4()
    for file_id, name, expires_at in (
        (expired_id, "expired.png", now - timedelta(minutes=1)),
        (active_id, "active.png", now + timedelta(days=2)),
    ):
        db_session.add(
            DeepSpaceWorkspaceFile(
                id=file_id,
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                conversation_id=conversation.id,
                name=name,
                content_type="image/png",
                source="temporary_asset",
                content="",
                size_bytes=20,
                storage_bucket="test-library",
                storage_key=f"assets/{file_id}",
                checksum_sha256="a" * 64,
                is_binary=True,
                metadata_json={"expires_at": expires_at.isoformat(), "retention": "temporary"},
            )
        )
    db_session.commit()

    deleted = cleanup_expired_temporary_assets(
        db_session,
        tenant_id=seeded.tenant_id,
        now=now,
    )
    db_session.commit()

    assert deleted == 1
    remaining_ids = set(
        db_session.execute(
            select(DeepSpaceWorkspaceFile.id).where(
                DeepSpaceWorkspaceFile.tenant_id == seeded.tenant_id,
                DeepSpaceWorkspaceFile.source == "temporary_asset",
            )
        ).scalars()
    )
    assert active_id in remaining_ids
    assert expired_id not in remaining_ids
    jobs = (
        db_session.execute(
            select(StorageCleanupJob).where(
                StorageCleanupJob.tenant_id == seeded.tenant_id,
                StorageCleanupJob.object_key == f"assets/{expired_id}",
            )
        )
        .scalars()
        .all()
    )
    assert len(jobs) == 1
