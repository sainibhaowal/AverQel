from __future__ import annotations

import base64
import binascii
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.system.services.storage_service import StorageService


class DeepSpaceMediaArtifactService:
    """Persist provider-produced media before exposing it to the browser."""

    _KIND_BY_PREFIX = {"image/": "image", "video/": "video", "audio/": "audio"}
    _KIND_BY_TYPE = {
        "text/markdown": "document",
        "text/plain": "document",
        "text/html": "document",
        "text/csv": "table",
        "application/json": "data",
        "image/svg+xml": "diagram",
        "application/pdf": "document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "table",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "document",
    }

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.storage = StorageService(settings)

    @classmethod
    def kind_for_content_type(cls, content_type: str) -> str | None:
        normalized = content_type.lower().split(";", 1)[0].strip()
        return next(
            (kind for prefix, kind in cls._KIND_BY_PREFIX.items() if normalized.startswith(prefix)),
            None,
        )

    @classmethod
    def kind_for_artifact(cls, content_type: str, requested_kind: str | None = None) -> str:
        normalized = content_type.lower().split(";", 1)[0].strip()
        if requested_kind and requested_kind in {
            "image",
            "video",
            "audio",
            "document",
            "table",
            "chart",
            "diagram",
            "data",
            "code",
        }:
            return requested_kind
        return cls._KIND_BY_TYPE.get(normalized) or cls.kind_for_content_type(normalized) or "file"

    def persist_base64(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        content_type: str,
        data_base64: str,
        provider_type: str | None,
        model_name: str | None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.persist_content_base64(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            content_type=content_type,
            data_base64=data_base64,
            provider_type=provider_type,
            model_name=model_name,
            title=title,
            metadata=metadata,
        )

    def persist_content_base64(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID | None,
        content_type: str,
        data_base64: str,
        provider_type: str | None,
        model_name: str | None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        requested_kind: str | None = None,
    ) -> dict[str, Any]:
        normalized_type = content_type.lower().split(";", 1)[0].strip()
        if not (
            self.kind_for_content_type(normalized_type)
            or normalized_type in self._KIND_BY_TYPE
            or normalized_type.startswith("text/")
        ):
            raise ValueError("Unsupported generated artifact content type.")
        kind = self.kind_for_artifact(normalized_type, requested_kind)
        try:
            payload = base64.b64decode(data_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Generated media payload was invalid.") from exc
        if not payload:
            raise ValueError("Generated media payload was empty.")
        artifact = DeepSpaceMediaArtifact(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            kind=kind,
            status="ready",
            title=(title or f"Generated {kind}")[:255],
            content_type=normalized_type,
            storage_bucket="pending",
            storage_key="pending",
            provider_type=provider_type,
            model_name=model_name,
            metadata_json=metadata or {},
        )
        stored = self.storage.put_bytes(
            tenant_id=tenant_id,
            document_id=artifact.id,
            filename=f"artifact.{artifact.content_type.split('/')[-1] or kind}",
            content_type=artifact.content_type,
            payload=payload,
        )
        artifact.storage_bucket = stored.bucket
        artifact.storage_key = stored.object_key
        artifact.size_bytes = stored.size_bytes
        self.db.add(artifact)
        self.db.commit()
        return {
            "id": str(artifact.id),
            "kind": artifact.kind,
            "status": artifact.status,
            "title": artifact.title,
            "content_type": artifact.content_type,
            "size_bytes": artifact.size_bytes,
            "url": f"/api/v1/deepspace/artifacts/{artifact.id}/content",
            "metadata": artifact.metadata_json,
        }
