from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session, selectinload

from app.core.ids import generate_uuid7_with_fallback
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.message import Message
from app.deepspace.models.message_version import MessageVersion


class DeepSpaceChatRepository:
    """Persistence operations for DeepSpace conversations only."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        title: str = "Untitled Note",
        content_html: str | None = None,
        kind: str = "deepspace",
    ) -> Conversation:
        conversation = Conversation(
            id=conversation_id or generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            kind=kind,
            content_html=content_html,
        )
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def get_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        kind: str = "deepspace",
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.id == conversation_id,
            Conversation.kind == kind,
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_conversations(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        kind: str = "deepspace",
    ) -> Sequence[Conversation]:
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.kind == kind,
            )
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.execute(stmt).scalars().all()

    def update_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None = None,
        content_html: str | None = None,
        kind: str = "deepspace",
    ) -> bool:
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if title is not None:
            values["title"] = title
        if content_html is not None:
            values["content_html"] = content_html
        result = self.db.execute(
            update(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.kind == kind,
            )
            .values(**values)
        )
        return bool(getattr(result, "rowcount", 0))

    def append_conversation_content(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        content_html: str,
        title: str | None = None,
        kind: str = "deepspace",
    ) -> Conversation | None:
        """Append content under a row lock without replacing existing notes."""
        conversation = self.db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.kind == kind,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if conversation is None:
            return None

        separator = '<hr data-averqel-document-separator="true" />'
        existing = (conversation.content_html or "").strip()
        conversation.content_html = (
            f"{existing}{separator}{content_html}" if existing else content_html
        )
        if title and conversation.title.strip().lower() in {"", "untitled note"}:
            conversation.title = title
        conversation.updated_at = datetime.now(UTC)
        self.db.flush()
        return conversation

    def delete_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: str = "deepspace",
    ) -> bool:
        result = self.db.execute(
            delete(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.kind == kind,
            )
        )
        return bool(getattr(result, "rowcount", 0))

    def bulk_delete_conversations(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        kind: str = "deepspace",
    ) -> int:
        if not conversation_ids:
            return 0
        result = self.db.execute(
            delete(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.kind == kind,
                Conversation.id.in_(conversation_ids),
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def add_message(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        metadata_json: dict[str, Any] | None = None,
        kind: str = "deepspace",
    ) -> Message:
        conversation = self.get_conversation(
            tenant_id=tenant_id, conversation_id=conversation_id, kind=kind
        )
        if conversation is None:
            raise ValueError("DeepSpace conversation not found")
        metadata = dict(metadata_json or {})
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_json=metadata,
        )
        self.db.add(message)
        self.db.flush()
        version = MessageVersion(
            message_id=message.id,
            version_index=1,
            content=content,
            metadata_json=metadata,
            source_type="initial",
        )
        self.db.add(version)
        self.db.flush()
        message.active_version_id = version.id
        self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=datetime.now(UTC))
        )
        self.db.flush()
        return message

    def get_messages(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: str = "deepspace",
    ) -> Sequence[Message]:
        stmt = (
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.id == conversation_id,
                Conversation.kind == kind,
            )
            .options(selectinload(Message.versions), selectinload(Message.active_version))
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return self.db.execute(stmt).scalars().unique().all()

    def get_message_by_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: str = "deepspace",
    ) -> Message | None:
        stmt = (
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.id == conversation_id,
                Conversation.kind == kind,
                Message.id == message_id,
            )
            .options(selectinload(Message.versions), selectinload(Message.active_version))
        )
        return self.db.execute(stmt).scalars().unique().one_or_none()

    def get_latest_turn_pair(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: str = "deepspace",
    ) -> tuple[Message | None, Message | None]:
        messages = list(
            self.get_messages(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                user_id=user_id,
                kind=kind,
            )
        )
        if len(messages) < 2:
            return None, None
        for index in range(len(messages) - 2, -1, -1):
            user_message, assistant_message = messages[index], messages[index + 1]
            if user_message.role == "user" and assistant_message.role == "assistant":
                return user_message, assistant_message
        return None, None

    def find_turn_by_request_id(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        user_id: uuid.UUID,
        request_id: str,
        kind: str = "deepspace",
    ) -> tuple[Message, Message] | None:
        """Return an existing turn for a client idempotency key."""
        normalized_request_id = str(request_id or "").strip()
        if not normalized_request_id:
            return None
        if conversation_id is None:
            stmt = (
                select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.user_id == user_id,
                    Conversation.kind == kind,
                    Message.role == "user",
                    Message.metadata_json["client_request_id"].astext == normalized_request_id,
                )
                .options(selectinload(Message.versions), selectinload(Message.active_version))
                .order_by(Message.created_at.desc(), Message.id.desc())
            )
            user_message = self.db.execute(stmt).scalars().first()
            if user_message is None:
                return None
            conversation_id = user_message.conversation_id
            messages = list(
                self.get_messages(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    kind=kind,
                )
            )
        else:
            messages = list(
                self.get_messages(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    kind=kind,
                )
            )
        for index, message in enumerate(messages[:-1]):
            if message.role != "user":
                continue
            metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
            if str(metadata.get("client_request_id") or "").strip() != normalized_request_id:
                continue
            assistant = messages[index + 1]
            if assistant.role == "assistant":
                return message, assistant
        return None

    def lock_request_id(self, request_id: str) -> None:
        """Serialize concurrent retries for one request key in PostgreSQL."""
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:request_id))"),
            {"request_id": str(request_id)},
        )

    def delete_message(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: str = "deepspace",
    ) -> bool:
        message = self.get_message_by_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message_id=message_id,
            user_id=user_id,
            kind=kind,
        )
        if message is None:
            return False
        self.db.delete(message)
        self.db.flush()
        return True

    def create_message_version(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        source_type: str = "user_edit",
        activate: bool = True,
        kind: str = "deepspace",
        metadata_json: dict[str, Any] | None = None,
    ) -> Message | None:
        message = self.get_message_by_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message_id=message_id,
            user_id=user_id,
            kind=kind,
        )
        if message is None:
            return None
        next_index = max((version.version_index for version in message.versions), default=0) + 1
        version = MessageVersion(
            message_id=message.id,
            version_index=next_index,
            content=content,
            metadata_json=dict(metadata_json or message.metadata_json or {}),
            source_type=source_type,
        )
        self.db.add(version)
        self.db.flush()
        if activate:
            message.active_version_id = version.id
            message.content = content
        self.db.flush()
        return message

    def activate_message_version(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        version_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: str = "deepspace",
    ) -> Message | None:
        message = self.get_message_by_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message_id=message_id,
            user_id=user_id,
            kind=kind,
        )
        if message is None:
            return None
        version = next((item for item in message.versions if item.id == version_id), None)
        if version is None:
            return None
        message.active_version_id = version.id
        message.content = version.content
        message.metadata_json = dict(version.metadata_json or {})
        self.db.flush()
        return message

    def complete_assistant_message(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        metadata_json: dict[str, Any],
    ) -> bool:
        message = self.get_message_by_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message_id=message_id,
            user_id=user_id,
        )
        if message is None or message.role != "assistant":
            return False
        message.content = content
        message.metadata_json = dict(metadata_json)
        if message.active_version is not None:
            message.active_version.content = content
            message.active_version.metadata_json = dict(metadata_json)
        self.db.flush()
        return True
