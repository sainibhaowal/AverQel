"""Authenticated device, moderation, and notification controls for collections."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
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
    CollectionModerationReportResponse,
    CollectionPushSubscriptionRequest,
    CollectionReportRequest,
    CollectionReportStatusUpdate,
)
from app.integrations.services.connector_secret_crypto import (
    ConnectorSecretCrypto,
    ConnectorSecretCryptoError,
)
from app.platform.database.session import get_db, set_db_tenant_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/collections", tags=["collection-security"])


def _rotate_sealed_chat_epoch(db: Session, *, collection: DocumentCollection, reason: str) -> None:
    """Rotate the sealed-chat epoch when encryption is enabled (no-op otherwise)."""
    if not bool(getattr(collection, "chat_encryption_enabled", False)):
        return
    from app.documents.services.collection_chat_encryption import (
        ChatEncryptionNotConfiguredError,
        rotate_epoch,
    )

    try:
        rotate_epoch(db, collection=collection, reason=reason)
    except ChatEncryptionNotConfiguredError:
        logger.warning(
            "Skipping sealed-chat rotation for collection %s: chat keyring is not configured",
            collection.id,
        )


@router.get(
    "/security/push-config", dependencies=[Depends(require_permissions("collections:read"))]
)
def get_push_config() -> dict[str, str | bool | None]:
    """Expose only the public VAPID key; private delivery credentials stay server-side."""
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "enabled": bool(
            settings.web_push_vapid_private_key
            and settings.web_push_vapid_public_key
            and settings.web_push_subject
        ),
        "public_key": settings.web_push_vapid_public_key,
    }


@router.get(
    "/admin/security/reports",
    response_model=list[CollectionModerationReportResponse],
    dependencies=[Depends(require_permissions("admin:collections:read"))],
)
def list_moderation_reports(
    status: str | None = Query(
        default="open", pattern=r"^(open|reviewing|resolved|dismissed|all)$"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[CollectionModerationReportResponse]:
    query = db.query(CollectionChatReport).filter(CollectionChatReport.tenant_id == auth.tenant_id)
    if status != "all":
        query = query.filter(CollectionChatReport.status == status)
    rows = (
        query.order_by(CollectionChatReport.created_at.desc(), CollectionChatReport.id.desc())
        .limit(limit)
        .all()
    )
    return [CollectionModerationReportResponse.model_validate(row) for row in rows]


@router.post(
    "/admin/security/reports/{report_id}",
    response_model=CollectionModerationReportResponse,
    dependencies=[Depends(require_permissions("admin:collections:write"))],
)
def update_moderation_report(
    report_id: uuid.UUID,
    payload: CollectionReportStatusUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> CollectionModerationReportResponse:
    row = (
        db.query(CollectionChatReport)
        .filter(
            CollectionChatReport.id == report_id, CollectionChatReport.tenant_id == auth.tenant_id
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="REPORT_NOT_FOUND", message="Moderation report not found.", status_code=404
        )
    row.status = payload.status
    row.resolved_at = datetime.now(UTC) if payload.status in {"resolved", "dismissed"} else None
    if payload.moderator_note:
        row.details = f"{row.details or ''}\nModerator: {payload.moderator_note}".strip()[:4000]
    db.commit()
    db.refresh(row)
    return CollectionModerationReportResponse.model_validate(row)


@router.get(
    "/{collection_id}/security/spam-score/{user_id}",
    dependencies=[Depends(require_permissions("admin:collections:read"))],
)
def collection_member_spam_score(
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    collection = _collection(db, collection_id, auth)
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    reports = (
        db.query(func.count(CollectionChatReport.id))
        .filter(
            CollectionChatReport.tenant_id == auth.tenant_id,
            CollectionChatReport.collection_id == collection.id,
            CollectionChatReport.reported_user_id == user_id,
            CollectionChatReport.created_at >= cutoff,
            CollectionChatReport.status.in_(("open", "reviewing")),
        )
        .scalar()
        or 0
    )
    messages = (
        db.query(func.count(CollectionChatMessage.id))
        .filter(
            CollectionChatMessage.collection_id == collection.id,
            CollectionChatMessage.user_id == user_id,
            CollectionChatMessage.created_at >= cutoff,
        )
        .scalar()
        or 0
    )
    score = min(100, int(reports) * 25 + max(0, int(messages) - 100) // 5)
    return {
        "user_id": str(user_id),
        "score": score,
        "reports_24h": int(reports),
        "messages_24h": int(messages),
    }


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
    if payload.protocol_version not in {"legacy-shared-key", "signal-pattern-v1"}:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Unsupported collection protocol version.",
            status_code=422,
        )
    if payload.protocol_version == "signal-pattern-v1":
        if not payload.identity_public_key:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="signal-pattern-v1 devices must register an X25519 identity public key.",
                status_code=422,
            )
        from app.documents.services.collection_chat_crypto import (
            validate_device_public_key,
        )

        try:
            validate_device_public_key(payload.identity_public_key)
        except Exception as exc:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="identity_public_key is not a valid X25519 key.",
                status_code=422,
            ) from exc
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
        _rotate_sealed_chat_epoch(db, collection=collection, reason="member-blocked")
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
        _rotate_sealed_chat_epoch(db, collection=collection, reason="member-unblocked")
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
