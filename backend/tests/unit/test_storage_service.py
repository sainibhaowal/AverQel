from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import Settings
from app.services.system.storage_service import StorageService, StorageServiceError


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        minio_endpoint="localhost:9000",
        minio_access_key="minio",
        minio_secret_key="minio",
        minio_secure=False,
        minio_bucket="bucket-a",
    )


def _client_error(code: str, status: int) -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation_name="op",
    )


def test_put_bytes_success_and_get_client_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeClient:
        def head_bucket(self, *, Bucket: str) -> None:  # noqa: N803
            assert Bucket == "bucket-a"

        def put_object(self, **kwargs: object) -> dict[str, object]:
            calls["put"] = kwargs
            return {"ETag": '"etag-1"'}

    def fake_client(service: str, **kwargs: object) -> FakeClient:
        calls["service"] = service
        calls["kwargs"] = kwargs
        return FakeClient()

    monkeypatch.setattr("app.services.system.storage_service.boto3.client", fake_client)
    service = StorageService(cast(Settings, _settings()))
    tenant_id = uuid.uuid4()
    document_id = uuid.uuid4()
    result = service.put_bytes(
        tenant_id=tenant_id,
        document_id=document_id,
        filename="doc.txt",
        content_type="text/plain",
        payload=b"hello",
    )
    assert result.etag == "etag-1"
    assert result.bucket == "bucket-a"
    assert calls["service"] == "s3"
    assert (
        cast(dict[str, Any], calls["kwargs"])["endpoint_url"] == "http://localhost:9000"
    )
    assert str(tenant_id) in result.object_key
    assert str(document_id) in result.object_key


def test_put_bytes_maps_storage_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def head_bucket(self, *, Bucket: str) -> None:  # noqa: N803
            assert Bucket

        def put_object(self, **kwargs: object) -> dict[str, object]:
            raise _client_error("AccessDenied", 403)

    monkeypatch.setattr(
        "app.services.system.storage_service.boto3.client",
        lambda *_args, **_kwargs: FakeClient(),
    )
    service = StorageService(cast(Settings, _settings()))
    with pytest.raises(StorageServiceError) as exc_info:
        service.put_bytes(
            tenant_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            filename="doc.txt",
            content_type="text/plain",
            payload=b"x",
        )
    assert exc_info.value.code == "STORAGE_UNAVAILABLE"
    assert exc_info.value.retryable is True


def test_get_bytes_not_found_maps_non_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def get_object(self, **kwargs: object) -> dict[str, object]:
            raise _client_error("NoSuchKey", 404)

    monkeypatch.setattr(
        "app.services.system.storage_service.boto3.client",
        lambda *_args, **_kwargs: FakeClient(),
    )
    service = StorageService(cast(Settings, _settings()))
    with pytest.raises(StorageServiceError) as exc_info:
        service.get_bytes(bucket="bucket-a", object_key="k")
    assert exc_info.value.code == "STORAGE_OBJECT_NOT_FOUND"
    assert exc_info.value.retryable is False


def test_get_bytes_retryable_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class ClientRaisesClientError:
        def get_object(self, **kwargs: object) -> dict[str, object]:
            raise _client_error("InternalError", 500)

    monkeypatch.setattr(
        "app.services.system.storage_service.boto3.client",
        lambda *_args, **_kwargs: ClientRaisesClientError(),
    )
    service = StorageService(cast(Settings, _settings()))
    with pytest.raises(StorageServiceError) as exc_info:
        service.get_bytes(bucket="bucket-a", object_key="k")
    assert exc_info.value.code == "STORAGE_UNAVAILABLE"
    assert exc_info.value.retryable is True

    class ClientRaisesBotoCore:
        def get_object(self, **kwargs: object) -> dict[str, object]:
            raise BotoCoreError()

    monkeypatch.setattr(
        "app.services.system.storage_service.boto3.client",
        lambda *_args, **_kwargs: ClientRaisesBotoCore(),
    )
    service = StorageService(cast(Settings, _settings()))
    with pytest.raises(StorageServiceError):
        service.get_bytes(bucket="bucket-a", object_key="k")


def test_get_bytes_success_and_delete_object_no_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Body:
        @staticmethod
        def read() -> bytes:
            return b"payload"

    class FakeClient:
        def get_object(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["Bucket"] == "bucket-a"
            return {"Body": _Body()}

        def delete_object(self, **kwargs: object) -> None:
            raise _client_error("InternalError", 500)

    monkeypatch.setattr(
        "app.services.system.storage_service.boto3.client",
        lambda *_args, **_kwargs: FakeClient(),
    )
    service = StorageService(cast(Settings, _settings()))
    assert service.get_bytes(bucket="bucket-a", object_key="obj") == b"payload"
    service.delete_object(bucket="bucket-a", object_key="obj")


def test_ensure_bucket_create_and_fail_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class CreateBucketClient:
        def __init__(self) -> None:
            self.created = False

        def head_bucket(self, **kwargs: object) -> None:
            raise _client_error("NotFound", 404)

        def create_bucket(self, **kwargs: object) -> None:
            self.created = True

    client = CreateBucketClient()
    monkeypatch.setattr(
        "app.services.system.storage_service.boto3.client",
        lambda *_args, **_kwargs: client,
    )
    service = StorageService(cast(Settings, _settings()))
    service._ensure_bucket(service._get_client())
    assert client.created is True

    class HeadBucketHardFail:
        def head_bucket(self, **kwargs: object) -> None:
            raise _client_error("BadGateway", 502)

    monkeypatch.setattr(
        "app.services.system.storage_service.boto3.client",
        lambda *_args, **_kwargs: HeadBucketHardFail(),
    )
    with pytest.raises(StorageServiceError):
        StorageService(cast(Settings, _settings()))._ensure_bucket(
            StorageService(cast(Settings, _settings()))._get_client()
        )

    class CreateBucketFail:
        def head_bucket(self, **kwargs: object) -> None:
            raise _client_error("NotFound", 404)

        def create_bucket(self, **kwargs: object) -> None:
            raise _client_error("InternalError", 500)

    monkeypatch.setattr(
        "app.services.system.storage_service.boto3.client",
        lambda *_args, **_kwargs: CreateBucketFail(),
    )
    with pytest.raises(StorageServiceError):
        StorageService(cast(Settings, _settings()))._ensure_bucket(
            StorageService(cast(Settings, _settings()))._get_client()
        )
