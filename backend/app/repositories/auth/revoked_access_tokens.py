from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.models.auth.revoked_access_token import RevokedAccessToken
from app.repositories.system.base import BaseRepository

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class RevokedAccessTokensRepository(BaseRepository):
    def create(self, row: RevokedAccessToken) -> RevokedAccessToken:
        self.apply_tenant_scope(row.tenant_id)
        self.db.add(row)
        self.db.flush()
        return row

    def exists(
        self,
        *,
        tenant_id: uuid.UUID,
        token_id: str,
    ) -> bool:
        self.apply_tenant_scope(tenant_id)
        stmt = select(RevokedAccessToken.id).where(
            RevokedAccessToken.tenant_id == tenant_id,
            RevokedAccessToken.token_id == token_id,
            RevokedAccessToken.expires_at > datetime.now(tz=UTC),
        )
        return self.db.execute(stmt).scalar_one_or_none() is not None

    def purge_expired(self, *, tenant_id: uuid.UUID) -> int:
        self.apply_tenant_scope(tenant_id)
        stmt = delete(RevokedAccessToken).where(
            RevokedAccessToken.tenant_id == tenant_id,
            RevokedAccessToken.expires_at <= datetime.now(tz=UTC),
        )
        result = self.db.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0)
