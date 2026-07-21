from __future__ import annotations

from app.documents.models.collection_notification import CollectionNotification
from app.documents.repositories.collection_notifications import (
    CollectionNotificationsRepository,
)


def test_collection_notifications_repository_is_idempotent_for_duplicate_keys(
    db_session,
    seed_user,
) -> None:
    seeded = seed_user(
        "tenant-notif-idem",
        "notif-idem@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    notification = CollectionNotification(
        recipient_user_id=seeded.user_id,
        actor_user_id=None,
        collection_id=None,
        collection_name="AverQel Proactive",
        event_type="agent_intervention",
        idempotency_key="notif-key-1",
        message="A proactive intervention is ready.",
    )

    repo = CollectionNotificationsRepository(db_session)
    first = repo.create(notification)
    second = repo.create(
        CollectionNotification(
            recipient_user_id=seeded.user_id,
            actor_user_id=None,
            collection_id=None,
            collection_name="AverQel Proactive",
            event_type="agent_intervention",
            idempotency_key="notif-key-1",
            message="A proactive intervention is ready.",
        )
    )

    db_session.commit()

    assert first.id == second.id
    assert repo.get_by_idempotency_key(idempotency_key="notif-key-1") is not None
    assert len(repo.list_for_user(user_id=seeded.user_id, limit=10)) == 1
