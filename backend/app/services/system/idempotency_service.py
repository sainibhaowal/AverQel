from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.models.system.idempotency_key import IdempotencyKey
from app.repositories.system.idempotency_keys import IdempotencyKeysRepository


@dataclass(slots=True)
class IdempotencyReplay:
    status_code: int
    response_body: dict[str, Any]


class IdempotencyService:
    def __init__(self, repository: IdempotencyKeysRepository) -> None:
        self.repository = repository

    def compute_fingerprint(
        self,
        *,
        payload_sha256: str,
        filename: str,
        content_type: str,
        size_bytes: int,
    ) -> str:
        normalized = {
            "payload_sha256": payload_sha256,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": max(0, size_bytes),
        }
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def check_replay_or_conflict(
        self,
        *,
        tenant_id: uuid.UUID,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> IdempotencyReplay | None:
        existing = self.repository.get(
            tenant_id=tenant_id, idempotency_key=idempotency_key
        )
        if existing is None:
            return None
        if existing.request_fingerprint != request_fingerprint:
            raise ApiError(
                code="IDEMPOTENCY_CONFLICT",
                message="Idempotency key was already used with a different request payload.",
                status_code=409,
            )
        return IdempotencyReplay(
            status_code=existing.status_code,
            response_body=existing.response_body,
        )

    def persist_result(
        self,
        *,
        tenant_id: uuid.UUID,
        idempotency_key: str,
        request_fingerprint: str,
        resource_type: str,
        resource_id: uuid.UUID,
        status_code: int,
        response_body: dict[str, Any],
    ) -> IdempotencyKey:
        row = IdempotencyKey(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            resource_type=resource_type,
            resource_id=resource_id,
            status_code=status_code,
            response_body=response_body,
        )
        return self.repository.create(row)
