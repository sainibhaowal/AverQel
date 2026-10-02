# 12. Collection rooms: connect, chat, and share

**Status:** available locally; experimental beta. Collections are small,
permission-aware rooms where approved people chat, exchange files, and share
documents without opening an entire workspace. This document describes the
member-facing contract; the message encryption construction lives in
[`10-collection-chat-encryption.md`](10-collection-chat-encryption.md) and
the route-by-route chat contract in
[`11-collection-chat.md`](11-collection-chat.md).

## 1. Connect with an ID

- Every user owns a collection code (their collection ID), visible and
  copyable from the collections surface.
- To connect, a user sends the other person's code as a join request.
  Owners can also invite directly. The other side accepts or declines; both
  directions stay explicit — there is no silent joining.
- Roles are `owner`, `member`/`shared`, and `pending`. Only owners invite,
  clear history, change expiry, and enable sealed chat. A room caps at ten
  connected members, and one pending invite at a time.

## 2. Chat like a messenger

- **Text, emoji, and reactions.** Messages support full Unicode (including
  emoji). Any message can carry one emoji reaction per member, toggled on
  and off, shown as badges with a floating reaction bar.
- **Typing indicators.** While a member types, the room broadcasts
  `user_typing` over the collection WebSocket (throttled to one signal per
  1.5 seconds, with an explicit stop), so the other side sees live typing.
- **Green ticks.** Each message carries delivery state per member device:
  sent, delivered (grey double tick), and read (emerald double tick). The
  sender's client reports `delivered` on receipt, and opening the room marks
  messages read. State never rolls backward from read.
- **Pictures and files.** Members attach photos and files as encrypted
  collection media (client-side sealed before upload); recipients preview
  and download from inside the room. Text captions travel with the media
  message.
- **History controls.** Cursor pagination, per-message receipts, owner
  chat-clear (with media cleanup queued and sealed epochs shredded), and
  per-collection expiry that prunes old messages automatically.

## 3. Share documents once

- A document is added to a collection **by reference**, never duplicated:
  members read the same controlled copy, and grounded queries stay
  permission-aware — a member can use a shared source only when the
  collection and its document access are approved.
- Document previews, OCR text, versions, and citations keep working under
  the collection's permission boundary.

## 4. Safety, moderation, and notifications

- Safety numbers confirm member devices match; sealed epochs rotate on
  membership change for rooms with sealed chat enabled.
- Members can block abusive peers and file reports with a message
  reference; admins triage with notes, and a per-member spam score combines
  reports and volume.
- Collection notifications (security changes, invites, device links) are
  idempotent with read lifecycle; browser push fanout reaches subscribed
  devices.

## 5. Experimental beta: what that means

Collections work end-to-end locally and are covered by integration and
browser tests, but they are labelled experimental beta because external
staging proof (real devices, real networks, second tenants) and the
phase-2 client-held sealed-chat custody are still open gates. During beta:

1. Enable sealed chat only after the chat keyring is configured; without it
   the API fails closed instead of silently downgrading.
2. Treat safety-number mismatches as a stop signal and re-verify devices.
3. Expect text-first polish: very large rooms, flaky networks, and older
   mobile browsers are the least exercised paths.

## 6. What must not change

1. No silent joins, no silent message edits, no read-state rollback.
2. Uploads stay client-side sealed; the server never needs plaintext.
3. Broadcasts stay metadata-only for sealed rooms.
4. Document access never widens beyond the collection's approved members.
5. Every claim on the public landing page must resolve to the behavior
   above; gated pieces stay labelled gated.

## 7. Verification

Integration coverage exercises invites/accept/decline, idempotent send,
reactions, receipts, media attach/download, expiry pruning, sealed
enable/rotate/clear-shred, blocks/reports, and tenant isolation. Frontend
coverage renders the encrypted chat client, typing state, ticks, reaction
bar and badges, media flows, safety numbers, and expiry controls.
