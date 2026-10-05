# Collection chat encryption: implemented custody boundaries

**Audience:** engineers, security reviewers, and deployment operators. This is
an implementation note, not a cryptographic certification or a promise that a
hosted deployment has enabled every mode.

## Summary

The current collection chat implementation has two distinct encryption
mechanisms. Neither should be marketed as zero-knowledge or as audited
Signal/libsignal end-to-end encryption.

1. The browser client uses Web Crypto AES-GCM for chat payloads and media. It
   derives a key from the collection ID and connection code with PBKDF2-SHA256
   (100,000 iterations). The collection API returns the connection code to
   authorized collection clients. Therefore, the server possesses the inputs
   needed to derive this key; the current design does not establish a
   server-blind key boundary.
2. An optional backend sealed-chat mode stores a sealed message envelope at
   rest. The API server derives message keys from server-held epoch keys and
   opens messages for authorized members. This protects selected storage,
   backup, log, and broadcast paths as implemented, but not against a
   compromised or malicious live server with the required keyring.

Collection documents remain server-readable for storage, malware scanning,
preview, OCR, indexing, and retrieval. Do not generalize chat encryption to
shared documents.

## Browser client mechanism

`frontend/lib/crypto.ts` implements AES-GCM message and file encryption,
password-derived backup encryption, and a deterministic safety fingerprint.
The collection detail client also caches chat state locally. The connection
code is returned by the collection API, so these features must not be described
as protection from server access. A safety fingerprint is not a verified
identity-key protocol and does not authenticate a member against active
interception. Local cache cleanup does not revoke copies, screenshots, browser
backups, or data already obtained by a recipient.

## Optional backend sealed-chat mode

`backend/app/documents/services/collection_chat_encryption.py` documents the
actual custody model: the API wraps epoch keys with a configured server
keyring, seals messages at rest, and opens them for authorized members. The
API can read the plaintext during this workflow. Enabling the mode requires a
valid active key ID and 32-byte keyring entry; it fails closed when the
deployment lacks the required keyring. Do not label its protocol
`signal-pattern-v1` in user-facing security claims.

Membership and manual rotation create new epochs where the relevant code path
calls rotation. Retired epoch keys are kept to preserve readable history;
deleting them can make corresponding rows unreadable. This means the former
claims of per-message forward secrecy, automatic crypto-shredding on expiry,
and unreadable retained backups were not accurate for the current service and
have been removed.

## Media, expiry, and retention

Media uses the client encryption helper, but the server has the derivation
inputs and controls the authenticated media routes. Owner-configured chat
expiry is enforced during the implemented history lifecycle and queues related
media cleanup. It is not proof of immediate erasure from every backup, device,
export, or recipient copy. Chat clear removes accessible history through its
API workflow; operators should not promise backup erasure unless a separate
backup retention process has been verified.

## Security review and future work

Before making stronger end-to-end claims, design and independently review a
client-held key protocol: private keys must not be recoverable from API data;
membership changes, device enrollment, key distribution, revocation, backup,
recovery, replay protection, and multi-device behavior need explicit threat
modeling and tests. A protocol name or use of AES-GCM is not itself evidence of
secure end-to-end encryption.

## Source map

- Browser helpers: `frontend/lib/crypto.ts`.
- Collection DTO and connection-code response: `backend/app/documents/api/collections.py`.
- Optional server-mediated sealed-chat orchestration:
  `backend/app/documents/services/collection_chat_encryption.py`.
- API routes, access checks, and expiry/clear workflows:
  `backend/app/documents/api/collections.py`.
- Collection member-facing guide: `11-collection-chat.md`.
