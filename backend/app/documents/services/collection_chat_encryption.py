"""Server-mediated orchestration for sealed collection chat.

Phase-1 custody model: the API server derives per-message keys from per-epoch
keys and unseals messages for authorized members over the existing
authenticated API. The database, backups, logs, and broadcasts never carry
plaintext for encrypted collections. Phase 2 (client-held X25519 private
keys) reuses the same envelope columns and headers; only derivation moves.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.documents.models.collection import (
    CollectionChatEpoch,
    CollectionChatMessage,
    DocumentCollection,
)
from app.documents.models.collection_security import CollectionDevice
from app.documents.services.collection_chat_crypto import (
    PROTOCOL_VERSION,
    CollectionChatCryptoError,
    SealedChatBody,
    epoch_aad,
    generate_epoch_key,
    open_message,
    plaintext_hash,
    seal_message,
    unwrap_epoch_key,
    validate_device_public_key,
    wrap_epoch_key,
)


class ChatEncryptionError(RuntimeError):
    """Raised when sealed-chat orchestration cannot proceed safely."""


class ChatEncryptionNotConfiguredError(ChatEncryptionError):
    """The deployment has no chat keyring; enabling fails closed."""


@dataclass(frozen=True, slots=True)
class SealedMessage:
    envelope: str
    epoch: int
    idx: int
    message_hash: str


def _parse_keyring(settings: Settings) -> dict[str, bytes]:
    raw = (settings.collection_chat_keyring_json or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChatEncryptionError("collection chat keyring is not valid JSON") from exc
    keyring: dict[str, bytes] = {}
    for kid, encoded in payload.items():
        try:
            keyring[kid] = base64.urlsafe_b64decode(encoded.encode("utf-8"))
        except Exception as exc:
            raise ChatEncryptionError(
                f"collection chat key for kid={kid!r} is not valid base64"
            ) from exc
    return keyring


def _active_keyring_key(settings: Settings) -> tuple[str, bytes]:
    keyring = _parse_keyring(settings)
    kid = (settings.collection_chat_active_kid or "").strip()
    if not kid or kid not in keyring:
        raise ChatEncryptionNotConfiguredError(
            "Collection chat encryption is not configured on this deployment."
        )
    key = keyring[kid]
    if len(key) != 32:
        raise ChatEncryptionError("collection chat keyring keys must decode to 32 bytes")
    return kid, key


def _latest_epoch(db: Session, *, collection_id: uuid.UUID) -> CollectionChatEpoch | None:
    return (
        db.query(CollectionChatEpoch)
        .filter(CollectionChatEpoch.collection_id == collection_id)
        .order_by(CollectionChatEpoch.epoch.desc())
        .first()
    )


def _unwrap_epoch(
    settings: Settings, *, collection_id: uuid.UUID, row: CollectionChatEpoch
) -> bytes:
    keyring = _parse_keyring(settings)
    key = keyring.get(row.key_kid)
    if key is None:
        raise ChatEncryptionError(
            "The key required to open this chat epoch is not available on this deployment."
        )
    return unwrap_epoch_key(
        keyring_key=key,
        nonce=row.key_nonce,
        blob=row.wrapped_key,
        aad=epoch_aad(collection_id=str(collection_id), epoch=row.epoch),
    )


def ensure_epoch(
    db: Session,
    *,
    collection: DocumentCollection,
    reason: str,
    settings: Settings | None = None,
) -> CollectionChatEpoch:
    """Return the latest epoch, creating epoch 1 when none exists."""
    existing = _latest_epoch(db, collection_id=collection.id)
    if existing is not None:
        return existing
    return rotate_epoch(db, collection=collection, reason=reason, settings=settings)


def rotate_epoch(
    db: Session,
    *,
    collection: DocumentCollection,
    reason: str,
    settings: Settings | None = None,
) -> CollectionChatEpoch:
    """Rotate to a fresh epoch key (membership change, manual rotation).

    Retired epoch rows are kept so history sealed under them stays readable
    to current members. Deleting epoch rows crypto-shreds that epoch; see
    :func:`shred_epochs`.
    """
    resolved = settings or get_settings()
    kid, keyring_key = _active_keyring_key(resolved)
    latest = _latest_epoch(db, collection_id=collection.id)
    next_epoch = int(latest.epoch) + 1 if latest is not None else 1
    epoch_key = generate_epoch_key()
    nonce, blob = wrap_epoch_key(
        keyring_key=keyring_key,
        epoch_key=epoch_key,
        aad=epoch_aad(collection_id=str(collection.id), epoch=next_epoch),
    )
    row = CollectionChatEpoch(
        id=uuid.uuid4(),
        collection_id=collection.id,
        epoch=next_epoch,
        wrapped_key=blob,
        key_nonce=nonce,
        key_kid=kid,
        reason=reason[:64],
    )
    db.add(row)
    db.flush()
    return row


def enable_encryption(
    db: Session,
    *,
    collection: DocumentCollection,
    settings: Settings | None = None,
) -> CollectionChatEpoch:
    """Enable sealed chat for a collection and create its first epoch."""
    resolved = settings or get_settings()
    _active_keyring_key(resolved)  # fail closed before flipping the flag
    collection.chat_encryption_enabled = True
    db.flush()
    return ensure_epoch(db, collection=collection, reason="enabled", settings=resolved)


def seal_for_send(
    db: Session,
    *,
    collection: DocumentCollection,
    sender: str,
    plaintext: str,
    settings: Settings | None = None,
) -> SealedMessage:
    """Seal one outgoing plaintext message under the collection's live epoch."""
    resolved = settings or get_settings()
    _active_keyring_key(resolved)
    epoch_row = ensure_epoch(db, collection=collection, reason="enabled", settings=resolved)
    epoch_key = _unwrap_epoch(resolved, collection_id=collection.id, row=epoch_row)
    max_idx = (
        db.query(CollectionChatMessage.crypto_idx)
        .filter(
            CollectionChatMessage.collection_id == collection.id,
            CollectionChatMessage.crypto_epoch == epoch_row.epoch,
        )
        .order_by(CollectionChatMessage.crypto_idx.desc())
        .first()
    )
    idx = int(max_idx[0]) + 1 if max_idx is not None else 1
    sealed = seal_message(
        epoch_key=epoch_key,
        collection_id=str(collection.id),
        epoch=epoch_row.epoch,
        sender=sender,
        idx=idx,
        plaintext=plaintext,
    )
    envelope = json.dumps(
        {
            "v": 1,
            "epoch": epoch_row.epoch,
            "sender": sender,
            "idx": idx,
            "nonce": sealed.nonce_b64,
            "ct": sealed.ciphertext_b64,
            "kid": epoch_row.key_kid,
        },
        separators=(",", ":"),
    )
    return SealedMessage(
        envelope=envelope,
        epoch=epoch_row.epoch,
        idx=idx,
        message_hash=plaintext_hash(plaintext),
    )


def open_for_read(
    db: Session,
    *,
    collection: DocumentCollection,
    db_message: CollectionChatMessage,
    settings: Settings | None = None,
) -> str:
    """Unseal one stored message for an authorized member. Fails closed."""
    if not db_message.is_encrypted:
        return db_message.message
    resolved = settings or get_settings()
    try:
        envelope = json.loads(db_message.message)
        sealed = SealedChatBody(nonce_b64=envelope["nonce"], ciphertext_b64=envelope["ct"])
        epoch_no = int(envelope["epoch"])
        sender = str(envelope["sender"])
        idx = int(envelope["idx"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ChatEncryptionError("Stored chat message envelope is malformed.") from exc
    epoch_row = (
        db.query(CollectionChatEpoch)
        .filter(
            CollectionChatEpoch.collection_id == collection.id,
            CollectionChatEpoch.epoch == epoch_no,
        )
        .first()
    )
    if epoch_row is None:
        raise ChatEncryptionError("The chat epoch for this message is no longer available.")
    epoch_key = _unwrap_epoch(resolved, collection_id=collection.id, row=epoch_row)
    try:
        return open_message(
            epoch_key=epoch_key,
            collection_id=str(collection.id),
            epoch=epoch_no,
            sender=sender,
            idx=idx,
            sealed=sealed,
        )
    except CollectionChatCryptoError as exc:
        raise ChatEncryptionError("Stored chat message failed authentication.") from exc


def shred_epochs(db: Session, *, collection: DocumentCollection) -> int:
    """Delete all epoch keys, rendering sealed history unsealable. Returns rows."""
    rows = (
        db.query(CollectionChatEpoch)
        .filter(CollectionChatEpoch.collection_id == collection.id)
        .all()
    )
    for row in rows:
        db.delete(row)
    db.flush()
    return len(rows)


def register_device_key(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    device_id: str,
    public_key_b64: str,
) -> CollectionDevice:
    """Register (or rotate) a device X25519 identity key for phase-2 custody."""
    validate_device_public_key(public_key_b64)
    device = (
        db.query(CollectionDevice)
        .filter(
            CollectionDevice.tenant_id == tenant_id,
            CollectionDevice.user_id == user_id,
            CollectionDevice.device_id == device_id,
        )
        .first()
    )
    if device is None:
        device = CollectionDevice(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            device_id=device_id,
        )
        db.add(device)
    device.identity_public_key = public_key_b64
    device.protocol_version = PROTOCOL_VERSION
    device.revoked_at = None
    db.flush()
    return device


def sender_label(*, user_id: uuid.UUID, device_id: str | None) -> str:
    """Stable sender label bound into message AAD."""
    return f"{user_id}:{device_id or 'default'}"
