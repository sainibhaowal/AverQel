"""Pure unit tests for the signal-pattern-v1 chat crypto primitives.

No database, no settings, no network: only the construction in
``app.documents.services.collection_chat_crypto``.
"""

import base64

import pytest

from app.documents.services.collection_chat_crypto import (
    CollectionChatCryptoError,
    derive_message_key,
    epoch_aad,
    generate_device_keypair,
    generate_epoch_key,
    open_message,
    plaintext_hash,
    seal_message,
    unwrap_epoch_key,
    validate_device_public_key,
    wrap_epoch_key,
)


def _seal(*, key: bytes, sender: str = "user-1:default", idx: int = 1):
    return seal_message(
        epoch_key=key,
        collection_id="collection-1",
        epoch=1,
        sender=sender,
        idx=idx,
        plaintext="hello sealed world",
    )


def test_device_keypair_roundtrip_validates() -> None:
    keypair = generate_device_keypair()

    raw = validate_device_public_key(keypair.public_key_b64)

    assert len(raw) == 32
    assert keypair.private_key_b64 != keypair.public_key_b64
    assert generate_device_keypair().public_key_b64 != keypair.public_key_b64


def test_device_key_validation_rejects_garbage() -> None:
    with pytest.raises(CollectionChatCryptoError):
        validate_device_public_key("not-base64!!!")
    with pytest.raises(CollectionChatCryptoError):
        validate_device_public_key(base64.b64encode(b"short").decode("ascii"))


def test_seal_open_roundtrip() -> None:
    key = generate_epoch_key()
    sealed = _seal(key=key)

    opened = open_message(
        epoch_key=key,
        collection_id="collection-1",
        epoch=1,
        sender="user-1:default",
        idx=1,
        sealed=sealed,
    )

    assert opened == "hello sealed world"


def test_seal_is_randomized_per_message() -> None:
    key = generate_epoch_key()

    first = _seal(key=key)
    second = _seal(key=key)

    assert first.ciphertext_b64 != second.ciphertext_b64
    assert first.nonce_b64 != second.nonce_b64


def test_tampered_ciphertext_fails_closed() -> None:
    key = generate_epoch_key()
    sealed = _seal(key=key)
    raw = bytearray(base64.b64decode(sealed.ciphertext_b64))
    raw[0] ^= 0x01
    tampered = type(sealed)(
        nonce_b64=sealed.nonce_b64,
        ciphertext_b64=base64.b64encode(bytes(raw)).decode("ascii"),
    )

    with pytest.raises(CollectionChatCryptoError):
        open_message(
            epoch_key=key,
            collection_id="collection-1",
            epoch=1,
            sender="user-1:default",
            idx=1,
            sealed=tampered,
        )


@pytest.mark.parametrize(
    "field",
    ["collection_id", "epoch", "sender", "idx"],
)
def test_binding_mismatch_fails_closed(field: str) -> None:
    key = generate_epoch_key()
    sealed = _seal(key=key)
    kwargs: dict[str, object] = {
        "epoch_key": key,
        "collection_id": "collection-1",
        "epoch": 1,
        "sender": "user-1:default",
        "idx": 1,
        "sealed": sealed,
    }
    kwargs[field] = (
        "other-collection"
        if field == "collection_id"
        else (2 if field in {"epoch", "idx"} else "user-2:default")
    )

    with pytest.raises(CollectionChatCryptoError):
        open_message(**kwargs)  # type: ignore[arg-type]


def test_epochs_are_isolated() -> None:
    first_key = generate_epoch_key()
    second_key = generate_epoch_key()
    sealed = _seal(key=first_key)

    with pytest.raises(CollectionChatCryptoError):
        open_message(
            epoch_key=second_key,
            collection_id="collection-1",
            epoch=1,
            sender="user-1:default",
            idx=1,
            sealed=sealed,
        )


def test_message_key_derivation_is_deterministic_per_position() -> None:
    key = generate_epoch_key()

    assert derive_message_key(epoch_key=key, sender="a", idx=1) == derive_message_key(
        epoch_key=key, sender="a", idx=1
    )
    assert derive_message_key(epoch_key=key, sender="a", idx=1) != derive_message_key(
        epoch_key=key, sender="a", idx=2
    )
    assert derive_message_key(epoch_key=key, sender="a", idx=1) != derive_message_key(
        epoch_key=key, sender="b", idx=1
    )


def test_epoch_key_wrap_roundtrip_and_wrong_key_fails() -> None:
    keyring_key = generate_epoch_key()
    epoch_key = generate_epoch_key()
    aad = epoch_aad(collection_id="collection-1", epoch=3)

    nonce, blob = wrap_epoch_key(keyring_key=keyring_key, epoch_key=epoch_key, aad=aad)

    assert unwrap_epoch_key(keyring_key=keyring_key, nonce=nonce, blob=blob, aad=aad) == epoch_key
    with pytest.raises(CollectionChatCryptoError):
        unwrap_epoch_key(keyring_key=generate_epoch_key(), nonce=nonce, blob=blob, aad=aad)
    with pytest.raises(CollectionChatCryptoError):
        unwrap_epoch_key(
            keyring_key=keyring_key,
            nonce=nonce,
            blob=blob,
            aad=epoch_aad(collection_id="collection-1", epoch=4),
        )


def test_plaintext_hash_is_stable_and_content_bound() -> None:
    assert plaintext_hash("same") == plaintext_hash("same")
    assert plaintext_hash("same") != plaintext_hash("different")
    assert len(plaintext_hash("x")) == 64


def test_seal_rejects_empty_and_oversize_plaintext() -> None:
    key = generate_epoch_key()
    with pytest.raises(CollectionChatCryptoError):
        seal_message(
            epoch_key=key,
            collection_id="c",
            epoch=1,
            sender="s",
            idx=1,
            plaintext="",
        )
    with pytest.raises(CollectionChatCryptoError):
        seal_message(
            epoch_key=key,
            collection_id="c",
            epoch=1,
            sender="s",
            idx=1,
            plaintext="x" * 4097,
        )
