from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.auth.repositories.users import UsersRepository
from app.auth.tenancy import require_request_tenant_id
from app.core.errors import ApiError
from app.documents.models.collection import (
    CollectionChatDelivery,
    CollectionChatMedia,
    DocumentCollection,
    UserPresence,
)
from app.documents.models.collection import (
    CollectionChatMessage as DBCollectionChatMessage,
)
from app.documents.models.collection_notification import CollectionNotification
from app.documents.models.collection_security import CollectionChatBlock, CollectionDevice
from app.documents.models.document import Document
from app.documents.repositories.collection_notifications import (
    CollectionNotificationsRepository,
)
from app.documents.repositories.collections import CollectionsRepository
from app.documents.schemas.collection import (
    CollectionDocumentAdd,
    CollectionDocumentRemove,
    CollectionInvitationRespond,
    CollectionInvitationResponse,
    CollectionNotificationResponse,
    CollectionPermissionAdd,
    CollectionPermissionRemove,
    CollectionPermissionResponse,
    DocumentCollectionCreate,
    DocumentCollectionResponse,
)
from app.documents.schemas.collection_chat import (
    CollectionChatMessage,
    CreateChatMessage,
)
from app.documents.schemas.collection_expiry import UpdateExpiryPayload
from app.documents.schemas.documents import DocumentMetadataResponse
from app.documents.services.collection_chat_encryption import (
    ChatEncryptionError,
    ChatEncryptionNotConfiguredError,
)
from app.documents.services.collection_chat_encryption import (
    open_for_read as open_chat_message,
)
from app.documents.services.collection_chat_encryption import (
    rotate_epoch as rotate_chat_epoch,
)
from app.documents.services.collection_chat_encryption import (
    seal_for_send as seal_chat_message,
)
from app.documents.services.collection_chat_encryption import (
    sender_label as chat_sender_label,
)
from app.documents.services.collection_chat_encryption import (
    shred_epochs as shred_chat_epochs,
)
from app.ingestion.services.extraction_quality import confidence_band
from app.platform.database.session import get_db
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.models.user_notification_preference import UserNotificationPreference
from app.system.services.cache_service import get_redis_client
from app.system.services.rate_limit_service import RateLimitService
from app.system.services.storage_lifecycle import StorageLifecycleService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/collections", tags=["collections"])


def _enforce_tenant_scope(request_tenant_id: uuid.UUID, auth: AuthContext) -> None:
    if request_tenant_id != auth.tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH",
            message="Requested tenant does not match authenticated tenant scope.",
            status_code=403,
        )


def _get_collection_or_404(
    *,
    repo: CollectionsRepository,
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID,
) -> DocumentCollection:
    coll = repo.get_by_id(tenant_id=tenant_id, collection_id=collection_id)
    if coll is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    return coll


def _enforce_collection_admin(
    *,
    repo: CollectionsRepository,
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    permission = repo.get_user_permission(
        tenant_id=tenant_id,
        collection_id=collection_id,
        user_id=user_id,
    )
    if permission is not None and getattr(permission, "role", None) == "owner":
        return
    raise ApiError(
        code="FORBIDDEN",
        message="Owner access for this collection is required.",
        status_code=403,
    )


def _enforce_collection_access(
    *,
    repo: CollectionsRepository,
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    permission = repo.get_user_permission(
        tenant_id=tenant_id,
        collection_id=collection_id,
        user_id=user_id,
    )
    if permission is None:
        raise ApiError(
            code="FORBIDDEN",
            message="You do not have access to this collection.",
            status_code=403,
        )
    return str(getattr(permission, "role", "shared"))


def _enforce_collection_access_global(
    *,
    repo: CollectionsRepository,
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    permission = repo.get_user_permission_global(
        collection_id=collection_id,
        user_id=user_id,
    )
    if permission is None:
        raise ApiError(
            code="FORBIDDEN",
            message="You do not have access to this collection.",
            status_code=403,
        )
    return str(getattr(permission, "role", "shared"))


def _collection_response(
    *,
    collection: DocumentCollection,
    requester_access_role: str,
    member_count: int,
    other_member_email: str | None = None,
    other_member_avatar: str | None = None,
) -> DocumentCollectionResponse:
    return DocumentCollectionResponse(
        id=collection.id,
        tenant_id=collection.tenant_id,
        name=collection.name,
        connection_code=collection.connection_code,
        other_member_email=other_member_email,
        other_member_avatar=other_member_avatar,
        description=collection.description,
        expiry_days=collection.expiry_days,
        requester_access_role=requester_access_role,
        member_count=member_count,
        security_epoch=collection.security_epoch,
        chat_encryption_enabled=bool(collection.chat_encryption_enabled),
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _normalize_member_role(raw_role: str | None) -> str:
    if raw_role == "owner":
        return "owner"
    if raw_role in {"shared", "member"}:
        return "member"
    return "pending"


def _is_connected_role(raw_role: str | None) -> bool:
    return _normalize_member_role(raw_role) in {"owner", "member"}


def _user_has_collection_block(
    db: Session, *, collection_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Return whether this sender has a moderation block with another member."""
    return (
        db.query(CollectionChatBlock.id)
        .filter(
            CollectionChatBlock.collection_id == collection_id,
            or_(
                CollectionChatBlock.blocker_user_id == user_id,
                CollectionChatBlock.blocked_user_id == user_id,
            ),
        )
        .first()
        is not None
    )


def _active_device_ids(db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[str]:
    rows = (
        db.query(CollectionDevice.device_id)
        .filter(
            CollectionDevice.tenant_id == tenant_id,
            CollectionDevice.user_id == user_id,
            CollectionDevice.revoked_at.is_(None),
        )
        .all()
    )
    return [str(row[0]) for row in rows] or ["legacy"]


def _validate_media_reference(
    *,
    collection: DocumentCollection,
    media_id: str | None,
    media_object_key: str | None,
) -> tuple[uuid.UUID | None, str | None]:
    """Validate a client-provided media reference without trusting its path."""
    if not media_id and not media_object_key:
        return None, None
    try:
        parsed_media_id = uuid.UUID(str(media_id)) if media_id else None
    except (TypeError, ValueError):
        raise ApiError(
            code="VALIDATION_ERROR",
            message="The media reference is invalid.",
            status_code=422,
        ) from None
    if parsed_media_id is None or not media_object_key:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="A media ID and storage reference must be supplied together.",
            status_code=422,
        )
    expected_prefix = f"{collection.tenant_id}/{parsed_media_id}/"
    normalized_key = str(media_object_key).replace("\\", "/")
    if not normalized_key.startswith(expected_prefix) or ".." in normalized_key.split("/"):
        raise ApiError(
            code="FORBIDDEN",
            message="The media object is not owned by this collection tenant.",
            status_code=403,
        )
    return parsed_media_id, normalized_key


def _require_complete_media_reference(
    *,
    is_media: bool,
    media_id: str | None,
    media_object_key: str | None,
    collection: DocumentCollection,
) -> tuple[uuid.UUID | None, str | None]:
    if is_media and (not media_id or not media_object_key):
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Media messages require an uploaded media ID and storage reference.",
            status_code=422,
        )
    return _validate_media_reference(
        collection=collection,
        media_id=media_id,
        media_object_key=media_object_key,
    )


def _validate_registered_media(
    *,
    db: Session,
    collection: DocumentCollection,
    user_id: uuid.UUID,
    media_id: uuid.UUID | None,
    object_key: str | None,
) -> CollectionChatMedia | None:
    """Validate a new registry record while keeping legacy uploads readable."""
    if media_id is None or object_key is None:
        return None
    media = db.query(CollectionChatMedia).filter(CollectionChatMedia.id == media_id).first()
    if media is None:
        return None
    if (
        media.collection_id != collection.id
        or media.tenant_id != collection.tenant_id
        or media.uploaded_by_user_id != user_id
        or media.object_key != object_key
        or media.status not in {"uploaded", "attached"}
    ):
        raise ApiError(
            code="FORBIDDEN",
            message="The media object is not available to this collection member.",
            status_code=403,
        )
    return media


def _queue_media_cleanup(
    *,
    db: Session,
    collection: DocumentCollection,
    media_id: uuid.UUID | None,
    object_key: str | None,
    owner_user_id: uuid.UUID,
    bucket: str,
) -> None:
    if media_id is not None:
        media = db.query(CollectionChatMedia).filter(CollectionChatMedia.id == media_id).first()
        if media is not None and media.collection_id == collection.id:
            media.status = "cleanup_queued"
            media.attached_message_id = None
    if object_key:
        db.add(
            StorageCleanupJob(
                tenant_id=collection.tenant_id,
                owner_user_id=owner_user_id,
                bucket=bucket,
                object_key=object_key,
            )
        )


def _resolve_other_member_email(
    *,
    repo: CollectionsRepository,
    users_repo: UsersRepository,
    collection_id: uuid.UUID,
    requester_user_id: uuid.UUID,
) -> str | None:
    permissions = repo.get_permissions_global(collection_id=collection_id)
    for permission in permissions:
        if permission.user_id == requester_user_id:
            continue
        if not _is_connected_role(getattr(permission, "role", None)):
            continue
        user = users_repo.get_by_id_global(permission.user_id)
        if user is not None:
            return user.email
    return None


def _resolve_other_member_avatar(
    *,
    repo: CollectionsRepository,
    users_repo: UsersRepository,
    collection_id: uuid.UUID,
    requester_user_id: uuid.UUID,
) -> str | None:
    permissions = repo.get_permissions_global(collection_id=collection_id)
    for permission in permissions:
        if permission.user_id == requester_user_id:
            continue
        if not _is_connected_role(getattr(permission, "role", None)):
            continue
        user = users_repo.get_by_id_global(permission.user_id)
        if user is not None:
            return user.avatar
    return None


def _generate_connection_code(repo: CollectionsRepository) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(10):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if repo.get_by_connection_code_global(connection_code=code) is None:
            return code
    raise ApiError(
        code="INTERNAL_SERVER_ERROR",
        message="Failed to generate a unique collection ID.",
        status_code=500,
    )


def _document_metadata_response(doc: Document) -> DocumentMetadataResponse:
    return DocumentMetadataResponse(
        document_id=doc.id,
        status=doc.status,
        processing_progress=doc.processing_progress,
        quarantined=doc.quarantined,
        information_yield=doc.information_yield,
        extraction_method=doc.extraction_method,
        extraction_coverage_score=doc.extraction_coverage_score,
        extraction_ocr_used=doc.extraction_ocr_used,
        extraction_vision_used=doc.extraction_vision_used,
        extraction_warnings=list(doc.extraction_warnings or []),
        extraction_confidence_band=confidence_band(doc.extraction_coverage_score),
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        sha256_hash=doc.sha256_hash,
        storage_bucket=doc.storage_bucket,
        storage_object_key=doc.storage_object_key,
        version=doc.version,
        parent_document_id=doc.parent_document_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _notification_response(
    item: CollectionNotification,
) -> CollectionNotificationResponse:
    return CollectionNotificationResponse(
        id=item.id,
        collection_id=item.collection_id,
        collection_name=item.collection_name,
        event_type=item.event_type,
        message=item.message,
        created_at=item.created_at,
        read_at=item.read_at,
    )


def _create_collection_notification(
    *,
    notifications_repo: CollectionNotificationsRepository,
    recipient_user_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    collection_id: uuid.UUID | None,
    collection_name: str,
    event_type: str,
    message: str,
    idempotency_key: str | None = None,
) -> None:
    notifications_repo.create(
        CollectionNotification(
            recipient_user_id=recipient_user_id,
            actor_user_id=actor_user_id,
            collection_id=collection_id,
            collection_name=collection_name,
            event_type=event_type,
            idempotency_key=idempotency_key
            or hashlib.sha256(
                "|".join(
                    [
                        str(recipient_user_id),
                        str(actor_user_id or ""),
                        str(collection_id or ""),
                        collection_name,
                        event_type,
                        message,
                    ]
                ).encode("utf-8")
            ).hexdigest(),
            message=message,
        )
    )


def _maybe_rotate_chat_epoch(db: Session, *, collection: DocumentCollection, reason: str) -> None:
    """Rotate the sealed-chat epoch when encryption is enabled.

    No-op for plaintext collections. When encryption is enabled but the
    deployment keyring is missing, rotation is skipped with a warning and
    sends keep failing closed until the keyring is restored.
    """
    if not bool(getattr(collection, "chat_encryption_enabled", False)):
        return
    try:
        rotate_chat_epoch(db, collection=collection, reason=reason)
    except ChatEncryptionNotConfiguredError:
        logger.warning(
            "Skipping sealed-chat rotation for collection %s: chat keyring is not configured",
            collection.id,
        )


def _record_collection_security_change(
    *,
    db: Session,
    repo: CollectionsRepository,
    notifications_repo: CollectionNotificationsRepository,
    collection: DocumentCollection,
    actor_user_id: uuid.UUID,
    excluded_user_ids: set[uuid.UUID] | None = None,
) -> None:
    """Advance the membership epoch and notify remaining members.

    This is an auditable security boundary: collections with sealed chat
    enabled also rotate to a fresh chat epoch, so removed members' epoch
    exposure ends at rotation. Plaintext collections only advance the
    membership counter.
    """
    collection.security_epoch = int(collection.security_epoch or 0) + 1
    _maybe_rotate_chat_epoch(db, collection=collection, reason="membership-change")
    excluded = excluded_user_ids or set()
    for permission in repo.get_permissions_global(collection_id=collection.id):
        if permission.user_id == actor_user_id or permission.user_id in excluded:
            continue
        if not _is_connected_role(getattr(permission, "role", None)):
            continue
        _create_collection_notification(
            notifications_repo=notifications_repo,
            recipient_user_id=permission.user_id,
            actor_user_id=actor_user_id,
            collection_id=collection.id,
            collection_name=collection.name,
            event_type="collection_security_changed",
            idempotency_key=f"collection-security:{collection.id}:{collection.security_epoch}:{permission.user_id}",
            message=(
                f'Security membership changed for "{collection.name}". '
                f"Verify trusted devices before sharing new messages (epoch {collection.security_epoch})."
            ),
        )


@router.post(
    "",
    response_model=DocumentCollectionResponse,
    status_code=201,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def create_collection(
    payload: DocumentCollectionCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DocumentCollectionResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    repo = CollectionsRepository(db)
    coll = DocumentCollection(
        tenant_id=auth.tenant_id,
        name=payload.name,
        connection_code=_generate_connection_code(repo),
        description=payload.description,
    )

    try:
        repo.create(coll)
        repo.add_permissions(
            tenant_id=auth.tenant_id,
            collection_id=coll.id,
            permissions=[{"user_id": auth.user_id, "role": "owner"}],
        )
        db.commit()
        db.refresh(coll)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to create collection.",
            status_code=500,
        ) from exc

    return _collection_response(
        collection=coll,
        requester_access_role="owner",
        member_count=1,
    )


@router.get(
    "",
    response_model=list[DocumentCollectionResponse],
    dependencies=[Depends(require_permissions("collections:read"))],
)
def list_collections(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[DocumentCollectionResponse]:
    repo = CollectionsRepository(db)
    users_repo = UsersRepository(db)
    items = repo.list_accessible_for_user_global(user_id=auth.user_id)
    responses: list[DocumentCollectionResponse] = []
    for item in items:
        permission = repo.get_user_permission_global(
            collection_id=item.id,
            user_id=auth.user_id,
        )
        responses.append(
            _collection_response(
                collection=item,
                requester_access_role=_normalize_member_role(
                    permission.role if permission is not None else None
                ),
                member_count=repo.count_connected_members_global(collection_id=item.id),
                other_member_email=_resolve_other_member_email(
                    repo=repo,
                    users_repo=users_repo,
                    collection_id=item.id,
                    requester_user_id=auth.user_id,
                ),
                other_member_avatar=_resolve_other_member_avatar(
                    repo=repo,
                    users_repo=users_repo,
                    collection_id=item.id,
                    requester_user_id=auth.user_id,
                ),
            )
        )
    return responses


@router.get(
    "/invitations",
    response_model=list[CollectionInvitationResponse],
    dependencies=[Depends(require_permissions("collections:read"))],
)
def list_pending_invitations(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[CollectionInvitationResponse]:
    repo = CollectionsRepository(db)
    users = UsersRepository(db)
    items = repo.list_pending_for_user_global(user_id=auth.user_id)
    responses: list[CollectionInvitationResponse] = []
    for item in items:
        permissions = repo.get_permissions_global(collection_id=item.id)
        inviter_user_id = next(
            (
                permission.user_id
                for permission in permissions
                if _normalize_member_role(getattr(permission, "role", None)) == "member"
            ),
            None,
        )
        inviter = users.get_by_id_global(inviter_user_id) if inviter_user_id else None
        responses.append(
            CollectionInvitationResponse(
                id=item.id,
                tenant_id=item.tenant_id,
                name=item.name,
                connection_code=item.connection_code,
                description=item.description,
                requester_access_role="pending",
                member_count=repo.count_connected_members_global(collection_id=item.id),
                created_at=item.created_at,
                updated_at=item.updated_at,
                inviter_user_id=inviter_user_id,
                inviter_user_email=inviter.email if inviter is not None else None,
            )
        )
    return responses


@router.get(
    "/notifications",
    response_model=list[CollectionNotificationResponse],
    dependencies=[Depends(require_permissions("collections:read"))],
)
def list_collection_notifications(
    offset: int = Query(default=0, ge=0, le=100_000),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[CollectionNotificationResponse]:
    muted_domains = (
        db.execute(
            select(UserNotificationPreference.muted_domains).where(
                UserNotificationPreference.tenant_id == auth.tenant_id,
                UserNotificationPreference.user_id == auth.user_id,
            )
        ).scalar_one_or_none()
        or []
    )
    if "collections" in muted_domains:
        return []
    repo = CollectionNotificationsRepository(db)
    items = repo.list_for_user(user_id=auth.user_id, limit=30, offset=offset)
    return [_notification_response(item) for item in items]


@router.get(
    "/{collection_id}",
    response_model=DocumentCollectionResponse,
    dependencies=[Depends(require_permissions("collections:read"))],
)
def get_collection(
    collection_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DocumentCollectionResponse:
    repo = CollectionsRepository(db)
    users_repo = UsersRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    requester_access_role = _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )
    return _collection_response(
        collection=collection,
        requester_access_role=_normalize_member_role(requester_access_role),
        member_count=repo.count_connected_members_global(collection_id=collection.id),
        other_member_email=_resolve_other_member_email(
            repo=repo,
            users_repo=users_repo,
            collection_id=collection.id,
            requester_user_id=auth.user_id,
        ),
        other_member_avatar=_resolve_other_member_avatar(
            repo=repo,
            users_repo=users_repo,
            collection_id=collection.id,
            requester_user_id=auth.user_id,
        ),
    )


@router.get(
    "/{collection_id}/notifications",
    response_model=list[CollectionNotificationResponse],
    dependencies=[Depends(require_permissions("collections:read"))],
)
def list_collection_notifications_for_collection(
    collection_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[CollectionNotificationResponse]:
    repo = CollectionsRepository(db)
    notifications_repo = CollectionNotificationsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )
    items = notifications_repo.list_for_user(
        user_id=auth.user_id,
        collection_id=collection_id,
        limit=20,
    )
    return [_notification_response(item) for item in items]


@router.post(
    "/notifications/{notification_id}/read",
    response_model=CollectionNotificationResponse,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def mark_collection_notification_read(
    notification_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> CollectionNotificationResponse:
    repo = CollectionNotificationsRepository(db)
    item = repo.get_for_user(user_id=auth.user_id, notification_id=notification_id)
    if item is None:
        raise ApiError(
            code="COLLECTION_NOTIFICATION_NOT_FOUND",
            message="Notification not found.",
            status_code=404,
        )
    if item.read_at is None:
        repo.mark_read(notification=item, read_at=datetime.now(tz=UTC))
        db.commit()
        db.refresh(item)
    return _notification_response(item)


@router.post(
    "/notifications/read-all",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def mark_all_collection_notifications_read(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionNotificationsRepository(db)
    repo.mark_all_read_for_user(user_id=auth.user_id, read_at=datetime.now(tz=UTC))
    db.commit()
    return Response(status_code=204)


@router.delete(
    "/notifications/{notification_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def delete_collection_notification(
    notification_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionNotificationsRepository(db)
    deleted = repo.delete_for_user(user_id=auth.user_id, notification_id=notification_id)
    if not deleted:
        raise ApiError(
            code="COLLECTION_NOTIFICATION_NOT_FOUND",
            message="Notification not found.",
            status_code=404,
        )
    db.commit()
    return Response(status_code=204)


@router.delete(
    "/notifications",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def clear_collection_notifications(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionNotificationsRepository(db)
    repo.delete_all_for_user(user_id=auth.user_id)
    db.commit()
    return Response(status_code=204)


@router.delete(
    "/{collection_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def delete_collection(
    collection_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    requester_role = _normalize_member_role(
        _enforce_collection_access_global(
            repo=repo,
            collection_id=collection_id,
            user_id=auth.user_id,
        )
    )
    if requester_role != "owner":
        raise ApiError(
            code="FORBIDDEN",
            message="Only the collection owner can delete this collection.",
            status_code=403,
        )

    permissions = repo.get_permissions_global(collection_id=collection_id)
    users_repo = UsersRepository(db)
    actor_user = users_repo.get_by_id_global(auth.user_id)
    actor_email = actor_user.email if actor_user is not None else "A member"
    notifications_repo = CollectionNotificationsRepository(db)
    try:
        for message in (
            db.query(DBCollectionChatMessage)
            .filter(DBCollectionChatMessage.collection_id == collection_id)
            .all()
        ):
            _queue_media_cleanup(
                db=db,
                collection=collection,
                media_id=message.media_id,
                object_key=message.media_object_key,
                owner_user_id=message.user_id,
                bucket=get_settings().minio_bucket,
            )
        for permission in permissions:
            if permission.user_id == auth.user_id:
                continue
            if _normalize_member_role(permission.role) not in {
                "owner",
                "member",
                "pending",
            }:
                continue
            _create_collection_notification(
                notifications_repo=notifications_repo,
                recipient_user_id=permission.user_id,
                actor_user_id=auth.user_id,
                collection_id=None,
                collection_name=collection.name,
                event_type="collection_deleted",
                message=f'{actor_email} deleted the collection "{collection.name}".',
            )
        repo.delete(
            tenant_id=collection.tenant_id,
            collection_id=collection_id,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to delete collection %s", collection_id)
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to delete collection.",
            status_code=500,
        ) from exc

    return Response(status_code=204)


@router.post(
    "/{collection_id}/documents",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
async def add_documents_to_collection(
    collection_id: uuid.UUID,
    payload: CollectionDocumentAdd,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    requester_role = _normalize_member_role(
        _enforce_collection_access_global(
            repo=repo,
            collection_id=collection_id,
            user_id=auth.user_id,
        )
    )
    if not _is_connected_role(requester_role):
        raise ApiError(
            code="FORBIDDEN",
            message="Approve the collection connection before adding documents.",
            status_code=403,
        )

    try:
        repo.add_documents_for_user_global(
            collection_id=collection_id,
            user_id=auth.user_id,
            document_ids=payload.document_ids,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to add documents to collection.",
            status_code=500,
        ) from exc

    try:
        await broadcast_manager.publish_event(
            str(collection_id),
            "document_sync",
            {"action": "add", "document_ids": [str(d) for d in payload.document_ids]},
        )
    except Exception:  # noqa: BLE001
        logger.warning("Collection document add broadcast failed", exc_info=True)

    return Response(status_code=204)


@router.get(
    "/{collection_id}/documents",
    response_model=list[DocumentMetadataResponse],
    dependencies=[Depends(require_permissions("collections:read"))],
)
def list_collection_documents(
    collection_id: uuid.UUID,
    response: Response,
    limit: int = Query(default=200, ge=1, le=200),
    before: datetime | None = Query(default=None),  # noqa: B008
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[DocumentMetadataResponse]:
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    requester_role = _normalize_member_role(
        _enforce_collection_access_global(
            repo=repo,
            collection_id=collection_id,
            user_id=auth.user_id,
        )
    )
    if not _is_connected_role(requester_role):
        raise ApiError(
            code="FORBIDDEN",
            message="Approve the collection connection before using shared documents.",
            status_code=403,
        )

    documents = repo.list_documents_for_user(
        collection_id=collection_id,
        user_id=auth.user_id,
        limit=limit + 1,
        before=before,
    )
    has_more = len(documents) > limit
    if has_more:
        documents = documents[:-1]
        response.headers["X-Collection-Has-More"] = "true"
        response.headers["X-Collection-Next-Cursor"] = documents[-1].created_at.isoformat()
    else:
        response.headers["X-Collection-Has-More"] = "false"
    return [_document_metadata_response(item) for item in documents]


@router.delete(
    "/{collection_id}/documents",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
async def remove_documents_from_collection(
    collection_id: uuid.UUID,
    payload: CollectionDocumentRemove,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    requester_role = _normalize_member_role(
        _enforce_collection_access_global(
            repo=repo,
            collection_id=collection_id,
            user_id=auth.user_id,
        )
    )
    if not _is_connected_role(requester_role):
        raise ApiError(
            code="FORBIDDEN",
            message="Approve the collection connection before changing documents.",
            status_code=403,
        )

    try:
        repo.remove_documents_for_user_global(
            collection_id=collection_id,
            user_id=auth.user_id,
            document_ids=payload.document_ids,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to remove documents from collection.",
            status_code=500,
        ) from exc

    try:
        await broadcast_manager.publish_event(
            str(collection_id),
            "document_sync",
            {
                "action": "remove",
                "document_ids": [str(d) for d in payload.document_ids],
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning("Collection document remove broadcast failed", exc_info=True)

    return Response(status_code=204)


@router.post(
    "/{collection_id}/permissions",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def add_permissions(
    collection_id: uuid.UUID,
    payload: CollectionPermissionAdd,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    requester_role = _normalize_member_role(
        _enforce_collection_access_global(
            repo=repo,
            collection_id=collection_id,
            user_id=auth.user_id,
        )
    )
    if requester_role != "owner":
        raise ApiError(
            code="FORBIDDEN",
            message="Only the collection owner can send invitations.",
            status_code=403,
        )

    target_user = UsersRepository(db).get_by_collection_code_global(
        payload.connection_code.strip().upper()
    )
    if target_user is None or not target_user.is_active:
        raise ApiError(
            code="INVALID_COLLECTION_MEMBER",
            message="That collection ID was not found.",
            status_code=404,
        )
    if target_user.id == auth.user_id:
        raise ApiError(
            code="INVALID_COLLECTION_MEMBER",
            message="Use another user's collection ID to connect.",
            status_code=400,
        )

    # Check if a 1:1 direct connection already exists between auth.user_id and target_user.id
    from app.documents.models.collection import (
        CollectionPermission as DBCollectionPermission,
    )

    user_collections = (
        db.query(DBCollectionPermission.collection_id)
        .filter(DBCollectionPermission.user_id == auth.user_id)
        .all()
    )
    user_col_ids = [c[0] for c in user_collections]

    if user_col_ids:
        duplicate_conn = (
            db.query(DBCollectionPermission.collection_id)
            .filter(
                DBCollectionPermission.collection_id.in_(user_col_ids),
                DBCollectionPermission.user_id == target_user.id,
            )
            .first()
        )
        if duplicate_conn:
            col_id = duplicate_conn[0]
            existing_col = repo.get_by_id_global(collection_id=col_id)
            if (
                existing_col
                and existing_col.description
                and "1:1 Connection" in existing_col.description
            ):
                raise ApiError(
                    code="DUPLICATE_CONNECTION",
                    message="Connection already exists!",
                    status_code=400,
                )

    if repo.count_connected_members_global(collection_id=collection.id) >= 10:
        raise ApiError(
            code="COLLECTION_BRIDGE_FULL",
            message="This collection already has its maximum ten members.",
            status_code=400,
        )
    if repo.has_pending_invite_global(collection_id=collection.id):
        raise ApiError(
            code="COLLECTION_BRIDGE_PENDING",
            message="This collection already has a pending connection request.",
            status_code=400,
        )

    if (
        repo.get_user_permission_global(
            collection_id=collection.id,
            user_id=target_user.id,
        )
        is not None
    ):
        raise ApiError(
            code="COLLECTION_BRIDGE_EXISTS",
            message="That user is already connected to this collection.",
            status_code=400,
        )

    try:
        repo.add_permissions(
            tenant_id=collection.tenant_id,
            collection_id=collection_id,
            permissions=[{"user_id": target_user.id, "role": "pending"}],
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to update collection permissions.",
            status_code=500,
        ) from exc

    return Response(status_code=204)


@router.get(
    "/{collection_id}/permissions",
    response_model=list[CollectionPermissionResponse],
    dependencies=[Depends(require_permissions("collections:read"))],
)
def list_permissions(
    collection_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[CollectionPermissionResponse]:
    repo = CollectionsRepository(db)
    users = UsersRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    requester_role = _normalize_member_role(
        _enforce_collection_access_global(
            repo=repo,
            collection_id=collection_id,
            user_id=auth.user_id,
        )
    )
    if not _is_connected_role(requester_role):
        raise ApiError(
            code="FORBIDDEN",
            message="Approve the collection connection before viewing connection members.",
            status_code=403,
        )

    permissions_list = []
    for item in repo.get_permissions_global(collection_id=collection_id):
        target_user = users.get_by_id_global(item.user_id)
        permissions_list.append(
            CollectionPermissionResponse(
                id=item.id,
                collection_id=item.collection_id,
                user_id=item.user_id,
                role=item.role,
                user_email=target_user.email if target_user else None,
                user_avatar=target_user.avatar if target_user else None,
                created_at=item.created_at,
            )
        )
    return permissions_list


@router.delete(
    "/{collection_id}/permissions",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def remove_permissions(
    collection_id: uuid.UUID,
    payload: CollectionPermissionRemove,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    requester_role = _normalize_member_role(
        _enforce_collection_access_global(
            repo=repo,
            collection_id=collection_id,
            user_id=auth.user_id,
        )
    )

    if requester_role == "pending":
        raise ApiError(
            code="FORBIDDEN",
            message="Approve the collection connection before changing members.",
            status_code=403,
        )

    if requester_role == "owner":
        user_ids = [user_id for user_id in payload.user_ids if user_id != auth.user_id]
        if not user_ids:
            raise ApiError(
                code="INVALID_COLLECTION_MEMBER",
                message="Select at least one non-owner member to remove.",
                status_code=400,
            )
    else:
        if payload.user_ids and any(user_id != auth.user_id for user_id in payload.user_ids):
            raise ApiError(
                code="FORBIDDEN",
                message="Members can only leave collections themselves.",
                status_code=403,
            )
        user_ids = [auth.user_id]

    tenant_id = collection.tenant_id
    users_repo = UsersRepository(db)
    notifications_repo = CollectionNotificationsRepository(db)
    actor_user = users_repo.get_by_id_global(auth.user_id)
    actor_email = actor_user.email if actor_user is not None else "A member"
    try:
        for target_user_id in user_ids:
            target_user = users_repo.get_by_id_global(target_user_id)
            if target_user is None:
                continue
            if requester_role == "owner":
                _create_collection_notification(
                    notifications_repo=notifications_repo,
                    recipient_user_id=target_user_id,
                    actor_user_id=auth.user_id,
                    collection_id=None,
                    collection_name=collection.name,
                    event_type="collection_removed",
                    message=f'{actor_email} removed you from "{collection.name}".',
                )
            else:
                for permission in repo.get_permissions_global(collection_id=collection_id):
                    if permission.user_id == auth.user_id:
                        continue
                    if _normalize_member_role(permission.role) not in {
                        "owner",
                        "member",
                    }:
                        continue
                    _create_collection_notification(
                        notifications_repo=notifications_repo,
                        recipient_user_id=permission.user_id,
                        actor_user_id=auth.user_id,
                        collection_id=collection_id,
                        collection_name=collection.name,
                        event_type="member_left",
                        idempotency_key=hashlib.sha256(
                            f"{collection_id}|{auth.user_id}|{permission.user_id}|member_left".encode()
                        ).hexdigest(),
                        message=f'{actor_email} left "{collection.name}" on {datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")}.',
                    )
        _record_collection_security_change(
            db=db,
            repo=repo,
            notifications_repo=notifications_repo,
            collection=collection,
            actor_user_id=auth.user_id,
            excluded_user_ids=set(user_ids),
        )
        repo.remove_permissions(
            tenant_id=tenant_id,
            collection_id=collection_id,
            user_ids=user_ids,
        )
        if not repo.get_permissions_global(collection_id=collection_id):
            repo.delete(tenant_id=collection.tenant_id, collection_id=collection_id)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to remove collection permissions.",
            status_code=500,
        ) from exc

    return Response(status_code=204)


@router.post(
    "/{collection_id}/invitations/respond",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def respond_to_collection_invitation(
    collection_id: uuid.UUID,
    payload: CollectionInvitationRespond,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )
    permission = repo.get_user_permission_global(
        collection_id=collection_id,
        user_id=auth.user_id,
    )
    if permission is None or permission.role != "pending":
        raise ApiError(
            code="FORBIDDEN",
            message="No pending collection invitation was found.",
            status_code=403,
        )

    try:
        if payload.action == "approve":
            if repo.count_connected_members_global(collection_id=collection_id) >= 10:
                raise ApiError(
                    code="COLLECTION_BRIDGE_FULL",
                    message="This collection already has its maximum ten members.",
                    status_code=400,
                )
            repo.update_permission_role_global(
                collection_id=collection_id,
                user_id=auth.user_id,
                role="member",
            )
            _record_collection_security_change(
                db=db,
                repo=repo,
                notifications_repo=CollectionNotificationsRepository(db),
                collection=collection,
                actor_user_id=auth.user_id,
            )
        else:
            repo.remove_permissions(
                tenant_id=collection.tenant_id,
                collection_id=collection_id,
                user_ids=[auth.user_id],
            )
            collection.security_epoch = int(collection.security_epoch or 0) + 1
            _maybe_rotate_chat_epoch(db, collection=collection, reason="member-removed")
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to respond to collection invitation.",
            status_code=500,
        ) from exc

    return Response(status_code=204)


# Real-time Team Chat Endpoints
import json  # noqa: E402


class CollectionBroadcastManager:
    stream_prefix = "averqel:collection-events:v1"

    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}
        self.active_connection_users: dict[str, dict[str, int]] = {}
        self.redis_tasks: dict[str, asyncio.Task] = {}
        # Delayed client init until get_settings is available
        self._redis_client = None

    @property
    def redis_client(self):
        if self._redis_client is None:
            from app.core.config import get_settings

            self._redis_client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        return self._redis_client

    async def connect(
        self,
        collection_id: str,
        websocket: WebSocket,
        *,
        user_id: uuid.UUID,
        max_connections: int,
    ) -> bool:
        user_key = str(user_id)
        users = self.active_connection_users.setdefault(collection_id, {})
        if users.get(user_key, 0) >= max(1, max_connections):
            await websocket.close(code=4429)
            return False
        redis_counter_key = f"averqel:collection-ws:v1:{collection_id}:{user_key}"
        redis_counted = False
        try:
            redis_count = int(
                await asyncio.wait_for(self.redis_client.incr(redis_counter_key), 1.0)
            )
            redis_counted = True
            if redis_count == 1:
                await self.redis_client.expire(redis_counter_key, 3600)
            if redis_count > max(1, max_connections):
                await self.redis_client.decr(redis_counter_key)
                await websocket.close(code=4429)
                return False
        except Exception:  # noqa: BLE001
            # Keep the local guard as a safe fallback when Redis is unavailable;
            # the durable global guard is restored automatically on reconnect.
            logger.warning("Global collection WebSocket limit unavailable", exc_info=True)
        await websocket.accept()
        if collection_id not in self.active_connections:
            self.active_connections[collection_id] = set()
            task = asyncio.create_task(self._redis_subscribe_loop(collection_id))
            self.redis_tasks[collection_id] = task
        self.active_connections[collection_id].add(websocket)
        users[user_key] = users.get(user_key, 0) + 1
        websocket.state.collection_user_id = user_key
        websocket.state.collection_redis_counter_key = redis_counter_key if redis_counted else None
        return True

    async def disconnect(self, collection_id: str, websocket: WebSocket) -> None:
        if collection_id in self.active_connections:
            self.active_connections[collection_id].discard(websocket)
            user_key = str(getattr(websocket.state, "collection_user_id", ""))
            redis_counter_key = getattr(websocket.state, "collection_redis_counter_key", None)
            if redis_counter_key:
                try:
                    await self.redis_client.decr(redis_counter_key)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Global collection WebSocket counter release failed", exc_info=True
                    )
            users = self.active_connection_users.get(collection_id)
            if users is not None and user_key:
                count = users.get(user_key, 0) - 1
                if count > 0:
                    users[user_key] = count
                else:
                    users.pop(user_key, None)
            if not self.active_connections[collection_id]:
                del self.active_connections[collection_id]
                self.active_connection_users.pop(collection_id, None)
                task = self.redis_tasks.pop(collection_id, None)
                if task:
                    task.cancel()

    def has_user_connection(self, user_id: uuid.UUID) -> bool:
        user_key = str(user_id)
        return any(user_key in users for users in self.active_connection_users.values())

    async def publish_event(self, collection_id: str, event_type: str, data: dict) -> None:
        event = {
            "type": event_type,
            "data": data,
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        payload = json.dumps(event, separators=(",", ":"))
        try:
            event_cursor = await self.redis_client.xadd(
                f"{self.stream_prefix}:{collection_id}",
                {"payload": payload},
                maxlen=10_000,
                approximate=True,
            )
            event["event_cursor"] = str(event_cursor)
            payload = json.dumps(event, separators=(",", ":"))
        except Exception:  # noqa: BLE001
            # Pub/Sub remains the low-latency path; REST history is the source
            # of truth if Redis persistence is temporarily unavailable.
            logger.warning("Collection event replay stream unavailable", exc_info=True)
        await self.redis_client.publish(f"collection_room:{collection_id}", payload)

    async def replay_events(self, collection_id: str, cursor: str) -> list[tuple[str, dict]]:
        if not cursor or cursor == "$":
            return []
        batches = await self.redis_client.xread(
            {f"{self.stream_prefix}:{collection_id}": cursor}, count=100
        )
        events: list[tuple[str, dict]] = []
        for _stream, entries in batches or []:
            for entry_id, fields in entries:
                try:
                    payload = json.loads(str(fields.get("payload") or ""))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict) and isinstance(payload.get("type"), str):
                    events.append((str(entry_id), payload))
        return events

    async def _redis_subscribe_loop(self, collection_id: str) -> None:
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(f"collection_room:{collection_id}")
        try:
            async for message in pubsub.listen():
                if message and message.get("type") == "message":
                    payload = message.get("data")
                    if payload:
                        connections = self.active_connections.get(collection_id, set())
                        if connections:
                            tasks = [
                                asyncio.create_task(conn.send_text(payload))
                                for conn in list(connections)
                            ]
                            if tasks:
                                await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"collection_room:{collection_id}")
            await pubsub.close()
        except Exception:
            logger.exception(f"Error in Redis subscription loop for collection {collection_id}")
            await asyncio.sleep(2)
            if collection_id in self.active_connections:
                task = asyncio.create_task(self._redis_subscribe_loop(collection_id))
                self.redis_tasks[collection_id] = task


broadcast_manager = CollectionBroadcastManager()

from app.core.config import Settings, get_settings  # noqa: E402
from app.deepspace.api.chats import _authenticate_websocket_auth_context  # noqa: E402


@router.get("/{collection_id}/ws-ticket")
def create_collection_ws_ticket(
    collection_id: uuid.UUID,
    device_id: str | None = Query(default=None, min_length=8, max_length=128),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, int | str]:
    repo = CollectionsRepository(db)
    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )
    if device_id:
        device = (
            db.query(CollectionDevice)
            .filter(
                CollectionDevice.tenant_id == auth.tenant_id,
                CollectionDevice.user_id == auth.user_id,
                CollectionDevice.device_id == device_id,
            )
            .first()
        )
        if device is None:
            device = CollectionDevice(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                device_id=device_id,
            )
            db.add(device)
        if device.revoked_at is not None:
            raise ApiError(
                code="DEVICE_REVOKED", message="This device has been revoked.", status_code=403
            )
        device.last_seen_at = datetime.now(UTC)
        db.commit()
    ticket = secrets.token_urlsafe(32)
    get_redis_client().setex(
        f"collection_ws_ticket:{ticket}",
        settings.document_event_stream_ticket_ttl_seconds,
        json.dumps(
            {
                "user_id": str(auth.user_id),
                "tenant_id": str(auth.tenant_id),
                "roles": sorted(auth.roles),
                "permissions": sorted(getattr(auth, "permissions", frozenset())),
                "token_id": auth.token_id,
                "device_id": device_id or "legacy",
            }
        ),
    )
    return {
        "ticket": ticket,
        "expires_in_seconds": settings.document_event_stream_ticket_ttl_seconds,
    }


@router.websocket("/{collection_id}/ws")
async def collection_websocket(
    websocket: WebSocket,
    collection_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    auth = None
    connected = False
    try:
        auth = await _authenticate_websocket_auth_context(websocket, db=db, settings=settings)

        repo = CollectionsRepository(db)
        collection = repo.get_by_id_global(collection_id=collection_id)
        if collection is None:
            await websocket.close(code=4004)
            return

        _enforce_collection_access_global(
            repo=repo,
            collection_id=collection_id,
            user_id=auth.user_id,
        )
        device_id = str(websocket.query_params.get("device_id") or "legacy")[:128]
        if device_id != "legacy":
            device = (
                db.query(CollectionDevice)
                .filter(
                    CollectionDevice.tenant_id == auth.tenant_id,
                    CollectionDevice.user_id == auth.user_id,
                    CollectionDevice.device_id == device_id,
                )
                .first()
            )
            if device is None or device.revoked_at is not None:
                await websocket.close(code=4403)
                return
            device.last_seen_at = datetime.now(UTC)
            db.commit()

        connected = await broadcast_manager.connect(
            str(collection_id),
            websocket,
            user_id=auth.user_id,
            max_connections=settings.collection_ws_connections_per_user,
        )
        if not connected:
            return

        try:
            replay_cursor = str(websocket.query_params.get("last_event_id") or "$")
            for event_cursor, event in await broadcast_manager.replay_events(
                str(collection_id), replay_cursor
            ):
                event["event_cursor"] = event_cursor
                await websocket.send_json(event)
        except Exception:  # noqa: BLE001
            logger.warning("Collection event replay failed", exc_info=True)

        # Mark user online
        presence = db.query(UserPresence).filter(UserPresence.user_id == auth.user_id).first()
        if not presence:
            presence = UserPresence(user_id=auth.user_id, is_online=True)
            db.add(presence)
        else:
            presence.is_online = True
            presence.last_seen = datetime.now(UTC)
        db.commit()

        # Broadcast presence change
        await broadcast_manager.publish_event(
            str(collection_id),
            "presence_change",
            {
                "user_id": str(auth.user_id),
                "is_online": True,
                "last_seen": presence.last_seen.isoformat(),
            },
        )

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60)
            except TimeoutError:
                # Force a write on otherwise idle sockets so dead TCP sessions
                # are noticed and removed instead of retaining presence forever.
                await websocket.send_json(
                    {"type": "ping", "data": {"timestamp": datetime.now(UTC).isoformat()}}
                )
                continue
            except json.JSONDecodeError:
                continue

            action = data.get("action")
            db.rollback()  # Refresh long-lived session transaction to read fresh database state
            if device_id != "legacy":
                active_device = (
                    db.query(CollectionDevice)
                    .filter(
                        CollectionDevice.tenant_id == auth.tenant_id,
                        CollectionDevice.user_id == auth.user_id,
                        CollectionDevice.device_id == device_id,
                        CollectionDevice.revoked_at.is_(None),
                    )
                    .first()
                )
                if active_device is None:
                    await websocket.close(code=4403)
                    break
            try:
                RateLimitService(settings).enforce_counter(
                    key=(f"rate_limit:collection_ws:{auth.user_id}:{collection_id}"),
                    limit=settings.collection_ws_messages_per_user_per_minute,
                    window_seconds=60,
                    scope="collection_websocket",
                )
            except ApiError as exc:
                await websocket.send_json(
                    {"type": "error", "data": {"code": exc.code, "message": exc.message}}
                )
                continue
            if action == "ping":
                await websocket.send_json(
                    {"type": "pong", "data": {"timestamp": datetime.now(UTC).isoformat()}}
                )
            elif action == "post_message":
                content = str(data.get("content", "")).strip()
                if not content:
                    continue
                if _user_has_collection_block(
                    db, collection_id=collection_id, user_id=auth.user_id
                ):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "code": "CHAT_BLOCKED",
                                "message": "Messaging is unavailable because a collection member is blocked.",
                            },
                        }
                    )
                    continue
                if len(content) > 4096:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "Messages are limited to 4096 characters.",
                            },
                        }
                    )
                    continue
                is_media = bool(data.get("is_media", False))
                media_mime_type = data.get("media_mime_type")
                client_message_id = str(data.get("client_message_id") or "").strip() or None
                if client_message_id and len(client_message_id) > 128:
                    continue

                media_id, media_object_key = _require_complete_media_reference(
                    collection=collection,
                    is_media=is_media,
                    media_id=data.get("media_id"),
                    media_object_key=data.get("media_object_key"),
                )
                registered_media = _validate_registered_media(
                    db=db,
                    collection=collection,
                    user_id=auth.user_id,
                    media_id=media_id,
                    object_key=media_object_key,
                )

                users_repo = UsersRepository(db)
                user = users_repo.get_by_id_global(auth.user_id)
                user_email = user.email if user else "anonymous@averqel.com"
                user_avatar = user.avatar if user else None

                existing_msg = None
                if client_message_id:
                    existing_msg = (
                        db.query(DBCollectionChatMessage)
                        .filter(
                            DBCollectionChatMessage.collection_id == collection_id,
                            DBCollectionChatMessage.user_id == auth.user_id,
                            DBCollectionChatMessage.client_message_id == client_message_id,
                        )
                        .first()
                    )
                if existing_msg is not None and (
                    existing_msg.message != content
                    or existing_msg.is_media != is_media
                    or existing_msg.media_object_key != media_object_key
                ):
                    raise ApiError(
                        code="IDEMPOTENCY_CONFLICT",
                        message="This client message ID was already used for different content.",
                        status_code=409,
                    )
                db_msg = existing_msg or DBCollectionChatMessage(
                    id=uuid.uuid4(),
                    collection_id=collection_id,
                    user_id=auth.user_id,
                    message=content,
                    client_message_id=client_message_id,
                    is_media=is_media,
                    media_mime_type=media_mime_type,
                    media_id=media_id,
                    media_object_key=media_object_key,
                    status="sent",
                )
                created_message = existing_msg is None
                if created_message:
                    try:
                        repo.create_chat_message(chat_message=db_msg)
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                        if client_message_id is None:
                            raise
                        db_msg = (
                            db.query(DBCollectionChatMessage)
                            .filter(
                                DBCollectionChatMessage.collection_id == collection_id,
                                DBCollectionChatMessage.user_id == auth.user_id,
                                DBCollectionChatMessage.client_message_id == client_message_id,
                            )
                            .first()
                        )
                        if db_msg is None:
                            raise
                        created_message = False
                if created_message:
                    if registered_media is not None:
                        registered_media.status = "attached"
                        registered_media.attached_message_id = db_msg.id
                    member_ids = [
                        permission.user_id
                        for permission in repo.get_permissions_global(collection_id=collection_id)
                        if permission.user_id != auth.user_id
                        and _is_connected_role(getattr(permission, "role", None))
                    ]
                    for member_id in member_ids:
                        for member_device_id in _active_device_ids(
                            db, tenant_id=collection.tenant_id, user_id=member_id
                        ):
                            db.add(
                                CollectionChatDelivery(
                                    message_id=db_msg.id,
                                    collection_id=collection_id,
                                    user_id=member_id,
                                    device_id=member_device_id,
                                )
                            )
                    db.commit()

                msg_payload = {
                    "id": str(db_msg.id),
                    "collection_id": str(db_msg.collection_id),
                    "user_id": str(db_msg.user_id),
                    "user_email": user_email,
                    "user_avatar": user_avatar,
                    "message": db_msg.message,
                    "client_message_id": db_msg.client_message_id,
                    "status": db_msg.status,
                    "is_media": db_msg.is_media,
                    "media_mime_type": db_msg.media_mime_type,
                    "media_id": str(db_msg.media_id) if db_msg.media_id else None,
                    "media_object_key": db_msg.media_object_key,
                    "reactions": db_msg.reactions,
                    "created_at": db_msg.created_at.isoformat(),
                }

                await broadcast_manager.publish_event(
                    str(collection_id), "new_message", msg_payload
                )
            elif action == "typing":
                is_typing = bool(data.get("is_typing", False))
                await broadcast_manager.publish_event(
                    str(collection_id),
                    "user_typing",
                    {"user_id": str(auth.user_id), "is_typing": is_typing},
                )
            elif action == "react":
                msg_id = data.get("message_id")
                reaction = data.get("reaction")
                if msg_id and reaction:
                    from app.documents.models.collection import (
                        CollectionChatMessage as DBCollectionChatMessage,
                    )

                    db_msg = (
                        db.query(DBCollectionChatMessage)
                        .filter(
                            DBCollectionChatMessage.id == uuid.UUID(msg_id),
                            DBCollectionChatMessage.collection_id == collection_id,
                        )
                        .first()
                    )
                    if db_msg:
                        try:
                            reactions_dict = json.loads(db_msg.reactions)
                        except Exception:
                            reactions_dict = {}

                        user_id_str = str(auth.user_id)
                        if reactions_dict.get(user_id_str) == reaction:
                            reactions_dict.pop(user_id_str, None)
                        else:
                            reactions_dict[user_id_str] = reaction

                        db_msg.reactions = json.dumps(reactions_dict)
                        db.commit()

                        await broadcast_manager.publish_event(
                            str(collection_id),
                            "message_reacted",
                            {
                                "message_id": str(db_msg.id),
                                "reactions": db_msg.reactions,
                            },
                        )
            elif action == "delivered":
                msg_id = data.get("message_id")
                if msg_id:
                    db_msg = (
                        db.query(DBCollectionChatMessage)
                        .filter(
                            DBCollectionChatMessage.id == uuid.UUID(msg_id),
                            DBCollectionChatMessage.collection_id == collection_id,
                        )
                        .first()
                    )
                    if db_msg:
                        receipt = (
                            db.query(CollectionChatDelivery)
                            .filter(
                                CollectionChatDelivery.message_id == db_msg.id,
                                CollectionChatDelivery.collection_id == collection_id,
                                CollectionChatDelivery.user_id == auth.user_id,
                                CollectionChatDelivery.device_id == device_id,
                            )
                            .first()
                        )
                        if receipt is None:
                            receipt = CollectionChatDelivery(
                                message_id=db_msg.id,
                                collection_id=collection_id,
                                user_id=auth.user_id,
                                device_id=device_id,
                            )
                            db.add(receipt)
                        receipt.status = "delivered"
                        receipt.delivered_at = datetime.now(UTC)
                        db.commit()
                        await broadcast_manager.publish_event(
                            str(collection_id),
                            "message_delivered",
                            {
                                "message_id": str(db_msg.id),
                                "user_id": str(auth.user_id),
                                "status": "delivered",
                            },
                        )
            elif action == "delete":
                msg_id = data.get("message_id")
                if msg_id:
                    from app.documents.models.collection import (
                        CollectionChatMessage as DBCollectionChatMessage,
                    )

                    db_msg = (
                        db.query(DBCollectionChatMessage)
                        .filter(
                            DBCollectionChatMessage.id == uuid.UUID(msg_id),
                            DBCollectionChatMessage.collection_id == collection_id,
                        )
                        .first()
                    )
                    # Senders or collection owners can delete
                    permission = repo.get_user_permission_global(
                        collection_id=collection_id,
                        user_id=auth.user_id,
                    )
                    role = str(getattr(permission, "role", "")) if permission else ""
                    is_owner = role == "owner"
                    if db_msg and (db_msg.user_id == auth.user_id or is_owner):
                        _queue_media_cleanup(
                            db=db,
                            collection=collection,
                            media_id=db_msg.media_id,
                            object_key=db_msg.media_object_key,
                            owner_user_id=db_msg.user_id,
                            bucket=settings.minio_bucket,
                        )
                        db_msg.message = "This message was deleted"
                        db_msg.is_media = False
                        db_msg.media_mime_type = None
                        db_msg.media_object_key = None
                        db_msg.reactions = "{}"
                        db.commit()
                        await broadcast_manager.publish_event(
                            str(collection_id),
                            "message_deleted",
                            {
                                "message_id": str(msg_id),
                                "message": "This message was deleted",
                            },
                        )
            elif action == "read":
                unread_msgs = (
                    db.query(DBCollectionChatMessage)
                    .filter(
                        DBCollectionChatMessage.collection_id == collection_id,
                        DBCollectionChatMessage.user_id != auth.user_id,
                    )
                    .all()
                )
                if unread_msgs:
                    for m in unread_msgs:
                        receipt = (
                            db.query(CollectionChatDelivery)
                            .filter(
                                CollectionChatDelivery.message_id == m.id,
                                CollectionChatDelivery.collection_id == collection_id,
                                CollectionChatDelivery.user_id == auth.user_id,
                                CollectionChatDelivery.device_id == device_id,
                            )
                            .first()
                        )
                        if receipt is None:
                            receipt = CollectionChatDelivery(
                                message_id=m.id,
                                collection_id=collection_id,
                                user_id=auth.user_id,
                                device_id=device_id,
                            )
                            db.add(receipt)
                        receipt.status = "read"
                        receipt.read_at = datetime.now(UTC)
                    db.commit()
                    await broadcast_manager.publish_event(
                        str(collection_id),
                        "messages_read",
                        {
                            "reader_id": str(auth.user_id),
                            "message_ids": [str(message.id) for message in unread_msgs],
                            "status": "read",
                        },
                    )
    except ApiError as exc:
        logger.info("Collection WebSocket rejected: %s", exc.code)
        try:
            await websocket.close(code=4401 if exc.status_code == 401 else 4403)
        except Exception:  # noqa: BLE001
            logger.debug("Collection websocket rejection close failed", exc_info=True)
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("Error in collection websocket handler")
        try:
            await websocket.close(code=1011)
        except Exception:
            logger.debug("Collection websocket close failed", exc_info=True)
    finally:
        if connected:
            await broadcast_manager.disconnect(str(collection_id), websocket)
        if auth and not broadcast_manager.has_user_connection(auth.user_id):
            try:
                presence = (
                    db.query(UserPresence).filter(UserPresence.user_id == auth.user_id).first()
                )
                if presence:
                    presence.is_online = False
                    presence.last_seen = datetime.now(UTC)
                    db.commit()
                    await broadcast_manager.publish_event(
                        str(collection_id),
                        "presence_change",
                        {
                            "user_id": str(auth.user_id),
                            "is_online": False,
                            "last_seen": presence.last_seen.isoformat(),
                        },
                    )
            except Exception:
                logger.exception("Error updating presence on disconnect")


@router.get("/{collection_id}/chats", response_model=list[CollectionChatMessage])
def get_collection_chats(
    collection_id: uuid.UUID,
    response: Response,
    limit: int = Query(default=100, ge=1, le=200),
    before: datetime | None = Query(default=None),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[CollectionChatMessage]:
    repo = CollectionsRepository(db)
    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection and collection.expiry_days > 0:
        from datetime import timedelta

        from app.documents.models.collection import (
            CollectionChatMessage as DBCollectionChatMessage,
        )

        cutoff = datetime.now(UTC) - timedelta(days=collection.expiry_days)
        expired_messages = (
            db.query(DBCollectionChatMessage)
            .filter(
                DBCollectionChatMessage.collection_id == collection_id,
                DBCollectionChatMessage.created_at < cutoff,
            )
            .all()
        )
        for message in expired_messages:
            _queue_media_cleanup(
                db=db,
                collection=collection,
                media_id=message.media_id,
                object_key=message.media_object_key,
                owner_user_id=message.user_id,
                bucket=get_settings().minio_bucket,
            )
            db.delete(message)
        db.commit()

    page_limit = max(1, min(limit, 200))
    db_messages = repo.list_chat_messages(
        collection_id=collection_id,
        limit=page_limit + 1,
        before=before,
    )
    has_more = len(db_messages) > page_limit
    if has_more:
        db_messages = db_messages[1:]
        response.headers["X-Chat-Has-More"] = "true"
        response.headers["X-Chat-Next-Cursor"] = db_messages[0][0].created_at.isoformat()
    else:
        response.headers["X-Chat-Has-More"] = "false"
    message_ids = [message.id for message, _email, _avatar in db_messages]
    receipts_by_message: dict[uuid.UUID, list[dict[str, str | None]]] = {}
    if message_ids:
        receipt_rows = (
            db.query(CollectionChatDelivery)
            .filter(
                CollectionChatDelivery.collection_id == collection_id,
                CollectionChatDelivery.message_id.in_(message_ids),
            )
            .all()
        )
        for receipt in receipt_rows:
            receipts_by_message.setdefault(receipt.message_id, []).append(
                {
                    "user_id": str(receipt.user_id),
                    "device_id": receipt.device_id,
                    "status": receipt.status,
                    "delivered_at": (
                        receipt.delivered_at.isoformat() if receipt.delivered_at else None
                    ),
                    "read_at": receipt.read_at.isoformat() if receipt.read_at else None,
                }
            )
    responses: list[CollectionChatMessage] = []
    for msg, email, avatar in db_messages:
        if bool(getattr(msg, "is_encrypted", False)):
            if collection is None:
                raise ApiError(
                    code="CHAT_DECRYPTION_FAILED",
                    message="Stored chat history cannot be opened with the current chat keys.",
                    status_code=500,
                )
            try:
                text = open_chat_message(db, collection=collection, db_message=msg)
            except ChatEncryptionError as exc:
                raise ApiError(
                    code="CHAT_DECRYPTION_FAILED",
                    message="Stored chat history cannot be opened with the current chat keys.",
                    status_code=500,
                ) from exc
        else:
            text = msg.message
        responses.append(
            CollectionChatMessage(
                id=str(msg.id),
                collection_id=str(msg.collection_id),
                user_id=str(msg.user_id),
                user_email=email,
                user_avatar=avatar,
                message=text,
                client_message_id=msg.client_message_id,
                status=msg.status,
                is_media=msg.is_media,
                media_mime_type=msg.media_mime_type,
                media_id=str(msg.media_id) if msg.media_id else None,
                media_object_key=msg.media_object_key,
                reactions=msg.reactions,
                receipts=receipts_by_message.get(msg.id, []),
                is_encrypted=bool(getattr(msg, "is_encrypted", False)),
                crypto_epoch=int(getattr(msg, "crypto_epoch", 0) or 0),
                created_at=msg.created_at.isoformat(),
            )
        )
    return responses


def _chat_message_response(
    *,
    db: Session,
    collection: DocumentCollection,
    db_msg: DBCollectionChatMessage,
    user_email: str,
    user_avatar: str | None = None,
    receipts: list[dict[str, str | None]] | None = None,
) -> CollectionChatMessage:
    """Build the API view of one chat row, unsealing sealed rows for members."""
    if bool(getattr(db_msg, "is_encrypted", False)):
        try:
            text = open_chat_message(db, collection=collection, db_message=db_msg)
        except ChatEncryptionError as exc:
            raise ApiError(
                code="CHAT_DECRYPTION_FAILED",
                message="This message cannot be opened with the current chat keys.",
                status_code=500,
            ) from exc
    else:
        text = db_msg.message
    return CollectionChatMessage(
        id=str(db_msg.id),
        collection_id=str(db_msg.collection_id),
        user_id=str(db_msg.user_id),
        user_email=user_email,
        user_avatar=user_avatar,
        message=text,
        client_message_id=db_msg.client_message_id,
        status=db_msg.status,
        is_media=db_msg.is_media,
        media_mime_type=db_msg.media_mime_type,
        media_id=str(db_msg.media_id) if db_msg.media_id else None,
        media_object_key=db_msg.media_object_key,
        reactions=db_msg.reactions,
        receipts=receipts or [],
        is_encrypted=bool(getattr(db_msg, "is_encrypted", False)),
        crypto_epoch=int(getattr(db_msg, "crypto_epoch", 0) or 0),
        created_at=db_msg.created_at.isoformat(),
    )


def _chat_idempotency_conflict(
    *,
    existing: DBCollectionChatMessage,
    collection: DocumentCollection,
    payload_message: str,
    payload_hash: str | None,
    is_media: bool,
    media_object_key: str | None,
) -> bool:
    """Compare a replayed send against the stored row without leaking plaintext."""
    if bool(getattr(existing, "is_encrypted", False)):
        if payload_hash is None or existing.message_hash != payload_hash:
            return True
    elif existing.message != payload_message:
        return True
    return existing.is_media != is_media or existing.media_object_key != media_object_key


@router.post("/{collection_id}/chats", response_model=CollectionChatMessage)
async def create_collection_chat(
    collection_id: uuid.UUID,
    payload: CreateChatMessage,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> CollectionChatMessage:
    repo = CollectionsRepository(db)
    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND", message="Collection not found.", status_code=404
        )
    if _user_has_collection_block(db, collection_id=collection_id, user_id=auth.user_id):
        raise ApiError(
            code="CHAT_BLOCKED",
            message="Messaging is unavailable because a collection member is blocked.",
            status_code=403,
        )
    settings = get_settings()
    RateLimitService(settings).enforce_counter(
        key=f"rate_limit:collection_chat:{auth.user_id}:{collection_id}",
        limit=settings.collection_ws_messages_per_user_per_minute,
        window_seconds=60,
        scope="collection_chat",
    )
    users_repo = UsersRepository(db)
    user = users_repo.get_by_id_global(auth.user_id)
    user_email = user.email if user else "anonymous@averqel.com"
    user_avatar = user.avatar if user else None

    chat_encrypted = bool(getattr(collection, "chat_encryption_enabled", False))
    payload_hash: str | None = None
    if chat_encrypted:
        from app.documents.services.collection_chat_crypto import (
            plaintext_hash as _plaintext_hash,
        )

        payload_hash = _plaintext_hash(payload.message)

    media_id, media_object_key = _require_complete_media_reference(
        collection=collection,
        is_media=payload.is_media,
        media_id=payload.media_id,
        media_object_key=payload.media_object_key,
    )
    registered_media = _validate_registered_media(
        db=db,
        collection=collection,
        user_id=auth.user_id,
        media_id=media_id,
        object_key=media_object_key,
    )
    if payload.client_message_id:
        existing = (
            db.query(DBCollectionChatMessage)
            .filter(
                DBCollectionChatMessage.collection_id == collection_id,
                DBCollectionChatMessage.user_id == auth.user_id,
                DBCollectionChatMessage.client_message_id == payload.client_message_id,
            )
            .first()
        )
        if existing is not None:
            if _chat_idempotency_conflict(
                existing=existing,
                collection=collection,
                payload_message=payload.message,
                payload_hash=payload_hash,
                is_media=payload.is_media,
                media_object_key=media_object_key,
            ):
                raise ApiError(
                    code="IDEMPOTENCY_CONFLICT",
                    message="This client message ID was already used for different content.",
                    status_code=409,
                )
            return _chat_message_response(
                db=db,
                collection=collection,
                db_msg=existing,
                user_email=user_email,
                user_avatar=user_avatar,
            )

    stored_message = payload.message
    crypto_epoch = 0
    crypto_idx = 0
    message_hash = payload_hash
    if chat_encrypted:
        try:
            sealed = seal_chat_message(
                db,
                collection=collection,
                sender=chat_sender_label(user_id=auth.user_id, device_id=None),
                plaintext=payload.message,
            )
        except ChatEncryptionNotConfiguredError as exc:
            raise ApiError(
                code="CHAT_ENCRYPTION_UNAVAILABLE",
                message="Sealed chat is enabled but encryption is not configured on this deployment.",
                status_code=503,
            ) from exc
        except ChatEncryptionError as exc:
            raise ApiError(
                code="CHAT_ENCRYPTION_FAILED",
                message="The message could not be sealed.",
                status_code=500,
            ) from exc
        stored_message = sealed.envelope
        crypto_epoch = sealed.epoch
        crypto_idx = sealed.idx
        message_hash = sealed.message_hash

    db_msg = DBCollectionChatMessage(
        id=uuid.uuid4(),
        collection_id=collection_id,
        user_id=auth.user_id,
        message=stored_message,
        client_message_id=payload.client_message_id,
        is_media=payload.is_media,
        media_mime_type=payload.media_mime_type,
        media_id=media_id,
        media_object_key=media_object_key,
        is_encrypted=chat_encrypted,
        crypto_epoch=crypto_epoch,
        crypto_idx=crypto_idx,
        message_hash=message_hash,
    )
    try:
        repo.create_chat_message(chat_message=db_msg)
        db.commit()
    except IntegrityError:
        db.rollback()
        if payload.client_message_id is None:
            raise
        existing = (
            db.query(DBCollectionChatMessage)
            .filter(
                DBCollectionChatMessage.collection_id == collection_id,
                DBCollectionChatMessage.user_id == auth.user_id,
                DBCollectionChatMessage.client_message_id == payload.client_message_id,
            )
            .first()
        )
        if existing is None:
            raise
        if _chat_idempotency_conflict(
            existing=existing,
            collection=collection,
            payload_message=payload.message,
            payload_hash=payload_hash,
            is_media=payload.is_media,
            media_object_key=media_object_key,
        ):
            raise ApiError(
                code="IDEMPOTENCY_CONFLICT",
                message="This client message ID was already used for different content.",
                status_code=409,
            ) from None
        db_msg = existing
        return _chat_message_response(
            db=db,
            collection=collection,
            db_msg=existing,
            user_email=user_email,
            user_avatar=user_avatar,
        )

    for permission in repo.get_permissions_global(collection_id=collection_id):
        if permission.user_id != auth.user_id and _is_connected_role(
            getattr(permission, "role", None)
        ):
            for member_device_id in _active_device_ids(
                db, tenant_id=collection.tenant_id, user_id=permission.user_id
            ):
                db.add(
                    CollectionChatDelivery(
                        message_id=db_msg.id,
                        collection_id=collection_id,
                        user_id=permission.user_id,
                        device_id=member_device_id,
                    )
                )
    if registered_media is not None:
        registered_media.status = "attached"
        registered_media.attached_message_id = db_msg.id
    db.commit()

    response = _chat_message_response(
        db=db,
        collection=collection,
        db_msg=db_msg,
        user_email=user_email,
        user_avatar=user.avatar if user else None,
    )

    # Broadcasts never carry plaintext for sealed collections; members fetch
    # the opened message over the authenticated API.
    broadcast_message = "" if response.is_encrypted else response.message
    msg_payload = {
        "id": response.id,
        "collection_id": response.collection_id,
        "user_id": response.user_id,
        "user_email": user_email,
        "user_avatar": user.avatar if user else None,
        "message": broadcast_message,
        "client_message_id": response.client_message_id,
        "status": response.status,
        "is_media": response.is_media,
        "media_mime_type": response.media_mime_type,
        "media_id": response.media_id,
        "media_object_key": response.media_object_key,
        "reactions": response.reactions,
        "is_encrypted": response.is_encrypted,
        "crypto_epoch": response.crypto_epoch,
        "created_at": response.created_at,
    }

    await broadcast_manager.publish_event(str(collection_id), "new_message", msg_payload)

    return response


from fastapi import File, UploadFile  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.system.services.storage_service import StorageService  # noqa: E402


@router.post("/{collection_id}/chats/media")
async def upload_collection_chat_media(
    collection_id: uuid.UUID,
    file: UploadFile = File(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if not collection:
        raise ApiError(code="NOT_FOUND", message="Collection not found")

    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )

    settings = get_settings()
    RateLimitService(settings).enforce_counter(
        key=f"rate_limit:collection_media:{auth.user_id}:{collection_id}",
        limit=settings.rate_limit_upload_per_user_per_5_minutes,
        window_seconds=300,
        scope="collection_media_upload",
    )
    storage = StorageService(settings)
    content_type = (
        (file.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    )
    allowed_types = {item.lower() for item in settings.upload_allowed_mime_types}
    if content_type not in allowed_types:
        raise ApiError(
            code="UNSUPPORTED_MEDIA_TYPE",
            message="This media type is not allowed for collection chat uploads.",
            status_code=415,
            details={"content_type": content_type},
        )
    declared_length = file.headers.get("content-length")
    try:
        declared_size = int(declared_length) if declared_length else None
    except ValueError:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="The media content length is invalid.",
            status_code=422,
        ) from None
    if declared_size is not None and declared_size > settings.upload_max_bytes:
        raise ApiError(
            code="PAYLOAD_TOO_LARGE",
            message="Collection media exceeds the configured upload limit.",
            status_code=413,
        )
    file_bytes = await file.read(settings.upload_max_bytes + 1)
    if len(file_bytes) > settings.upload_max_bytes:
        raise ApiError(
            code="PAYLOAD_TOO_LARGE",
            message="Collection media exceeds the configured upload limit.",
            status_code=413,
        )

    media_id = uuid.uuid4()
    stored_obj = storage.put_bytes(
        tenant_id=collection.tenant_id,
        document_id=media_id,
        filename=file.filename or "media",
        content_type=content_type,
        payload=file_bytes,
    )
    try:
        db.add(
            CollectionChatMedia(
                id=media_id,
                collection_id=collection_id,
                tenant_id=collection.tenant_id,
                uploaded_by_user_id=auth.user_id,
                object_key=stored_obj.object_key,
                bucket=stored_obj.bucket,
                content_type=content_type,
                size_bytes=len(file_bytes),
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _queue_media_cleanup(
            db=db,
            collection=collection,
            media_id=None,
            object_key=stored_obj.object_key,
            owner_user_id=auth.user_id,
            bucket=stored_obj.bucket,
        )
        db.commit()
        raise ApiError(
            code="MEDIA_REGISTRATION_FAILED",
            message="The uploaded media could not be registered safely.",
            status_code=500,
        ) from exc

    return {
        "media_id": str(media_id),
        "filename": file.filename,
        "object_key": stored_obj.object_key,
        "bucket": stored_obj.bucket,
    }


@router.get("/{collection_id}/chats/media/{media_id}/{filename}")
async def download_collection_chat_media(
    collection_id: uuid.UUID,
    media_id: uuid.UUID,
    filename: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if not collection:
        raise ApiError(code="NOT_FOUND", message="Collection not found")

    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )

    settings = get_settings()
    storage = StorageService(settings)

    import re

    safe_fn = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    # Fallback to file if empty
    if not safe_fn:
        safe_fn = "file"
    object_key = f"{collection.tenant_id}/{media_id}/{safe_fn}"

    stream = storage.get_stream(bucket=settings.minio_bucket, object_key=object_key)
    return StreamingResponse(stream, media_type="application/octet-stream")


@router.post("/{collection_id}/chats/clear")
async def clear_collection_chats(
    collection_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if not collection:
        raise ApiError(code="NOT_FOUND", message="Collection not found")

    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )

    from app.documents.models.collection import (
        CollectionChatMessage as DBCollectionChatMessage,
    )

    # Delete messages and enqueue encrypted media objects for durable cleanup.
    messages = (
        db.query(DBCollectionChatMessage)
        .filter(DBCollectionChatMessage.collection_id == collection_id)
        .all()
    )
    settings = get_settings()
    for message in messages:
        _queue_media_cleanup(
            db=db,
            collection=collection,
            media_id=message.media_id,
            object_key=message.media_object_key,
            owner_user_id=message.user_id,
            bucket=settings.minio_bucket,
        )
        db.delete(message)
    # Crypto-shred sealed history: without epoch keys, retained backups of the
    # deleted rows can never be unsealed again.
    shred_chat_epochs(db, collection=collection)
    db.commit()

    # Broadcast clear event to instantly purge active clients' state/cache
    await broadcast_manager.publish_event(str(collection_id), "chat_cleared", {})

    return {"status": "success", "message": "Chat history cleared successfully"}


def _require_collection_owner(
    *, repo: CollectionsRepository, collection_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    role = _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=user_id,
    )
    if _normalize_member_role(role) != "owner":
        raise ApiError(
            code="FORBIDDEN",
            message="Only the collection owner can manage sealed chat.",
            status_code=403,
        )


@router.post("/{collection_id}/chat-encryption/enable")
def enable_sealed_chat(
    collection_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Enable sealed chat (signal-pattern-v1) for a collection. Owner only."""
    from app.documents.services.collection_chat_encryption import (
        enable_encryption as _enable_encryption,
    )

    repo = CollectionsRepository(db)
    _require_collection_owner(repo=repo, collection_id=collection_id, user_id=auth.user_id)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND", message="Collection not found.", status_code=404
        )
    try:
        epoch_row = _enable_encryption(db, collection=collection)
    except ChatEncryptionNotConfiguredError as exc:
        raise ApiError(
            code="CHAT_ENCRYPTION_UNAVAILABLE",
            message="Sealed chat cannot be enabled because encryption is not configured on this deployment.",
            status_code=503,
        ) from exc
    db.commit()
    return {
        "status": "success",
        "chat_encryption_enabled": True,
        "crypto_epoch": epoch_row.epoch,
        "protocol": "signal-pattern-v1",
    }


@router.post("/{collection_id}/chat-encryption/rotate")
def rotate_sealed_chat_epoch(
    collection_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Rotate to a fresh sealed-chat epoch. Owner only. History stays readable."""
    repo = CollectionsRepository(db)
    _require_collection_owner(repo=repo, collection_id=collection_id, user_id=auth.user_id)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND", message="Collection not found.", status_code=404
        )
    if not bool(getattr(collection, "chat_encryption_enabled", False)):
        raise ApiError(
            code="CHAT_ENCRYPTION_DISABLED",
            message="Sealed chat is not enabled for this collection.",
            status_code=409,
        )
    try:
        epoch_row = rotate_chat_epoch(db, collection=collection, reason="manual-rotation")
    except ChatEncryptionNotConfiguredError as exc:
        raise ApiError(
            code="CHAT_ENCRYPTION_UNAVAILABLE",
            message="Sealed chat cannot rotate because encryption is not configured on this deployment.",
            status_code=503,
        ) from exc
    db.commit()
    return {
        "status": "success",
        "crypto_epoch": epoch_row.epoch,
        "protocol": "signal-pattern-v1",
    }


@router.post("/{collection_id}/chat-encryption/device-key")
def register_sealed_chat_device_key(
    collection_id: uuid.UUID,
    payload: dict[str, str],
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Register this member device's X25519 identity key (phase-2 custody)."""
    from app.documents.services.collection_chat_crypto import (
        CollectionChatCryptoError as _ChatCryptoError,
    )
    from app.documents.services.collection_chat_encryption import (
        register_device_key as _register_device_key,
    )

    repo = CollectionsRepository(db)
    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND", message="Collection not found.", status_code=404
        )
    device_id = (payload.get("device_id") or "").strip()
    public_key = (payload.get("public_key") or "").strip()
    if not device_id or len(device_id) > 128:
        raise ApiError(
            code="INVALID_DEVICE_KEY",
            message="device_id must be a non-empty string.",
            status_code=422,
        )
    if not public_key:
        raise ApiError(
            code="INVALID_DEVICE_KEY",
            message="public_key must be a base64 X25519 key.",
            status_code=422,
        )
    try:
        _register_device_key(
            db,
            tenant_id=collection.tenant_id,
            user_id=auth.user_id,
            device_id=device_id,
            public_key_b64=public_key,
        )
    except (ChatEncryptionError, _ChatCryptoError) as exc:
        raise ApiError(
            code="INVALID_DEVICE_KEY",
            message="public_key is not a valid X25519 identity key.",
            status_code=422,
        ) from exc
    db.commit()
    return {"status": "success", "protocol": "signal-pattern-v1"}


@router.get("/{collection_id}/presence")
def get_collection_members_presence(
    collection_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    repo = CollectionsRepository(db)
    _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )

    from app.auth.models.user import User
    from app.documents.models.collection import CollectionPermission

    query = (
        db.query(User.id, User.email, UserPresence.is_online, UserPresence.last_seen)
        .join(CollectionPermission, CollectionPermission.user_id == User.id)
        .outerjoin(UserPresence, UserPresence.user_id == User.id)
        .where(CollectionPermission.collection_id == collection_id)
    )

    results = query.all()

    return [
        {
            "user_id": str(r[0]),
            "email": r[1],
            "is_online": bool(r[2]),
            "last_seen": r[3].isoformat() if r[3] else None,
        }
        for r in results
    ]


@router.put("/{collection_id}/expiry", response_model=DocumentCollectionResponse)
async def update_collection_expiry(
    collection_id: uuid.UUID,
    payload: UpdateExpiryPayload,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DocumentCollectionResponse:
    repo = CollectionsRepository(db)
    role = _enforce_collection_access_global(
        repo=repo,
        collection_id=collection_id,
        user_id=auth.user_id,
    )
    if _normalize_member_role(role) != "owner":
        raise ApiError(
            code="FORBIDDEN",
            message="Only the bridge owner can update self-destruct timers.",
            status_code=403,
        )

    collection = repo.get_by_id_global(collection_id=collection_id)
    if not collection:
        raise ApiError(
            code="COLLECTION_NOT_FOUND",
            message="Collection not found.",
            status_code=404,
        )

    collection.expiry_days = payload.expiry_days
    StorageLifecycleService(db).touch_source(
        tenant_id=collection.tenant_id,
        category="collections",
        source_type="collection",
        source_id=str(collection.id),
        dependency_group_id=str(collection.id),
        activity_kind="collection_expiry_updated",
    )
    db.commit()

    await broadcast_manager.publish_event(
        str(collection_id), "expiry_updated", {"expiry_days": payload.expiry_days}
    )

    member_count = repo.count_connected_members_global(collection_id=collection_id)
    return _collection_response(
        collection=collection,
        requester_access_role=role,
        member_count=member_count,
    )
