# Qel Connect chat contract

**Implementation note:** the repository contains Qel Connect chat, membership,
and report workflows. Hosted availability and security posture remain
deployment-specific. Qel Connect chat is separate from DeepSpace conversations
and Query history; see the [release index](../release/03-current-worktree-change-index.md)
for the checked source and deployment status.

## 1. Member and message lifecycle

Qel Connect provides explicit membership, shared-document references, chat,
supported media, presence, notifications, blocking, and member-submitted
reports. API routes enforce Qel Connect membership and tenant access. The
frontend does not grant access by itself.

Chat history is paginated. Sending supports a client message identifier for
retry handling. Owner clear and expiry workflows remove messages through the
implemented API and queue media cleanup as applicable. Expiry cleanup is not
a promise that copies, recipient devices, or all backups are erased.

## 2. Encryption boundary

The browser contains AES-GCM client encryption helpers. Their key derives from
the Qel Connect ID and connection code, and the Qel Connect API returns that
code to authorized clients. The backend therefore has the derivation inputs;
do not describe the current chat as zero-knowledge or server-blind
end-to-end encryption.

Qel Connect may also enable an optional backend sealed-chat mode. That mode
seals records at rest using server-held epoch keys, but the API opens messages
for authorized members. It requires an operator-configured keyring and fails
closed if that configuration is missing. See
[`10-collection-chat-encryption.md`](10-collection-chat-encryption.md) for
the custody details and security limitations. Shared source documents are
server-readable for normal document features.

## 3. Realtime, presence, and notifications

Collection routes issue scoped websocket tickets and publish supported
collection events through the realtime service. Presence and delivery/read
state are application signals; they do not prove that a person read or
understood a message. Collection notification and push availability depends on
the registered device and configured push service.

## 4. Reports and restricted moderation

Members may block another member and submit a report, including a supported
message reference. The moderation queue is a report-triage workflow for users
assigned the `collection_moderator` role. It is protected by permission checks
and active-tenant scope, and is not a general interface for browsing member
collections or chat history. Report details load on demand; reads and decisions
are audited.

## 5. Deployment and release status

The implementation includes database-backed collection, chat, membership,
notification, and report flows. Production readiness still requires the
release owner to verify migrations, worker and realtime services, object
storage, push configuration, authorization, recovery, and supported client
devices in the target environment. A passing local test suite is not hosted
deployment evidence. The feature is currently treated as experimental beta in
the repository release documentation.

## 6. Required documentation language

- Do not claim zero-knowledge, server-blind encryption, or Signal/libsignal
  protocol compatibility.
- Do not claim expiry removes all copies or backups.
- Do not claim moderation grants a platform-wide view of private collections.
- Keep collection chat, DeepSpace, and Query as distinct product surfaces.
