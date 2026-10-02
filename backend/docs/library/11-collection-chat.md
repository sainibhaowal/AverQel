# 11. Collection chat contract

**Status:** available locally. Collection chat is the real-time,
permission-aware conversation surface inside a collection, separate from
DeepSpace agent runs and grounded queries.

## 1. Two encryption layers

**Client-side end-to-end encryption (default).** The dashboard collections
client derives a symmetric AES-GCM-256 key in the browser with PBKDF2-SHA-256
(100,000 iterations) from the collection id and connection code, using
WebCrypto. Text messages and file attachments are sealed client-side; the
server stores and relays ciphertext envelopes it cannot open. Members confirm
matching safety numbers to verify devices, recent history is cached in
IndexedDB, and chat backups are encrypted with a password-derived key and a
random 16-byte salt.

**Server-side sealed epochs (opt-in).** Collections can additionally enable
`signal-pattern-v1` sealed chat: per-epoch keys wrapped under the server chat
keyring, per-message keys derived and never stored, rotation on membership
change and block/unblock, and crypto-shredding on clear. See
[`10-collection-chat-encryption.md`](10-collection-chat-encryption.md). The
two layers compose: enabling sealed epochs never weakens the client-side
envelope.

## 2. Message routes (`/api/v1/collections/{id}/chats`)

- `GET` history with cursor pagination (`limit`, `before`, `X-Chat-Has-More`
  / `X-Chat-Next-Cursor`), per-message delivery receipts, and expiry pruning:
  messages older than the collection `expiry_days` are deleted with their
  media cleanup queued.
- `POST` send with `client_message_id` idempotency: replays return the stored
  message, conflicting reuses fail with `IDEMPOTENCY_CONFLICT` (hash-compared
  for sealed rows, so retries never leak plaintext).
- `POST /chats/media` registers an encrypted upload; `GET
  /chats/media/{media_id}/{filename}` serves it to members.
- `POST /chats/clear` (owner) deletes history, queues media cleanup,
  shreds sealed epochs, and broadcasts `chat_cleared` so live clients purge.
- Broadcasts never carry plaintext for sealed collections; members fetch
  opened text over the authenticated API.

## 3. Presence and realtime

- `GET /{id}/ws-ticket` mints a scoped ticket; `websocket /{id}/ws` streams
  collection events over Redis pub/sub with replay and heartbeat.
- `GET /{id}/presence` lists online members. Delivery receipts track
  per-member, per-device state without exposing message content.

## 4. Membership, moderation, and notifications

- Invites are explicit and owner-controlled (`permissions`, `invitations`,
  accept/decline); every grant, removal, and block advances the membership
  epoch and notifies remaining members.
- Members can block abusive peers and file reports with an optional message
  reference; admins triage reports (`open`/`reviewing`/`resolved`/
  `dismissed`) with moderation notes. A per-member spam score combines
  recent reports and message volume.
- Collection notifications (security changes, invites, device links) carry
  idempotency keys with read/read-all/delete lifecycle.
- Browser push subscriptions store WebPush secrets encrypted at rest; fanout
  runs through the collection push worker.

## 5. Expiry and retention

`PUT /{id}/expiry` sets `expiry_days` (owner). Expired chat rows are pruned
on history reads with media cleanup queued, and sealed epochs for cleared
history are shredded so retained backups stay unreadable. Collection deletion
cascades to messages, media records, epochs, deliveries, and permissions.

## 6. What must not change

1. The server must never require or persist plaintext for default
   collections; sealed rows must fail closed, never silently skipped.
2. Membership changes must keep advancing the security epoch and rotating
   sealed epochs when enabled.
3. Moderation (blocks, reports, spam scores) stays available without
   breaking the encryption envelopes.
4. Broadcasts stay metadata-only for sealed collections.

## 7. Verification

Integration coverage exercises idempotent send, conflicting-retry rejection,
sealed enable/send/read/rotate/clear-shred, tamper-closed reads, device-key
registration, rotation guards, expiry pruning, and tenant isolation.
Frontend coverage renders the encrypted chat client, safety numbers,
media flows, receipts, and expiry controls.
