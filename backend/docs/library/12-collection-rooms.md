# Collections: member workflow and release boundaries

**Status:** experimental beta in this repository. This guide describes the
implemented member workflow; it is not evidence that a hosted deployment has
passed production staging.

## 1. Purpose

A collection is a small collaboration boundary for invited members to share
selected documents and use collection-specific chat. It does not expose an
entire tenant workspace. Documents are shared through the collection's
authorized references and remain part of the server-side Documents Hub
processing model.

## 2. Membership

Members join through the collection invitation and acceptance flows. Collection
roles and ownership determine which membership, sharing, retention, and
security actions are available. The API validates membership on reads and
writes; hiding a button in the frontend is not the access-control boundary.

## 3. Chat, files, and collaboration

The current interface supports collection chat and selected collaborative
features such as media, reactions, presence, read/delivery state, notifications,
blocking, and reports. Availability can differ by deployment and client.
Collection chat is separate from DeepSpace agent conversations and Query
history.

The client contains encryption helpers, but the connection code used by their
key derivation is returned by the collection API. An optional server-mediated
sealed-at-rest mode also exists. Neither design should be described as
zero-knowledge or as audited Signal-compatible end-to-end encryption. See
[`10-collection-chat-encryption.md`](10-collection-chat-encryption.md) before
publishing any security language.

## 4. Sharing and report review

Shared documents remain server-readable for scanning, preview, OCR, indexing,
and retrieval. Access remains subject to collection membership and document
permissions.

Members can submit reports and block members where those controls are
available. The restricted moderation queue lets authorized tenant
administrators triage reports and record moderation history. It is not a
general collection or private-message browser.

## 5. Expiry and deletion

The collection owner can configure chat expiry or clear history where the
controls are available. Cleanup follows the implemented API and worker path.
It does not, by itself, establish deletion from backups, exported copies,
recipient devices, screenshots, or external storage. The service's retention
and backup policy remains relevant.

## 6. Beta release gates

Before removing the experimental-beta label, the release owner should record
target-environment evidence for:

- ordered database migrations and backup/restore behavior;
- cross-tenant and role-based access checks;
- concurrent invitations, membership changes, blocks, and reports;
- message and media delivery on supported real devices and networks;
- expiry, cleanup, retention, and failure recovery;
- push/realtime service configuration and operational monitoring;
- an independently reviewed threat model and accurate user-facing encryption
  language.

Local integration or frontend tests cover only the paths they exercise. They
do not substitute for this deployment evidence.
