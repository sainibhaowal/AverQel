from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.auth.security import hash_refresh_token
from app.auth.models.refresh_token import RefreshToken
from app.system.repositories.base import BaseRepository

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class RefreshTokensRepository(BaseRepository):
    def create(self, token: RefreshToken) -> None:
        self.apply_tenant_scope(token.tenant_id)
        self.db.add(token)

    def get_by_hash(self, tenant_id: uuid.UUID, token_hash: str) -> RefreshToken | None:
        self.apply_tenant_scope(tenant_id)
        query = select(RefreshToken).where(
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.token_hash == token_hash,
        )
        return self.db.execute(query).scalar_one_or_none()

    def revoke_token(
        self,
        *,
        tenant_id: uuid.UUID,
        token: RefreshToken,
        reason: str,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        now = datetime.now(tz=UTC)
        token.revoked_at = token.revoked_at or now
        token.revocation_reason = reason

    def mark_rotated(self, *, tenant_id: uuid.UUID, token: RefreshToken) -> None:
        self.apply_tenant_scope(tenant_id)
        now = datetime.now(tz=UTC)
        token.rotated_at = now
        token.revoked_at = now
        token.revocation_reason = "rotated"

    def revoke_family(
        self,
        *,
        tenant_id: uuid.UUID,
        token_family_id: uuid.UUID,
        reason: str,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        now = datetime.now(tz=UTC)
        statement = (
            update(RefreshToken)
            .where(
                RefreshToken.tenant_id == tenant_id,
                RefreshToken.token_family_id == token_family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(
                revoked_at=now,
                revocation_reason=reason,
            )
        )
        self.db.execute(statement)

    def revoke_all_for_user(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        now = datetime.now(tz=UTC)
        statement = (
            update(RefreshToken)
            .where(
                RefreshToken.tenant_id == tenant_id,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(
                revoked_at=now,
                revocation_reason=reason,
            )
        )
        self.db.execute(statement)

    def revoke_by_raw_token(
        self,
        *,
        tenant_id: uuid.UUID,
        raw_refresh_token: str,
        hash_secret: str,
    ) -> None:
        token_hash = hash_refresh_token(raw_refresh_token, hash_secret)
        token = self.get_by_hash(tenant_id, token_hash)
        if token is None:
            return
        self.revoke_token(
            tenant_id=tenant_id,
            token=token,
            reason="self_deleted",
        )
