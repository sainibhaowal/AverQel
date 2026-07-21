from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.errors import ApiError
from app.auth.rbac import require_permissions
from app.auth.tenancy import require_request_tenant_id
from app.db.session import get_db
from app.documents.models.collection import DocumentCollection, UserPresence
from app.documents.models.collection_notification import CollectionNotification
from app.documents.models.document import Document
from app.auth.repositories.users import UsersRepository
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
from app.documents.schemas.documents import DocumentMetadataResponse
from app.documents.schemas.collection_chat import CollectionChatMessage, CreateChatMessage
from app.documents.schemas.collection_expiry import UpdateExpiryPayload
from app.ingestion.services.extraction_quality import confidence_band

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
        requester_access_role="member",
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
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[CollectionNotificationResponse]:
    repo = CollectionNotificationsRepository(db)
    items = repo.list_for_user(user_id=auth.user_id, limit=30)
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
    deleted = repo.delete_for_user(
        user_id=auth.user_id, notification_id=notification_id
    )
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

        await broadcast_manager.publish_event(
            str(collection_id),
            "document_sync",
            {"action": "add", "document_ids": [str(d) for d in payload.document_ids]}
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to add documents to collection.",
            status_code=500,
        ) from exc

    return Response(status_code=204)


@router.get(
    "/{collection_id}/documents",
    response_model=list[DocumentMetadataResponse],
    dependencies=[Depends(require_permissions("collections:read"))],
)
def list_collection_documents(
    collection_id: uuid.UUID,
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

    return [
        _document_metadata_response(item)
        for item in repo.list_documents_for_user(
            collection_id=collection_id,
            user_id=auth.user_id,
        )
    ]


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

        await broadcast_manager.publish_event(
            str(collection_id),
            "document_sync",
            {"action": "remove", "document_ids": [str(d) for d in payload.document_ids]}
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to remove documents from collection.",
            status_code=500,
        ) from exc

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
    from app.documents.models.collection import CollectionPermission as DBCollectionPermission
    user_collections = db.query(DBCollectionPermission.collection_id).filter(
        DBCollectionPermission.user_id == auth.user_id
    ).all()
    user_col_ids = [c[0] for c in user_collections]

    if user_col_ids:
        duplicate_conn = db.query(DBCollectionPermission.collection_id).filter(
            DBCollectionPermission.collection_id.in_(user_col_ids),
            DBCollectionPermission.user_id == target_user.id
        ).first()
        if duplicate_conn:
            col_id = duplicate_conn[0]
            existing_col = repo.get_by_id_global(collection_id=col_id)
            if existing_col and existing_col.description and "1:1 Connection" in existing_col.description:
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
        if payload.user_ids and any(
            user_id != auth.user_id for user_id in payload.user_ids
        ):
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
                for permission in repo.get_permissions_global(
                    collection_id=collection_id
                ):
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
        else:
            repo.remove_permissions(
                tenant_id=collection.tenant_id,
                collection_id=collection_id,
                user_ids=[auth.user_id],
            )
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
    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}
        self.redis_tasks: dict[str, asyncio.Task] = {}
        # Delayed client init until get_settings is available
        self._redis_client = None

    @property
    def redis_client(self):
        if self._redis_client is None:
            from app.core.config import get_settings
            self._redis_client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        return self._redis_client

    async def connect(self, collection_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if collection_id not in self.active_connections:
            self.active_connections[collection_id] = set()
            task = asyncio.create_task(self._redis_subscribe_loop(collection_id))
            self.redis_tasks[collection_id] = task
        self.active_connections[collection_id].add(websocket)

    async def disconnect(self, collection_id: str, websocket: WebSocket) -> None:
        if collection_id in self.active_connections:
            self.active_connections[collection_id].discard(websocket)
            if not self.active_connections[collection_id]:
                del self.active_connections[collection_id]
                task = self.redis_tasks.pop(collection_id, None)
                if task:
                    task.cancel()

    async def publish_event(self, collection_id: str, event_type: str, data: dict) -> None:
        payload = json.dumps({"type": event_type, "data": data})
        await self.redis_client.publish(f"collection_room:{collection_id}", payload)

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

from app.api.v1.deepspace_chats import _authenticate_websocket_auth_context  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402


@router.websocket("/{collection_id}/ws")
async def collection_websocket(
    websocket: WebSocket,
    collection_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    await broadcast_manager.connect(str(collection_id), websocket)
    auth = None
    try:
        auth = await _authenticate_websocket_auth_context(
            websocket, db=db, settings=settings
        )

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
            }
        )

        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                continue

            action = data.get("action")
            db.rollback() # Refresh long-lived session transaction to read fresh database state
            if action == "post_message":
                content = str(data.get("content", "")).strip()
                if not content:
                    continue
                is_media = bool(data.get("is_media", False))
                media_mime_type = data.get("media_mime_type")

                users_repo = UsersRepository(db)
                user = users_repo.get_by_id_global(auth.user_id)
                user_email = user.email if user else "anonymous@averqel.com"
                user_avatar = user.avatar if user else None

                from app.documents.models.collection import (
                    CollectionChatMessage as DBCollectionChatMessage,
                )

                db_msg = DBCollectionChatMessage(
                    id=uuid.uuid4(),
                    collection_id=collection_id,
                    user_id=auth.user_id,
                    message=content,
                    is_media=is_media,
                    media_mime_type=media_mime_type,
                    status="sent",
                )
                repo.create_chat_message(chat_message=db_msg)
                db.commit()

                msg_payload = {
                    "id": str(db_msg.id),
                    "collection_id": str(db_msg.collection_id),
                    "user_id": str(db_msg.user_id),
                    "user_email": user_email,
                    "user_avatar": user_avatar,
                    "message": db_msg.message,
                    "status": db_msg.status,
                    "is_media": db_msg.is_media,
                    "media_mime_type": db_msg.media_mime_type,
                    "reactions": db_msg.reactions,
                    "created_at": db_msg.created_at.isoformat()
                }

                await broadcast_manager.publish_event(
                    str(collection_id), "new_message", msg_payload
                )
            elif action == "typing":
                is_typing = bool(data.get("is_typing", False))
                await broadcast_manager.publish_event(
                    str(collection_id),
                    "user_typing",
                    {
                        "user_id": str(auth.user_id),
                        "is_typing": is_typing
                    }
                )
            elif action == "react":
                msg_id = data.get("message_id")
                reaction = data.get("reaction")
                if msg_id and reaction:
                    from app.documents.models.collection import (
                        CollectionChatMessage as DBCollectionChatMessage,
                    )
                    db_msg = db.query(DBCollectionChatMessage).filter(DBCollectionChatMessage.id == uuid.UUID(msg_id)).first()
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
                                "reactions": db_msg.reactions
                            }
                        )
            elif action == "delivered":
                msg_id = data.get("message_id")
                if msg_id:
                    from app.documents.models.collection import (
                        CollectionChatMessage as DBCollectionChatMessage,
                    )
                    db_msg = db.query(DBCollectionChatMessage).filter(DBCollectionChatMessage.id == uuid.UUID(msg_id)).first()
                    if db_msg and db_msg.status == "sent":
                        db_msg.status = "delivered"
                        db.commit()
                        await broadcast_manager.publish_event(
                            str(collection_id),
                            "message_delivered",
                            {
                                "message_id": str(db_msg.id),
                                "status": "delivered"
                            }
                        )
            elif action == "delete":
                msg_id = data.get("message_id")
                if msg_id:
                    from app.documents.models.collection import (
                        CollectionChatMessage as DBCollectionChatMessage,
                    )
                    db_msg = db.query(DBCollectionChatMessage).filter(
                        DBCollectionChatMessage.id == uuid.UUID(msg_id)
                    ).first()
                    # Senders or collection owners can delete
                    permission = repo.get_user_permission_global(
                        collection_id=collection_id,
                        user_id=auth.user_id,
                    )
                    role = str(getattr(permission, "role", "")) if permission else ""
                    is_owner = role == "owner"
                    if db_msg and (db_msg.user_id == auth.user_id or is_owner):
                        db_msg.message = "This message was deleted"
                        db_msg.is_media = False
                        db_msg.media_mime_type = None
                        db_msg.reactions = "{}"
                        db.commit()
                        await broadcast_manager.publish_event(
                            str(collection_id),
                            "message_deleted",
                            {
                                "message_id": str(msg_id),
                                "message": "This message was deleted"
                            }
                        )
            elif action == "read":
                from app.documents.models.collection import (
                    CollectionChatMessage as DBCollectionChatMessage,
                )
                unread_msgs = (
                    db.query(DBCollectionChatMessage)
                    .filter(
                        DBCollectionChatMessage.collection_id == collection_id,
                        DBCollectionChatMessage.user_id != auth.user_id,
                        DBCollectionChatMessage.status != "read"
                    )
                    .all()
                )
                if unread_msgs:
                    for m in unread_msgs:
                        m.status = "read"
                    db.commit()
                    await broadcast_manager.publish_event(
                        str(collection_id),
                        "messages_read",
                        {
                            "reader_id": str(auth.user_id),
                            "status": "read"
                        }
                    )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Error in collection websocket handler")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if auth:
            try:
                presence = db.query(UserPresence).filter(UserPresence.user_id == auth.user_id).first()
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
                        }
                    )
            except Exception:
                logger.exception("Error updating presence on disconnect")
        await broadcast_manager.disconnect(str(collection_id), websocket)

@router.get("/{collection_id}/chats", response_model=list[CollectionChatMessage])
def get_collection_chats(
    collection_id: uuid.UUID,
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

        from app.documents.models.collection import CollectionChatMessage as DBCollectionChatMessage
        cutoff = datetime.now(UTC) - timedelta(days=collection.expiry_days)
        db.query(DBCollectionChatMessage).filter(
            DBCollectionChatMessage.collection_id == collection_id,
            DBCollectionChatMessage.created_at < cutoff
        ).delete(synchronize_session=False)
        db.commit()

    db_messages = repo.list_chat_messages(collection_id=collection_id)
    return [
        CollectionChatMessage(
            id=str(msg.id),
            collection_id=str(msg.collection_id),
            user_id=str(msg.user_id),
            user_email=email,
            user_avatar=avatar,
            message=msg.message,
            status=msg.status,
            is_media=msg.is_media,
            media_mime_type=msg.media_mime_type,
            reactions=msg.reactions,
            created_at=msg.created_at.isoformat()
        )
        for msg, email, avatar in db_messages
    ]

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
    users_repo = UsersRepository(db)
    user = users_repo.get_by_id_global(auth.user_id)
    user_email = user.email if user else "anonymous@averqel.com"

    from app.documents.models.collection import CollectionChatMessage as DBCollectionChatMessage

    db_msg = DBCollectionChatMessage(
        id=uuid.uuid4(),
        collection_id=collection_id,
        user_id=auth.user_id,
        message=payload.message,
        is_media=payload.is_media,
        media_mime_type=payload.media_mime_type,
    )
    repo.create_chat_message(chat_message=db_msg)
    db.commit()

    msg_payload = {
        "id": str(db_msg.id),
        "collection_id": str(db_msg.collection_id),
        "user_id": str(db_msg.user_id),
        "user_email": user_email,
        "user_avatar": user.avatar if user else None,
        "message": db_msg.message,
        "status": db_msg.status,
        "is_media": db_msg.is_media,
        "media_mime_type": db_msg.media_mime_type,
        "reactions": db_msg.reactions,
        "created_at": db_msg.created_at.isoformat()
    }

    await broadcast_manager.publish_event(
        str(collection_id), "new_message", msg_payload
    )

    return CollectionChatMessage(**msg_payload)


from fastapi import File, UploadFile  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.system.storage_service import StorageService  # noqa: E402


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
    storage = StorageService(settings)
    file_bytes = await file.read()

    media_id = uuid.uuid4()
    stored_obj = storage.put_bytes(
        tenant_id=collection.tenant_id,
        document_id=media_id,
        filename=file.filename or "media",
        content_type=file.content_type or "application/octet-stream",
        payload=file_bytes,
    )

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

    from app.documents.models.collection import CollectionChatMessage as DBCollectionChatMessage

    # Delete all E2EE messages
    db.query(DBCollectionChatMessage).filter(DBCollectionChatMessage.collection_id == collection_id).delete()
    db.commit()

    # Broadcast clear event to instantly purge active clients' state/cache
    await broadcast_manager.publish_event(
        str(collection_id),
        "chat_cleared",
        {}
    )

    return {"status": "success", "message": "Chat history cleared successfully"}

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
            "last_seen": r[3].isoformat() if r[3] else None
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
    db.commit()

    await broadcast_manager.publish_event(
        str(collection_id),
        "expiry_updated",
        {
            "expiry_days": payload.expiry_days
        }
    )

    member_count = repo.count_connected_members_global(collection_id=collection_id)
    return _collection_response(
        collection=collection,
        requester_access_role=role,
        member_count=member_count,
    )
