from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from typing import cast

import boto3  # type: ignore[import-untyped]
from botocore.client import BaseClient  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import Settings

logger = logging.getLogger(__name__)

_FILENAME_SAFE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_FALLBACK_FILENAME = "file"


class StorageServiceError(Exception):
    def __init__(self, *, code: str, message: str, retryable: bool) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


@dataclass(slots=True)
class StoredObject:
    bucket: str
    object_key: str
    etag: str
    size_bytes: int
    content_type: str


def _safe_filename(filename: str) -> str:
    normalized = filename.strip().replace("\\", "/").split("/")[-1]
    normalized = _FALLBACK_FILENAME if not normalized else normalized
    normalized = _FILENAME_SAFE_PATTERN.sub("_", normalized)
    return normalized or _FALLBACK_FILENAME


class StorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: BaseClient | None = None
        self._bucket_verified = False

    def put_bytes(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> StoredObject:
        client = self._get_client()
        self._ensure_bucket(client)

        safe_filename = _safe_filename(filename)
        object_key = f"{tenant_id}/{document_id}/{safe_filename}"

        try:
            response = client.put_object(
                Bucket=self.settings.minio_bucket,
                Key=object_key,
                Body=payload,
                ContentType=content_type,
                Metadata={
                    "tenant_id": str(tenant_id),
                    "document_id": str(document_id),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
            )
        except (BotoCoreError, ClientError) as exc:
            logger.warning(
                "Object storage put failed.",
                exc_info=exc,
                extra={
                    "bucket": self.settings.minio_bucket,
                    "object_key": object_key,
                },
            )
            raise StorageServiceError(
                code="STORAGE_UNAVAILABLE",
                message="Unable to store document in object storage.",
                retryable=True,
            ) from exc

        etag = str(response.get("ETag", "")).strip('"')
        return StoredObject(
            bucket=self.settings.minio_bucket,
            object_key=object_key,
            etag=etag,
            size_bytes=len(payload),
            content_type=content_type,
        )

    def get_bytes(self, *, bucket: str, object_key: str) -> bytes:
        client = self._get_client()
        body = None
        try:
            response = client.get_object(Bucket=bucket, Key=object_key)
            body = response["Body"]
            data = body.read()
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"NoSuchKey", "NoSuchBucket", "NotFound"}:
                raise StorageServiceError(
                    code="STORAGE_OBJECT_NOT_FOUND",
                    message="Object storage payload is missing.",
                    retryable=False,
                ) from exc
            raise StorageServiceError(
                code="STORAGE_UNAVAILABLE",
                message="Unable to read document from object storage.",
                retryable=True,
            ) from exc
        except BotoCoreError as exc:
            raise StorageServiceError(
                code="STORAGE_UNAVAILABLE",
                message="Unable to read document from object storage.",
                retryable=True,
            ) from exc
        finally:
            if body is not None:
                try:
                    body.close()
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to close object storage response body.", exc_info=True)

        return cast(bytes, data)

    def get_stream(self, *, bucket: str, object_key: str):
        """Return a stream for the object."""
        client = self._get_client()
        try:
            response = client.get_object(Bucket=bucket, Key=object_key)
            return response["Body"]
        except (BotoCoreError, ClientError) as exc:
            logger.warning(
                "Object storage stream failed.",
                exc_info=exc,
                extra={"bucket": bucket, "object_key": object_key},
            )
            raise StorageServiceError(
                code="STORAGE_UNAVAILABLE",
                message="Unable to stream document from object storage.",
                retryable=True,
            ) from exc

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        client = self._get_client()
        try:
            client.delete_object(Bucket=bucket, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            logger.warning(
                "Object storage delete failed.",
                exc_info=exc,
                extra={"bucket": bucket, "object_key": object_key},
            )

    def copy_object(
        self,
        *,
        bucket: str,
        source_key: str,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        content_type: str,
    ) -> StoredObject:
        """Copy an object inside the private bucket without exposing it publicly."""
        client = self._get_client()
        self._ensure_bucket(client)
        safe_filename = _safe_filename(filename)
        object_key = f"{tenant_id}/{document_id}/{safe_filename}"
        try:
            client.copy_object(
                Bucket=bucket,
                Key=object_key,
                CopySource={"Bucket": bucket, "Key": source_key},
                ContentType=content_type,
                MetadataDirective="REPLACE",
                Metadata={"tenant_id": str(tenant_id), "document_id": str(document_id)},
            )
            head = client.head_object(Bucket=bucket, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageServiceError(
                code="STORAGE_UNAVAILABLE",
                message="Unable to copy the Library object.",
                retryable=True,
            ) from exc
        return StoredObject(
            bucket=bucket,
            object_key=object_key,
            etag=str(head.get("ETag", "")).strip('"'),
            size_bytes=int(head.get("ContentLength", 0)),
            content_type=content_type,
        )

    def _ensure_bucket(self, client: BaseClient) -> None:
        if self._bucket_verified:
            return

        try:
            client.head_bucket(Bucket=self.settings.minio_bucket)
            self._bucket_verified = True
            return
        except ClientError as exc:
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if status not in {403, 404}:
                raise StorageServiceError(
                    code="STORAGE_UNAVAILABLE",
                    message="Unable to verify object storage bucket.",
                    retryable=True,
                ) from exc

        try:
            client.create_bucket(Bucket=self.settings.minio_bucket)
            self._bucket_verified = True
        except ClientError as exc:
            raise StorageServiceError(
                code="STORAGE_UNAVAILABLE",
                message="Unable to create object storage bucket.",
                retryable=True,
            ) from exc

    def _get_client(self) -> BaseClient:
        if self._client is not None:
            return self._client

        endpoint = (self.settings.minio_endpoint or "").strip()
        if not endpoint:
            raise StorageServiceError(
                code="STORAGE_UNAVAILABLE",
                message="Object storage endpoint is not configured.",
                retryable=False,
            )

        if not endpoint.startswith(("http://", "https://")):
            scheme = "https" if self.settings.minio_secure else "http"
            endpoint = f"{scheme}://{endpoint}"

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=self.settings.minio_access_key,
            aws_secret_access_key=self.settings.minio_secret_key,
            use_ssl=self.settings.minio_secure,
            verify=(self.settings.minio_verify_ssl if self.settings.minio_secure else False),
        )
        return self._client
