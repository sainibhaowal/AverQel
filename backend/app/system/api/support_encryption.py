from __future__ import annotations

import base64
import binascii
import hashlib
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.auth.tenancy import TenantContext, get_tenant_context
from app.platform.database.session import get_db, set_db_tenant_context
from app.system.api.admin import require_platform_admin_access
from app.system.models.support_encryption_key import SupportEncryptionKey
from app.system.schemas.support_encryption import (
    SupportKeyRegistration,
    SupportPrivateKeyResponse,
    SupportPublicKeyResponse,
)
from app.system.services.audit_service import AuditService

router = APIRouter(prefix="/support/encryption", tags=["support-encryption"])


def _check_registration(payload: SupportKeyRegistration) -> None:
    try:
        public_key_bytes = base64.b64decode(payload.public_key, validate=True)
        salt = base64.b64decode(payload.salt, validate=True)
        iv = base64.b64decode(payload.iv, validate=True)
        private_key = base64.b64decode(payload.private_key_ciphertext, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="Invalid encrypted key material") from exc
    if hashlib.sha256(public_key_bytes).hexdigest() != payload.key_id:
        raise HTTPException(status_code=422, detail="Key fingerprint does not match public key")
    if len(salt) != 16 or len(iv) != 12 or len(private_key) < 32:
        raise HTTPException(status_code=422, detail="Encrypted key material has invalid lengths")
    try:
        public_key = serialization.load_der_public_key(public_key_bytes)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Public key is not valid DER") from exc
    if not isinstance(public_key, RSAPublicKey) or public_key.key_size != 3072:
        raise HTTPException(status_code=422, detail="Support keys must be RSA-3072 public keys")
    if public_key.public_numbers().e != 65537:
        raise HTTPException(status_code=422, detail="Support RSA public key exponent is invalid")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"


def _private_response(row: SupportEncryptionKey) -> SupportPrivateKeyResponse:
    return SupportPrivateKeyResponse(
        key_id=row.key_id,
        public_key=row.public_key,
        private_key_ciphertext=row.private_key_ciphertext,
        salt=row.salt,
        iv=row.iv,
    )


@router.get("/admin-public-key", response_model=SupportPublicKeyResponse)
def get_platform_admin_public_key(
    response: Response,
    _auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> SupportPublicKeyResponse:
    _no_store(response)
    # Public key material is intentionally available to authenticated users in every tenant.
    set_db_tenant_context(db, "bypass")
    row = db.execute(
        select(SupportEncryptionKey)
        .where(SupportEncryptionKey.scope == "platform_admin")
        .order_by(SupportEncryptionKey.created_at)
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=503, detail="Support encryption is not initialized")
    return SupportPublicKeyResponse(key_id=row.key_id, public_key=row.public_key)


@router.get("/me", response_model=SupportPrivateKeyResponse)
def get_my_encryption_key(
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> SupportPrivateKeyResponse:
    _no_store(response)
    row = db.execute(
        select(SupportEncryptionKey).where(
            SupportEncryptionKey.user_id == auth.user_id,
            SupportEncryptionKey.tenant_id == tenant.tenant_id,
            SupportEncryptionKey.scope == "user",
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Support encryption key is not set up")
    return _private_response(row)


@router.put("/me", response_model=SupportPublicKeyResponse)
def save_my_encryption_key(
    response: Response,
    payload: SupportKeyRegistration,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> SupportPublicKeyResponse:
    _no_store(response)
    _check_registration(payload)
    row = db.execute(
        select(SupportEncryptionKey).where(
            SupportEncryptionKey.user_id == auth.user_id,
            SupportEncryptionKey.tenant_id == tenant.tenant_id,
            SupportEncryptionKey.scope == "user",
        )
    ).scalar_one_or_none()
    if row is not None:
        if row.key_id != payload.key_id:
            raise HTTPException(
                status_code=409,
                detail="A support key already exists for this account; key replacement requires recovery.",
            )
        return SupportPublicKeyResponse(key_id=row.key_id, public_key=row.public_key)
    row = SupportEncryptionKey(
        tenant_id=tenant.tenant_id,
        user_id=auth.user_id,
        scope="user",
        key_id=payload.key_id,
        public_key=payload.public_key,
        private_key_ciphertext=payload.private_key_ciphertext,
        salt=payload.salt,
        iv=payload.iv,
    )
    db.add(row)
    db.flush()
    AuditService(db).write_event(
        tenant_id=tenant.tenant_id,
        actor_user_id=auth.user_id,
        action="support.encryption_key.create",
        resource_type="support_encryption_key",
        resource_id=str(row.id),
    )
    db.commit()
    return SupportPublicKeyResponse(key_id=row.key_id, public_key=row.public_key)


@router.get(
    "/admin-private-key",
    response_model=SupportPrivateKeyResponse,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def get_platform_admin_private_key_backup(
    response: Response,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> SupportPrivateKeyResponse:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    row = db.execute(
        select(SupportEncryptionKey).where(SupportEncryptionKey.scope == "platform_admin")
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Support encryption key is not set up")
    if row.user_id != auth.user_id:
        raise HTTPException(status_code=403, detail="This encryption key belongs to another admin")
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.encryption_key.read",
        resource_type="support_encryption_key",
        resource_id=str(row.id),
    )
    return _private_response(row)


@router.put(
    "/admin-private-key",
    response_model=SupportPublicKeyResponse,
    dependencies=[Depends(require_permissions("admin:support:write"))],
)
def create_platform_admin_encryption_key(
    response: Response,
    payload: SupportKeyRegistration,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> SupportPublicKeyResponse:
    _no_store(response)
    _check_registration(payload)
    set_db_tenant_context(db, "bypass")
    existing = db.execute(
        select(SupportEncryptionKey).where(SupportEncryptionKey.scope == "platform_admin")
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id != auth.user_id:
            raise HTTPException(
                status_code=409,
                detail="The platform support encryption key is owned by another administrator.",
            )
        if existing.key_id != payload.key_id:
            raise HTTPException(
                status_code=409,
                detail="A platform support key already exists; key replacement requires recovery.",
            )
        return SupportPublicKeyResponse(key_id=existing.key_id, public_key=existing.public_key)
    row = SupportEncryptionKey(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        scope="platform_admin",
        key_id=payload.key_id,
        public_key=payload.public_key,
        private_key_ciphertext=payload.private_key_ciphertext,
        salt=payload.salt,
        iv=payload.iv,
    )
    db.add(row)
    db.flush()
    AuditService(db).write_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.encryption_key.create",
        resource_type="support_encryption_key",
        resource_id=str(row.id),
    )
    db.commit()
    return SupportPublicKeyResponse(key_id=row.key_id, public_key=row.public_key)


@router.get(
    "/users/{user_id}/public-key",
    response_model=SupportPublicKeyResponse,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def get_user_public_key_for_admin(
    response: Response,
    user_id: uuid.UUID,
    _auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> SupportPublicKeyResponse:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    row = db.execute(
        select(SupportEncryptionKey).where(
            SupportEncryptionKey.user_id == user_id,
            SupportEncryptionKey.scope == "user",
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=409, detail="The user has not initialized support encryption"
        )
    return SupportPublicKeyResponse(key_id=row.key_id, public_key=row.public_key)
