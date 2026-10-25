from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.errors import ApiError
from app.deepspace.api.library import LibraryUploadCreate, create_library_upload
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.deepspace.workers import library_uploads as upload_workers
from app.platform.database.session import (
    get_session_factory,
    set_db_tenant_context,
    set_db_user_context,
)
from app.system.services.storage_quota import StorageQuotaService


def test_composer_can_upload_same_named_files_as_distinct_library_records(
    db_session, seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "ComposerUploadTenant",
        "composer-uploads@example.com",
        "StrongPass!1234",
        ("user",),
    )
    set_db_tenant_context(db_session, seeded.tenant_id)
    set_db_user_context(db_session, seeded.user_id)
    conversation = DeepSpaceChatRepository(db_session).create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Composer uploads",
        kind="deepspace",
    )
    db_session.add(
        DeepSpaceWorkspaceFile(
            id=uuid.uuid4(),
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation.id,
            name="screenshot.png",
            content_type="image/png",
            content="",
            source="user",
            size_bytes=12,
            checksum_sha256="a" * 64,
            is_binary=True,
        )
    )
    db_session.commit()

    monkeypatch.setattr(StorageQuotaService, "reserve_capacity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(StorageQuotaService, "release_capacity", lambda *_args, **_kwargs: True)
    auth = SimpleNamespace(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        roles=frozenset({"user"}),
    )
    settings = SimpleNamespace(upload_max_bytes=25 * 1024 * 1024)

    def create_composer_upload():
        return asyncio.run(
            create_library_upload(
                conversation_id=conversation.id,
                payload=LibraryUploadCreate(
                    name="screenshot.png",
                    size_bytes=12,
                    content_type="image/png",
                    rename_on_conflict=True,
                ),
                auth=auth,
                db=db_session,
                settings=settings,
            )
        )

    first = create_composer_upload()
    second = create_composer_upload()

    assert first.name == "screenshot (2).png"
    assert second.name == "screenshot (3).png"
    assert first.id != second.id
    assert first.file_id is None
    assert second.file_id is None

    with pytest.raises(ApiError) as conflict:
        asyncio.run(
            create_library_upload(
                conversation_id=conversation.id,
                payload=LibraryUploadCreate(name="screenshot.png", size_bytes=12),
                auth=auth,
                db=db_session,
                settings=settings,
            )
        )
    assert conflict.value.status_code == 409


def test_composer_upload_finalization_rechecks_a_name_claimed_after_reservation(
    db_session, seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "ComposerUploadRaceTenant",
        "composer-upload-race@example.com",
        "StrongPass!1234",
        ("user",),
    )
    set_db_tenant_context(db_session, seeded.tenant_id)
    set_db_user_context(db_session, seeded.user_id)
    conversation = DeepSpaceChatRepository(db_session).create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Composer upload race",
        kind="deepspace",
    )
    monkeypatch.setattr(StorageQuotaService, "reserve_capacity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(StorageQuotaService, "release_capacity", lambda *_args, **_kwargs: True)
    auth = SimpleNamespace(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        roles=frozenset({"user"}),
    )
    settings = SimpleNamespace(upload_max_bytes=25 * 1024 * 1024)
    upload = asyncio.run(
        create_library_upload(
            conversation_id=conversation.id,
            payload=LibraryUploadCreate(
                name="screenshot.png",
                size_bytes=4,
                content_type="image/png",
                rename_on_conflict=True,
            ),
            auth=auth,
            db=db_session,
            settings=settings,
        )
    )
    db_session.add(
        DeepSpaceWorkspaceFile(
            id=uuid.uuid4(),
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation.id,
            name=upload.name,
            content_type="image/png",
            content="",
            source="user",
            size_bytes=4,
            checksum_sha256="b" * 64,
            is_binary=True,
        )
    )
    db_session.commit()

    class _Storage:
        def __init__(self, _settings: object) -> None:
            pass

        def get_upload_chunk(self, **_kwargs: object) -> bytes:
            return b"same"

        def delete_upload_chunks(self, **_kwargs: object) -> None:
            return None

        def delete_object(self, **_kwargs: object) -> None:
            return None

    expected_file_id = uuid.uuid4()
    finalized_names: list[str] = []

    def finalize(db, *, upload, **_kwargs):
        finalized_names.append(upload.filename)
        file = DeepSpaceWorkspaceFile(
            id=expected_file_id,
            tenant_id=upload.tenant_id,
            user_id=upload.user_id,
            conversation_id=upload.conversation_id,
            parent_folder_id=upload.parent_folder_id,
            name=upload.filename,
            content_type=upload.content_type,
            content="",
            source="user",
            size_bytes=4,
            checksum_sha256="c" * 64,
            is_binary=True,
            metadata_json={"extraction_status": {"state": "processing"}},
        )
        db.add(file)
        db.flush()
        return file

    monkeypatch.setattr(upload_workers, "get_settings", lambda: settings)
    monkeypatch.setattr(upload_workers, "get_session_factory", get_session_factory)
    monkeypatch.setattr(upload_workers, "StorageService", _Storage)
    monkeypatch.setattr(upload_workers, "finalize_upload", finalize)
    monkeypatch.setattr(
        upload_workers,
        "_enqueue_library_file_processing",
        lambda *_args, **_kwargs: None,
    )

    # Use a separate session for the Celery worker, as production does.
    result = upload_workers.finalize_library_upload.run(
        upload_id=upload.id,
        tenant_id=str(seeded.tenant_id),
    )

    db_session.expire_all()
    completed_upload = db_session.execute(
        select(DeepSpaceLibraryUpload).where(DeepSpaceLibraryUpload.id == uuid.UUID(upload.id))
    ).scalar_one()
    assert result == str(expected_file_id)
    assert finalized_names == ["screenshot (2).png"]
    assert completed_upload.filename == "screenshot (2).png"
    assert completed_upload.file_id == expected_file_id
    assert completed_upload.status == "completed"
