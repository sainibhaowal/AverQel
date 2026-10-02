# 06. DeepSpace plans and tenant storage

## Current implementation

The authenticated `GET /api/v1/plans/current` endpoint reports the role-based
plan and tenant-scoped durable storage usage. The Settings → Plan & Storage
page displays this information and the available plan cards.

The separate authenticated `GET /api/v1/storage/current` endpoint powers
Settings → Storage details. That page refreshes every 15 seconds and also has a
manual refresh action. It exposes aggregate counts and sizes only; it never
returns chat text, memory values, provider credentials, MCP secrets, or object
storage keys.

Each tenant now has a durable `tenant_storage_allocations` record. New
registrations receive an allocation in the same transaction as the account;
existing tenants are backfilled by the migration. The allocation is a logical
quota over the existing tenant-prefixed object storage and database-owned
content—it does not move data or create a separate physical bucket.

| Account role | Plan | Storage |
| --- | --- | ---: |
| `user` / `reader` | Free | 500 MiB |
| `editor` | Editor | 1 GiB |
| `admin` / `super_admin` | Admin | 1 GiB |

The Admin card is returned only to an authenticated admin role and is also
filtered in the frontend. Role checks are server-authoritative; hiding the
card in the browser is not the security boundary.

## Storage scope

The quota is shared by the authenticated tenant/workspace and currently counts:

- non-deleted Documents;
- current DeepSpace Library files;
- saved DeepSpace media artifacts;
- active resumable Library upload reservations;
- durable chat, memory, collection/index, activity, queue, workspace metadata,
  and protected connection payload estimates.

The Storage details page also inventories related tenant-owned records so users
can understand the account as a whole:

- chat history and notes;
- grounded query history and saved generated answers;
- saved memory;
- collections and indexed chunks;
- agent activity and reconnectable run history;
- queues and durable task records;
- workspace folders;
- provider and MCP profiles (record counts only; secrets remain protected);
- model token usage.

These database-backed categories are included in the logical tenant quota using
safe estimates of durable content bytes. They are not claims about PostgreSQL
physical disk overhead. Secret values, private model reasoning, and temporary
system caches remain protected and are not exposed by the page.

Historical Library versions are not double-counted as current files. Temporary
system caches and private model reasoning are not included in the tenant quota:
global infrastructure cache must not consume one tenant's allocation. Durable
tenant-owned cache should be added to the metered model before it is treated as
user storage. Token counts remain usage metrics, not storage bytes.

## Enforcement

Quota checks run before durable writes at the document, Library,
workspace-file, generated-artifact, chat/note, grounded-query, memory,
collection-chat, queue/task, runtime-event/checkpoint, provider-secret, MCP,
and connector boundaries. Updates use replacement-aware accounting so an edit
does not count the old value twice. The tenant row is locked while usage is
checked to prevent concurrent writes from both passing the same quota check.
A quota failure returns `STORAGE_QUOTA_EXCEEDED` at API boundaries or aborts
the current transaction in worker paths; it does not cancel unrelated chats,
queues, providers, or existing files.

The meter is logical and live: exact object sizes are combined with safe byte
estimates for durable database content, JSON, encrypted ciphertext, and vector
payloads. PostgreSQL indexes, row overhead, WAL, backups, and global caches are
not represented as tenant-owned bytes. The Storage page polls every 15 seconds
and supports manual refresh; it is not a push/WebSocket meter.

## Compatibility boundary

This feature does not change model selection, provider settings, DeepSpace SSE,
message ordering, queue pause/resume/steer/retry, authentication, tenant
isolation, object-storage key layout, or explicit deletion workflows. Feature
entitlements beyond storage are intentionally not enforced yet; the plan page
lists the current baseline features while product access rules are decided.

The Storage details page is read-only. It does not delete, archive, compact,
cancel, pause, steer, or modify any account data. It uses the authenticated
tenant from the server auth context for every query.

## Verification

- Backend plan-resolution unit tests cover Free, Editor, Admin, and legacy role aliases.
- Backend API tests verify tenant-authenticated plan data and Admin-card visibility.
- Backend integration tests verify chat history metering, quota rejection, replacement
  accounting, and tenant-scoped storage enforcement.
- Frontend tests verify the Plan & Storage settings card and hide the Admin card for normal users.
- TypeScript, focused Vitest tests, Python compilation, Ruff, and diff checks must pass before release.

## Production rollout

The allocation migration must be applied before production rollout. Run the
focused tests with the real staging PostgreSQL/object-storage configuration and
exercise concurrent document, Library, chat, and artifact writes. Future
billing or plan changes should update the allocation policy rather than moving
tenant data or changing encryption boundaries.
