from __future__ import annotations

import uuid

from sqlalchemy import select

from app.system.models.idempotency_key import IdempotencyKey
from app.system.repositories.base import BaseRepository


class IdempotencyKeysRepository(BaseRepository):
    def get(
        self, *, tenant_id: uuid.UUID, idempotency_key: str
    ) -> IdempotencyKey | None:
        self.apply_tenant_scope(tenant_id)
        query = select(IdempotencyKey).where(
            IdempotencyKey.tenant_id == tenant_id,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
        return self.db.execute(query).scalar_one_or_none()

    def create(self, key: IdempotencyKey) -> IdempotencyKey:
        self.apply_tenant_scope(key.tenant_id)
        self.db.add(key)
        self.db.flush()
        return key
