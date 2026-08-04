from __future__ import annotations

import base64
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.system.services.storage_service import StorageService


class DeepSpaceMediaArtifactService:
    """Persist provider-produced media before exposing it to the browser."""

    _KIND_BY_PREFIX = {"image/": "image", "video/": "video", "audio/": "audio"}

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
        kind = self.kind_for_content_type(content_type)
        if kind is None:
            raise ValueError("Unsupported generated media type.")
        try:
            payload = base64.b64decode(data_base64, validate=True)
        except ValueError as exc:
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
            content_type=content_type.lower().split(";", 1)[0],
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
        }
