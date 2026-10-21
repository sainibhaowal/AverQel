from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models.user import User
from app.platform.database.session import set_db_tenant_context
from app.system.schemas.conversation import ConversationParticipantResponse


def _message_author_id(message: object) -> uuid.UUID | None:
    author_id = getattr(message, "author_user_id", None)
    return author_id if isinstance(author_id, uuid.UUID) else None


def conversation_participants(
    db: Session,
    messages: Sequence[object],
    *,
    primary_author_ids: Sequence[uuid.UUID] = (),
    include_display_names: bool = True,
    tenant_id_to_restore: uuid.UUID | str | None = None,
) -> tuple[list[ConversationParticipantResponse], dict[uuid.UUID, str]]:
    """Load visible participants' profile fields once for this thread.

    Profile rows can belong to another tenant, such as a platform support agent.
    The query is limited to authors of messages already authorized for this
    thread and reads only their avatar plus an optional display name.
    """
    message_author_ids = (_message_author_id(message) for message in messages)
    author_ids = list(
        dict.fromkeys(
            [*primary_author_ids, *(id_ for id_ in message_author_ids if id_ is not None)]
        )
    )
    if not author_ids:
        return [], {}

    profiles: dict[uuid.UUID, tuple[str | None, str | None]]
    set_db_tenant_context(db, "bypass")
    try:
        if include_display_names:
            profiles = {
                row.id: (row.display_name, row.avatar)
                for row in db.execute(
                    select(User.id, User.display_name, User.avatar).where(User.id.in_(author_ids))
                ).all()
            }
        else:
            profiles = {
                row.id: (None, row.avatar)
                for row in db.execute(
                    select(User.id, User.avatar).where(User.id.in_(author_ids))
                ).all()
            }
    finally:
        if tenant_id_to_restore is not None:
            set_db_tenant_context(db, tenant_id_to_restore)

    participants: list[ConversationParticipantResponse] = []
    author_refs: dict[uuid.UUID, str] = {}
    for author_id in author_ids:
        profile = profiles.get(author_id)
        if profile is None:
            continue
        participant_ref = f"participant-{len(participants) + 1}"
        author_refs[author_id] = participant_ref
        participants.append(
            ConversationParticipantResponse(
                ref=participant_ref,
                display_name=profile[0],
                avatar=profile[1],
            )
        )

    return participants, author_refs
