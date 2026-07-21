from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.documents.models.collection_notification import CollectionNotification
from app.platform.database.session import set_db_tenant_context
from app.system.repositories.base import BaseRepository
from app.system.services.metrics_service import observe_db_query


class CollectionNotificationsRepository(BaseRepository):
    def _apply_bypass_scope(self) -> None:
        set_db_tenant_context(self.db, "bypass")

    def create(self, notification: CollectionNotification) -> CollectionNotification:
        if getattr(notification, "idempotency_key", None):
            existing = self.get_by_idempotency_key(
                idempotency_key=str(notification.idempotency_key)
            )
            if existing is not None:
                return existing
        with observe_db_query("collection_notifications.create"):
            try:
                with self.db.begin_nested():
                    self.db.add(notification)
                    self.db.flush()
            except IntegrityError:
                if getattr(notification, "idempotency_key", None):
                    existing = self.get_by_idempotency_key(
                        idempotency_key=str(notification.idempotency_key)
                    )
                    if existing is not None:
                        return existing
                raise
        return notification

    def get_by_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> CollectionNotification | None:
        self._apply_bypass_scope()
        query = select(CollectionNotification).where(
            CollectionNotification.idempotency_key == idempotency_key
        )
        with observe_db_query("collection_notifications.get_by_idempotency_key"):
            return self.db.execute(query).scalar_one_or_none()

    def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[CollectionNotification]:
        self._apply_bypass_scope()
        query = select(CollectionNotification).where(
            CollectionNotification.recipient_user_id == user_id
        )
        if collection_id is not None:
            query = query.where(CollectionNotification.collection_id == collection_id)
        query = query.order_by(
            CollectionNotification.created_at.desc(),
            CollectionNotification.id.desc(),
        ).limit(limit)
        with observe_db_query("collection_notifications.list_for_user"):
            return list(self.db.execute(query).scalars().all())

    def get_for_user(
        self,
        *,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> CollectionNotification | None:
        self._apply_bypass_scope()
        query = select(CollectionNotification).where(
            CollectionNotification.id == notification_id,
            CollectionNotification.recipient_user_id == user_id,
        )
        with observe_db_query("collection_notifications.get_for_user"):
            return self.db.execute(query).scalar_one_or_none()

    def mark_all_read_for_user(
        self,
        *,
        user_id: uuid.UUID,
        collection_id: uuid.UUID | None = None,
        read_at: datetime,
    ) -> None:
        self._apply_bypass_scope()
        items = self.list_for_user(
            user_id=user_id, collection_id=collection_id, limit=200
        )
        with observe_db_query("collection_notifications.mark_all_read_for_user"):
            for item in items:
                if item.read_at is None:
                    item.read_at = read_at

    def mark_read(
        self,
        *,
        notification: CollectionNotification,
        read_at: datetime,
    ) -> CollectionNotification:
        self._apply_bypass_scope()
        with observe_db_query("collection_notifications.mark_read"):
            notification.read_at = read_at
            self.db.flush()
        return notification

    def delete_for_user(
        self,
        *,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> bool:
        item = self.get_for_user(user_id=user_id, notification_id=notification_id)
        if item is None:
            return False
        self._apply_bypass_scope()
        with observe_db_query("collection_notifications.delete_for_user"):
            self.db.delete(item)
            self.db.flush()
        return True

    def delete_all_for_user(
        self,
        *,
        user_id: uuid.UUID,
    ) -> int:
        items = self.list_for_user(user_id=user_id, limit=500)
        self._apply_bypass_scope()
        with observe_db_query("collection_notifications.delete_all_for_user"):
            for item in items:
                self.db.delete(item)
            self.db.flush()
        return len(items)
