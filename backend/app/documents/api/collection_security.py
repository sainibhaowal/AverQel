"""Authenticated device, moderation, and notification controls for collections."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.errors import ApiError
from app.documents.api.collections import _enforce_collection_access_global
from app.documents.models.collection import CollectionChatMessage, DocumentCollection
from app.documents.models.collection_notification import CollectionNotification
from app.documents.models.collection_security import (
    CollectionChatBlock,
    CollectionChatReport,
    CollectionDevice,
    CollectionPushSubscription,
)
from app.documents.repositories.collection_notifications import CollectionNotificationsRepository
from app.documents.repositories.collections import CollectionsRepository
from app.documents.schemas.collection_security import (
    CollectionBlockRequest,
    CollectionDeviceResponse,
    CollectionDeviceUpsert,
    CollectionPushSubscriptionRequest,
    CollectionReportRequest,
)
from app.integrations.services.connector_secret_crypto import (
    ConnectorSecretCrypto,
    ConnectorSecretCryptoError,
)
from app.platform.database.session import get_db, set_db_tenant_context

router = APIRouter(prefix="/collections", tags=["collection-security"])


def _collection(db: Session, collection_id: uuid.UUID, auth: AuthContext) -> DocumentCollection:
    repo = CollectionsRepository(db)
    collection = repo.get_by_id_global(collection_id=collection_id)
    if collection is None:
        raise ApiError(
            code="COLLECTION_NOT_FOUND", message="Collection not found.", status_code=404
        )
    _enforce_collection_access_global(repo=repo, collection_id=collection_id, user_id=auth.user_id)
    return collection


def _notify_self(
    db: Session, *, auth: AuthContext, collection: DocumentCollection, event_type: str, message: str
) -> None:
    CollectionNotificationsRepository(db).create(
        CollectionNotification(
            recipient_user_id=auth.user_id,
            actor_user_id=auth.user_id,
            collection_id=collection.id,
            collection_name=collection.name,
            event_type=event_type,
            message=message,
            idempotency_key=f"{event_type}:{auth.user_id}:{collection.id}:{datetime.now(UTC).date().isoformat()}",
        )
    )


@router.get(
    "/security/devices",
    response_model=list[CollectionDeviceResponse],
    dependencies=[Depends(require_permissions("collections:read"))],
)
def list_collection_devices(
    auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> list[CollectionDeviceResponse]:
    rows = (
        db.query(CollectionDevice)
        .filter(
            CollectionDevice.tenant_id == auth.tenant_id, CollectionDevice.user_id == auth.user_id
        )
        .order_by(CollectionDevice.last_seen_at.desc())
        .all()
    )
    return [CollectionDeviceResponse.model_validate(row) for row in rows]


@router.post(
    "/security/devices",
    response_model=CollectionDeviceResponse,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def register_collection_device(
    payload: CollectionDeviceUpsert,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> CollectionDeviceResponse:
    if payload.protocol_version != "legacy-shared-key":
        raise ApiError(
            code="VALIDATION_ERROR",
            message="This deployment only supports the explicitly labelled legacy collection protocol.",
            status_code=422,
        )
    created = False
    row = (
        db.query(CollectionDevice)
        .filter(
            CollectionDevice.tenant_id == auth.tenant_id,
            CollectionDevice.user_id == auth.user_id,
            CollectionDevice.device_id == payload.device_id,
        )
        .first()
    )
    if row is None:
        row = CollectionDevice(
            tenant_id=auth.tenant_id, user_id=auth.user_id, device_id=payload.device_id
        )
        db.add(row)
        created = True
    row.label = payload.label
    row.identity_public_key = payload.identity_public_key
    row.protocol_version = payload.protocol_version
    row.revoked_at = None
    row.last_seen_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    if created:
        CollectionNotificationsRepository(db).create(
            CollectionNotification(
                recipient_user_id=auth.user_id,
                actor_user_id=auth.user_id,
                collection_id=None,
                collection_name="Account Security",
                event_type="device_registered",
                message=f"A new {row.label} device was linked to your account.",
                idempotency_key=f"device-registered:{row.id}",
            )
        )
        db.commit()
    return CollectionDeviceResponse.model_validate(row)


@router.delete(
    "/security/devices/{device_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def revoke_collection_device(
    device_id: str, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> Response:
    row = (
        db.query(CollectionDevice)
        .filter(
            CollectionDevice.tenant_id == auth.tenant_id,
            CollectionDevice.user_id == auth.user_id,
            CollectionDevice.device_id == device_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(code="DEVICE_NOT_FOUND", message="Device not found.", status_code=404)
    row.revoked_at = datetime.now(UTC)
    db.commit()
    CollectionNotificationsRepository(db).create(
        CollectionNotification(
            recipient_user_id=auth.user_id,
            actor_user_id=auth.user_id,
            collection_id=None,
            collection_name="Account Security",
            event_type="device_revoked",
            message=f"The {row.label} device was revoked.",
            idempotency_key=f"device-revoked:{row.id}:{row.revoked_at.isoformat()}",
        )
    )
    db.commit()
    return Response(status_code=204)


@router.post(
    "/{collection_id}/security/blocks",
    status_code=201,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def block_collection_member(
    collection_id: uuid.UUID,
    payload: CollectionBlockRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    collection = _collection(db, collection_id, auth)
    if payload.user_id == auth.user_id:
        raise ApiError(
            code="VALIDATION_ERROR", message="You cannot block yourself.", status_code=422
        )
    repo = CollectionsRepository(db)
    _enforce_collection_access_global(
        repo=repo, collection_id=collection_id, user_id=payload.user_id
    )
    set_db_tenant_context(db, "bypass")
    row = (
        db.query(CollectionChatBlock)
        .filter(
            CollectionChatBlock.collection_id == collection_id,
            CollectionChatBlock.blocker_user_id == auth.user_id,
            CollectionChatBlock.blocked_user_id == payload.user_id,
        )
        .first()
    )
    if row is None:
        db.add(
            CollectionChatBlock(
                tenant_id=collection.tenant_id,
                collection_id=collection_id,
                blocker_user_id=auth.user_id,
                blocked_user_id=payload.user_id,
                reason=payload.reason,
            )
        )
        db.commit()
    return {"status": "blocked"}


@router.delete(
    "/{collection_id}/security/blocks/{user_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def unblock_collection_member(
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    collection = _collection(db, collection_id, auth)
    set_db_tenant_context(db, "bypass")
    row = (
        db.query(CollectionChatBlock)
        .filter(
            CollectionChatBlock.collection_id == collection.id,
            CollectionChatBlock.blocker_user_id == auth.user_id,
            CollectionChatBlock.blocked_user_id == user_id,
        )
        .first()
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


@router.post(
    "/{collection_id}/security/reports",
    status_code=201,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def report_collection_member(
    collection_id: uuid.UUID,
    payload: CollectionReportRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    collection = _collection(db, collection_id, auth)
    repo = CollectionsRepository(db)
    if payload.reported_user_id is not None:
        _enforce_collection_access_global(
            repo=repo, collection_id=collection_id, user_id=payload.reported_user_id
        )
    if payload.message_id is not None:
        message = (
            db.query(CollectionChatMessage)
            .filter(
                CollectionChatMessage.id == payload.message_id,
                CollectionChatMessage.collection_id == collection_id,
            )
            .first()
        )
        if message is None:
            raise ApiError(
                code="MESSAGE_NOT_FOUND",
                message="Message not found in this collection.",
                status_code=404,
            )
        if payload.reported_user_id is not None and message.user_id != payload.reported_user_id:
            raise ApiError(
                code="REPORT_TARGET_MISMATCH",
                message="The reported user does not own this message.",
                status_code=422,
            )
    set_db_tenant_context(db, "bypass")
    db.add(
        CollectionChatReport(
            tenant_id=collection.tenant_id,
            collection_id=collection_id,
            reporter_user_id=auth.user_id,
            reported_user_id=payload.reported_user_id,
            message_id=payload.message_id,
            reason=payload.reason,
            details=payload.details,
        )
    )
    db.commit()
    return {"status": "reported"}


@router.post(
    "/security/push-subscriptions",
    status_code=201,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def register_push_subscription(
    payload: CollectionPushSubscriptionRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not payload.endpoint.startswith("https://"):
        raise ApiError(
            code="VALIDATION_ERROR", message="Push endpoints must use HTTPS.", status_code=422
        )
    try:
        encrypted = ConnectorSecretCrypto().encrypt(
            payload.auth, aad=f"collection-push:{auth.tenant_id}:{auth.user_id}".encode()
        )
    except ConnectorSecretCryptoError as exc:
        raise ApiError(
            code="PUSH_NOT_CONFIGURED",
            message="Push secret encryption is not configured on this deployment.",
            status_code=503,
        ) from exc
    row = (
        db.query(CollectionPushSubscription)
        .filter(
            CollectionPushSubscription.tenant_id == auth.tenant_id,
            CollectionPushSubscription.user_id == auth.user_id,
            CollectionPushSubscription.endpoint == payload.endpoint,
        )
        .first()
    )
    if row is None:
        row = CollectionPushSubscription(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            device_id=payload.device_id,
            endpoint=payload.endpoint,
            p256dh=payload.p256dh,
            auth_ciphertext=encrypted.ciphertext,
            auth_nonce=encrypted.nonce,
            auth_kid=encrypted.kid,
        )
        db.add(row)
    else:
        row.device_id = payload.device_id
        row.p256dh = payload.p256dh
        row.auth_ciphertext, row.auth_nonce, row.auth_kid = (
            encrypted.ciphertext,
            encrypted.nonce,
            encrypted.kid,
        )
        row.active = True
        row.failure_count = 0
    db.commit()
    return {"status": "registered"}


@router.delete(
    "/security/push-subscriptions",
    status_code=204,
    dependencies=[Depends(require_permissions("collections:write"))],
)
def remove_push_subscription(
    endpoint: str, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> Response:
    row = (
        db.query(CollectionPushSubscription)
        .filter(
            CollectionPushSubscription.tenant_id == auth.tenant_id,
            CollectionPushSubscription.user_id == auth.user_id,
            CollectionPushSubscription.endpoint == endpoint,
        )
        .first()
    )
    if row is not None:
        row.active = False
        db.commit()
    return Response(status_code=204)
