# 10. Sealed collection chat (signal-pattern-v1)

**Status:** implemented in this worktree (backend). Plaintext remains the
default; sealing is opt-in per collection.

## What it is

Collection text messages can be sealed so the database, backups, logs, and
WebSocket broadcasts never carry plaintext. The construction mirrors Signal's
sender-key/epoch pattern using the already-audited `cryptography` library
(X25519, HKDF-SHA256, AES-256-GCM). No new crypto dependency was added.

* Per message: fresh random 256-bit message key derived from the live epoch
  key via HKDF (`info = averqel-chat-v1 | msg | sender | idx`). Message keys
  are used once and never persisted — per-message forward secrecy.
* Binding: AES-GCM associated data pins
  `collection_id | epoch | sender | idx`, so cross-collection replay,
  reordering, and sender confusion fail closed.
* Epochs: random 256-bit epoch keys wrapped under the server chat keyring
  (`AKS_COLLECTION_CHAT_ACTIVE_KID` / `AKS_COLLECTION_CHAT_KEYRING_JSON`,
  32-byte keys). Membership changes (grant, revoke, block, unblock) and
  manual rotation cut a fresh epoch, bounding any single key's exposure.
* Crypto-shredding: deleting epoch keys renders that epoch's messages
  permanently unsealable. Chat clear and expiry deletion shred keys, so
  retained backups of deleted rows stay unreadable.
* Idempotency without plaintext: sealed rows store `message_hash`
  (SHA-256) so `client_message_id` retries compare hashes, never content.

## Custody model (phase 1 vs phase 2)

Phase 1 (this worktree) is server-mediated: the API derives message keys
and unseals rows for authorized members over the existing authenticated
API. This protects data at rest, backups, logs, and ex-member reads after
rotation — it does not protect against a live compromised server.

Phase 2 moves derivation into clients holding X25519 private keys. Ready
today: per-device identity registry (`collection_devices.identity_public_key`,
`protocol_version = signal-pattern-v1`), device-key endpoints, and envelopes
that already carry `epoch / sender / idx`. No schema or wire change needed.

## Operating rules

* Enabling without the keyring pair fails closed (`503
  CHAT_ENCRYPTION_UNAVAILABLE`); tampered or orphaned rows fail closed
  (`500 CHAT_DECRYPTION_FAILED`), never silently skipped.
* Broadcasts for sealed collections carry metadata only; members fetch
  opened text via `GET /chats`.
* Media bytes stay under existing server-side access control; only the text
  body is sealed. Server-side plaintext moderation/search does not apply to
  sealed rows — reports, blocks, and member moderation remain available.
* Owner-only: enable, rotate. Any member: send, read, register device key.

## Verification

* `tests/unit/test_collection_chat_crypto.py` — 14 tests: roundtrip,
  randomization, tamper/AAD binding, epoch isolation, wrap/unwrap, hash,
  input validation.
* `tests/integration/test_collection_chat_encryption.py` — 4 tests:
  enable→send→ciphertext-at-rest→read→replay→conflict→rotate→clear-shred,
  tamper-closed, device keys, rotate guard.
* Migration `20261012_0008` is additive with a single head; the
  `(collection, epoch, idx)` uniqueness is a *partial* index over sealed
  rows only, so legacy plaintext history migrates untouched.
