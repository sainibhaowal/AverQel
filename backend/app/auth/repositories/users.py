from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.auth.models.user import User
from app.platform.database.session import set_db_tenant_context
from app.system.repositories.base import BaseRepository

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class UsersRepository(BaseRepository):
    def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        self.apply_tenant_scope(tenant_id)
        query = select(User).where(
            User.tenant_id == tenant_id,
            User.email == email,
        )
        return self.db.execute(query).scalar_one_or_none()

    def get_by_email_global(self, email: str) -> User | None:
        # Intentional bypass for authentication bootstrap when tenant is not yet resolved.
        # Caller/request lifecycle must ensure tenant context is safely managed after this call.
        set_db_tenant_context(self.db, "bypass")
        query = select(User).where(User.email == email)
        return self.db.execute(query).scalar_one_or_none()

    def get_by_id(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        self.apply_tenant_scope(tenant_id)
        query = select(User).where(
            User.tenant_id == tenant_id,
            User.id == user_id,
        )
        return self.db.execute(query).scalar_one_or_none()

    def list_by_tenant(self, tenant_id: uuid.UUID) -> list[User]:
        self.apply_tenant_scope(tenant_id)
        query = select(User).where(User.tenant_id == tenant_id).order_by(User.created_at.asc())
        return list(self.db.execute(query).scalars().all())

    def list_all(self) -> list[User]:
        set_db_tenant_context(self.db, "bypass")
        query = select(User).order_by(User.created_at.asc())
        return list(self.db.execute(query).scalars().all())

    def get_by_id_global(self, user_id: uuid.UUID) -> User | None:
        set_db_tenant_context(self.db, "bypass")
        query = select(User).where(User.id == user_id)
        return self.db.execute(query).scalar_one_or_none()

    def get_by_collection_code_global(self, collection_code: str) -> User | None:
        set_db_tenant_context(self.db, "bypass")
        query = select(User).where(User.collection_code == collection_code.upper())
        return self.db.execute(query).scalar_one_or_none()

    def count_by_tenant(self, tenant_id: uuid.UUID) -> int:
        self.apply_tenant_scope(tenant_id)
        query = select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        return int(self.db.execute(query).scalar_one() or 0)

    def register_failed_login(
        self,
        *,
        tenant_id: uuid.UUID,
        user: User,
        max_failed_attempts: int,
        lockout_minutes: int,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= max_failed_attempts:
            user.locked_until = datetime.now(tz=UTC) + timedelta(minutes=lockout_minutes)

    def register_successful_login(self, *, tenant_id: uuid.UUID, user: User) -> None:
        self.apply_tenant_scope(tenant_id)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(tz=UTC)

    def create(self, user: User) -> User:
        self.db.add(user)
        return user

    def delete(self, *, tenant_id: uuid.UUID, user: User) -> None:
        self.apply_tenant_scope(tenant_id)
        self.db.delete(user)
