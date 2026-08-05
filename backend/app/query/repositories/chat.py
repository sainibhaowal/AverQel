from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.ids import generate_uuid7_with_fallback
from app.query.models.conversation import Conversation
from app.query.models.message import Message
from app.query.models.message_version import MessageVersion

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class ChatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        title: str = "New Conversation",
        kind: str = "query",
        content_html: str | None = None,
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
        kind: str = "query",
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
        kind: str = "query",
        limit: int = 50,
        offset: int = 0,
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
        kind: str,
        user_id: uuid.UUID | None = None,
        title: str | None = None,
        content_html: str | None = None,
    ) -> bool:
        values: dict[str, Any] = {"updated_at": datetime.now(tz=UTC)}
        if title is not None:
            values["title"] = title
        if content_html is not None:
            values["content_html"] = content_html

        stmt = (
            update(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
                Conversation.kind == kind,
            )
            .values(**values)
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        result = self.db.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    def update_conversation_title(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        title: str,
        user_id: uuid.UUID | None = None,
        kind: str = "query",
    ) -> bool:
        stmt = (
            update(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
                Conversation.kind == kind,
            )
            .values(title=title, updated_at=datetime.now(tz=UTC))
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        result = self.db.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    def delete_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        kind: str = "query",
    ) -> bool:
        stmt = delete(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.id == conversation_id,
            Conversation.kind == kind,
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        result = self.db.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    def bulk_delete_conversations(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_ids: list[uuid.UUID],
        user_id: uuid.UUID | None = None,
        kind: str = "query",
    ) -> int:
        if not conversation_ids:
            return 0
        stmt = delete(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.id.in_(conversation_ids),
            Conversation.kind == kind,
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        result = self.db.execute(stmt)
        return getattr(result, "rowcount", 0)

    def delete_message(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        kind: str = "query",
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
        self._touch_conversation(conversation_id, tenant_id)
        self.db.flush()
        return True

    def add_message(
        self,
        *,
        tenant_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID,
        kind: str = "query",
        role: str,
        content: str,
        metadata_json: dict[str, Any] | None = None,
        tokens: int | None = None,
    ) -> Message:
        conversation = self._resolve_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            kind=kind,
        )
        if conversation is None:
            raise ValueError("Conversation not found for tenant")

        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_json=metadata_json or {},
            tokens=tokens,
        )
        self.db.add(message)
        self.db.flush()
        version = self._create_message_version_row(
            message=message,
            content=content,
            metadata_json=metadata_json or {},
            source_type="initial",
        )
        message.active_version_id = version.id
        message.content = version.content
        message.metadata_json = dict(version.metadata_json)

        stmt = (
            update(Conversation)
            .where(
                Conversation.tenant_id == conversation.tenant_id,
                Conversation.id == conversation_id,
            )
            .values(updated_at=datetime.now(tz=UTC))
        )
        self.db.execute(stmt)

        self.db.flush()
        return message

    def create_message_version(
        self,
        *,
        tenant_id: uuid.UUID,
        message_id: uuid.UUID,
        content: str,
        metadata_json: dict[str, Any] | None = None,
        source_type: str,
        activate: bool = True,
    ) -> MessageVersion:
        message = self.get_message(
            tenant_id=tenant_id,
            message_id=message_id,
        )
        if message is None:
            raise ValueError("Message not found for tenant")

        version = self._create_message_version_row(
            message=message,
            content=content,
            metadata_json=metadata_json or {},
            source_type=source_type,
        )
        if activate:
            self._activate_version(message=message, version=version)
        self._touch_conversation(message.conversation_id, tenant_id)
        self.db.flush()
        return version

    def get_message(
        self,
        *,
        tenant_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> Message | None:
        stmt = (
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .options(
                selectinload(Message.versions),
                selectinload(Message.active_version),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Message.id == message_id,
            )
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_message_by_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        kind: str = "query",
    ) -> Message | None:
        stmt = (
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .options(
                selectinload(Message.versions),
                selectinload(Message.active_version),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.kind == kind,
                Message.conversation_id == conversation_id,
                Message.id == message_id,
            )
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_messages(
        self,
        *,
        tenant_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        kind: str = "query",
        limit: int = 100,
    ) -> Sequence[Message]:
        conversation = self._resolve_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            user_id=user_id,
            kind=kind,
        )
        if conversation is None:
            return []

        stmt = (
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .options(
                selectinload(Message.versions),
                selectinload(Message.active_version),
            )
            .where(
                Conversation.tenant_id == conversation.tenant_id,
                Conversation.kind == conversation.kind,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def _resolve_conversation(
        self,
        *,
        tenant_id: uuid.UUID | None,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        kind: str = "query",
    ) -> Conversation | None:
        if tenant_id is not None:
            return self.get_conversation(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                user_id=user_id,
                kind=kind,
            )

        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.kind == kind,
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_latest_message(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        kind: str = "query",
        role: str | None = None,
    ) -> Message | None:
        stmt = (
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .options(
                selectinload(Message.versions),
                selectinload(Message.active_version),
            )
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.kind == kind,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
        )
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        if role is not None:
            stmt = stmt.where(Message.role == role)
        return self.db.execute(stmt.limit(1)).scalar_one_or_none()

    def get_latest_turn_pair(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        kind: str = "query",
    ) -> tuple[Message | None, Message | None]:
        messages = list(
            self.get_messages(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                user_id=user_id,
                kind=kind,
                limit=200,
            )
        )
        last_assistant: Message | None = None
        for message in reversed(messages):
            if message.role == "assistant":
                last_assistant = message
                break
        if last_assistant is None:
            return None, None
        last_user: Message | None = None
        assistant_index = messages.index(last_assistant)
        for idx in range(assistant_index - 1, -1, -1):
            candidate = messages[idx]
            if candidate.role == "user":
                last_user = candidate
                break
        return last_user, last_assistant

    def activate_message_version(
        self,
        *,
        tenant_id: uuid.UUID,
        message_id: uuid.UUID,
        version_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> Message:
        message = self.get_message(
            tenant_id=tenant_id,
            message_id=message_id,
            user_id=user_id,
        )
        if message is None:
            raise ValueError("Message not found for tenant")
        version = next((item for item in message.versions if item.id == version_id), None)
        if version is None:
            raise ValueError("Message version not found for message")
        self._activate_version(message=message, version=version)
        self._touch_conversation(message.conversation_id, tenant_id)
        self.db.flush()
        return message

    def _create_message_version_row(
        self,
        *,
        message: Message,
        content: str,
        metadata_json: dict[str, Any],
        source_type: str,
    ) -> MessageVersion:
        current_count = (
            self.db.execute(
                select(func.max(MessageVersion.version_index)).where(
                    MessageVersion.message_id == message.id
                )
            ).scalar_one()
            or 0
        )
        version = MessageVersion(
            message=message,
            version_index=current_count + 1,
            content=content,
            metadata_json=metadata_json,
            source_type=source_type,
        )
        self.db.add(version)
        self.db.flush()
        return version

    def _activate_version(self, *, message: Message, version: MessageVersion) -> None:
        message.active_version_id = version.id
        message.active_version = version
        message.content = version.content
        message.metadata_json = dict(version.metadata_json)

    def fork_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        kind: str = "query",
    ) -> Conversation:
        original = self.get_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            user_id=user_id,
            kind=kind,
        )
        if not original:
            raise ValueError("Original conversation not found")

        # 1. Create new conversation
        forked = Conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            title=f"Fork of {original.title}",
            kind=kind,
            content_html=original.content_html,
        )
        self.db.add(forked)
        self.db.flush()

        # 2. Duplicate messages
        messages = self.get_messages(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            user_id=user_id,
            kind=kind,
        )
        for m in messages:
            new_msg = Message(
                conversation_id=forked.id,
                role=m.role,
                content=m.content,
                metadata_json=dict(m.metadata_json or {}),
                tokens=m.tokens,
            )
            self.db.add(new_msg)
            self.db.flush()

            # Re-create active version
            version = MessageVersion(
                message_id=new_msg.id,
                version_index=1,
                content=m.content,
                metadata_json=dict(m.metadata_json or {}),
                source_type="fork",
            )
            self.db.add(version)
            self.db.flush()
            new_msg.active_version_id = version.id

        self.db.commit()
        return forked

    def rewind_last_turn(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        kind: str = "query",
    ) -> bool:
        messages = list(
            self.get_messages(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                user_id=user_id,
                kind=kind,
                limit=200,
            )
        )
        if not messages:
            return False

        # Find the last assistant message
        to_delete = []
        found_assistant = False
        for m in reversed(messages):
            to_delete.append(m.id)
            if m.role == "assistant":
                found_assistant = True
                break

        if not found_assistant:
            return False

        stmt = delete(Message).where(Message.id.in_(to_delete))
        self.db.execute(stmt)
        self._touch_conversation(conversation_id, tenant_id)
        return True

    def _touch_conversation(self, conversation_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        stmt = (
            update(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
            )
            .values(updated_at=datetime.now(tz=UTC))
        )
        self.db.execute(stmt)
