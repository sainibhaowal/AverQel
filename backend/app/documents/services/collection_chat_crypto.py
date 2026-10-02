"""Signal-pattern sealed chat crypto for collection messages.

Pure cryptographic primitives with no database or settings dependencies so the
construction stays unit-testable in isolation. The orchestration layer
(:mod:`app.documents.services.collection_chat_encryption`) owns key custody,
epochs, and persistence.

Construction (``signal-pattern-v1``):

* Every message is sealed with a fresh random 256-bit message key under
  AES-GCM. The associated data binds ``collection_id | epoch | sender | idx``,
  so ciphertext cannot be replayed or reordered across collections, epochs,
  senders, or positions without detection.
* The message key is derived deterministically from the epoch key with
  HKDF-SHA256 (``info = averqel-chat-v1 | msg | sender | idx``). Message keys
  are never persisted in any form, which gives per-message forward secrecy:
  deleting an epoch key cryptographically shreds every message sealed under
  that epoch.
* Epoch keys are random 256-bit values wrapped (AES-GCM) under a server-side
  keyring key identified by ``kid``. A membership change (grant, revoke,
  block) rotates to a fresh epoch, bounding the blast radius of any single
  epoch-key exposure.
* Per-device X25519 identity keys are registered on
  :class:`CollectionDevice`. Phase 1 keeps message-key derivation
  server-mediated so the current web client works unchanged; the envelope
  already carries ``epoch / sender / idx`` so a future phase can move
  derivation into clients holding private keys without changing the wire
  format or the stored rows.

What this is NOT: transport still requires TLS, and a live compromised
server performing derivations remains in scope for phase 2 client custody.
The guarantees provided today are ciphertext at rest (database, backups,
and logs never see plaintext), epoch-bounded exposure, tamper-evident
ordering, and crypto-shredding on chat clear/expiry via epoch-key deletion.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PROTOCOL_VERSION = "signal-pattern-v1"
ENVELOPE_VERSION = 1
KEY_BYTES = 32
NONCE_BYTES = 12
_MAX_PLAINTEXT_BYTES = 4096


class CollectionChatCryptoError(RuntimeError):
    """Raised when chat key handling, sealing, or unsealing fails."""


@dataclass(frozen=True, slots=True)
class DeviceKeypair:
    """Base64-encoded X25519 identity keypair for one user device."""

    private_key_b64: str
    public_key_b64: str


@dataclass(frozen=True, slots=True)
class SealedChatBody:
    """Wire/storage form of one sealed message (never contains plaintext)."""

    nonce_b64: str
    ciphertext_b64: str


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str, *, what: str, expected_len: int | None = None) -> bytes:
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise CollectionChatCryptoError(f"chat {what} is not valid base64") from exc
    if expected_len is not None and len(raw) != expected_len:
        raise CollectionChatCryptoError(
            f"chat {what} must decode to {expected_len} bytes, got {len(raw)}"
        )
    return raw


def generate_device_keypair() -> DeviceKeypair:
    """Generate a fresh X25519 identity keypair for one user device."""
    private_key = X25519PrivateKey.generate()
    return DeviceKeypair(
        private_key_b64=_b64encode(
            private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        ),
        public_key_b64=_b64encode(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ),
    )


def validate_device_public_key(public_key_b64: str) -> bytes:
    """Validate a registered device public key; returns the raw 32 bytes."""
    raw = _b64decode(public_key_b64, what="device public key", expected_len=KEY_BYTES)
    try:
        X25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise CollectionChatCryptoError("chat device public key is not a valid X25519 key") from exc
    return raw


def generate_epoch_key() -> bytes:
    """Generate a fresh random 256-bit epoch key."""
    return os.urandom(KEY_BYTES)


def derive_message_key(*, epoch_key: bytes, sender: str, idx: int) -> bytes:
    """Derive the per-message key for ``(epoch_key, sender, idx)``.

    The derivation is deterministic so any holder of the epoch key can unseal
    history, while the derived message key itself is used once and discarded.
    """
    if len(epoch_key) != KEY_BYTES:
        raise CollectionChatCryptoError("chat epoch key must be 32 bytes")
    if not sender or len(sender) > 256:
        raise CollectionChatCryptoError("chat sender must be a non-empty string")
    if idx < 0:
        raise CollectionChatCryptoError("chat message index must be non-negative")
    info = f"averqel-chat-v1|msg|{sender}|{idx}".encode()
    return HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=None,
        info=info,
    ).derive(epoch_key)


def _aad(*, collection_id: str, epoch: int, sender: str, idx: int) -> bytes:
    if epoch < 0:
        raise CollectionChatCryptoError("chat epoch must be non-negative")
    return f"averqel-chat-v1|{collection_id}|{epoch}|{sender}|{idx}".encode()


def seal_message(
    *,
    epoch_key: bytes,
    collection_id: str,
    epoch: int,
    sender: str,
    idx: int,
    plaintext: str,
) -> SealedChatBody:
    """Seal one plaintext message; returns only ciphertext material."""
    plaintext_bytes = plaintext.encode("utf-8")
    if not plaintext_bytes or len(plaintext_bytes) > _MAX_PLAINTEXT_BYTES:
        raise CollectionChatCryptoError("chat plaintext must be 1..4096 bytes")
    message_key = derive_message_key(epoch_key=epoch_key, sender=sender, idx=idx)
    nonce = os.urandom(NONCE_BYTES)
    # message_key is a short-lived local, used once and never stored.
    ciphertext = AESGCM(message_key).encrypt(
        nonce,
        plaintext_bytes,
        _aad(collection_id=collection_id, epoch=epoch, sender=sender, idx=idx),
    )
    return SealedChatBody(nonce_b64=_b64encode(nonce), ciphertext_b64=_b64encode(ciphertext))


def open_message(
    *,
    epoch_key: bytes,
    collection_id: str,
    epoch: int,
    sender: str,
    idx: int,
    sealed: SealedChatBody,
) -> str:
    """Unseal one message; raises closed on any tamper or mismatch."""
    message_key = derive_message_key(epoch_key=epoch_key, sender=sender, idx=idx)
    try:
        plaintext_bytes = AESGCM(message_key).decrypt(
            _b64decode(sealed.nonce_b64, what="nonce", expected_len=NONCE_BYTES),
            _b64decode(sealed.ciphertext_b64, what="ciphertext"),
            _aad(collection_id=collection_id, epoch=epoch, sender=sender, idx=idx),
        )
    except InvalidTag as exc:
        raise CollectionChatCryptoError("chat message failed authentication") from exc
    try:
        return plaintext_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CollectionChatCryptoError("chat plaintext is not valid UTF-8") from exc


def plaintext_hash(plaintext: str) -> str:
    """SHA-256 hex of the plaintext for idempotency without storing content."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def wrap_epoch_key(*, keyring_key: bytes, epoch_key: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Wrap an epoch key under a server keyring key; returns (nonce, blob)."""
    if len(keyring_key) not in {16, 24, 32}:
        raise CollectionChatCryptoError("chat keyring key must be 16, 24, or 32 bytes")
    if len(epoch_key) != KEY_BYTES:
        raise CollectionChatCryptoError("chat epoch key must be 32 bytes")
    nonce = os.urandom(NONCE_BYTES)
    return nonce, AESGCM(keyring_key).encrypt(nonce, epoch_key, aad)


def unwrap_epoch_key(*, keyring_key: bytes, nonce: bytes, blob: bytes, aad: bytes) -> bytes:
    """Unwrap an epoch key; raises closed when the kid/key is wrong."""
    try:
        return AESGCM(keyring_key).decrypt(nonce, blob, aad)
    except InvalidTag as exc:
        raise CollectionChatCryptoError("chat epoch key failed authentication") from exc


def epoch_aad(*, collection_id: str, epoch: int) -> bytes:
    """AAD binding a wrapped epoch key to exactly one collection epoch."""
    return f"averqel-chat-v1|epoch-key|{collection_id}|{epoch}".encode()
