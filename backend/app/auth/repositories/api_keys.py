from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.auth.models.api_key import ApiKey
from app.system.repositories.base import BaseRepository
from app.system.services.metrics_service import observe_db_query

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class ApiKeysRepository(BaseRepository):
    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def create(self, api_key: ApiKey) -> ApiKey:
        self.apply_tenant_scope(api_key.tenant_id)
        with observe_db_query("api_keys.create"):
            self.db.add(api_key)
            self.db.flush()
        return api_key

    def get_by_hash(self, *, key_hash: str) -> ApiKey | None:
        # Tenant is unknown at lookup time, so we intentionally do not apply tenant scope here.
        query = select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active.is_(True),
        )
        with observe_db_query("api_keys.get_by_hash"):
            return self.db.execute(query).scalar_one_or_none()

    def update_last_used(self, *, key_id: uuid.UUID) -> None:
        stmt = update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=datetime.now(tz=UTC))
        with observe_db_query("api_keys.update_last_used"):
            self.db.execute(stmt)

    def list_by_tenant(self, *, tenant_id: uuid.UUID) -> list[ApiKey]:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc())
        )
        with observe_db_query("api_keys.list_by_tenant"):
            return list(self.db.execute(query).scalars().all())
