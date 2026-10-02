# Storage-controlled retention: current state and minimal safe fixes

> **Historical design record.** The active implementation and release status are
> maintained in the [Storage retention lifecycle production guide](../02-storage-retention-production-guide.md).

## Status

This document records the original current-state review and the minimal safe
design that led to the implemented Storage retention lifecycle. It is retained
for audit and decision history. The backend guide and code are authoritative if
this record differs from them.

The local implementation is archive-first and metadata-only. The tenant policy,
lifecycle registry, adapters, reconciliation, quota reservations, archive
manifests, restore, protections, scan leases, and checkpoints are implemented.
Automatic archive is guarded to development, test, and staging environments;
production/VPS automatic archive is disabled. Permanent purge is not
implemented.

External staging deployment, backup/restore proof, and authenticated staging
E2E proof remain release gates. They are deployment evidence, not permission to
delete data locally or in production.

## User-facing contract

Storage exposes one tenant-scoped lifecycle setting:

```text
Off | 30 days | 60 days | 90 days
```

The default is `Off` for existing and newly allocated tenants. The setting
controls eligibility for reversible archive of known, durable, tenant-owned
user content. It never enables permanent deletion.

Current API routes:

| Method and route | Purpose |
| --- | --- |
| `GET /api/v1/storage/retention` | Read the authenticated tenant policy. |
| `PUT /api/v1/storage/retention` | Set `off`, `30`, `60`, or `90`. |
| `GET /api/v1/storage/retention/preview` | Return tenant-scoped candidate/protection totals. |
| `POST /api/v1/storage/reconcile` | Reconcile and report the authenticated tenant. |
| `POST /api/v1/storage/archives/{item_id}` | Archive one eligible owned item without deleting its source. |
| `POST /api/v1/storage/archives/{item_id}/restore` | Restore one archived owned item. |

DeepSpace-specific routes are documented in the canonical guide and provide
archived-history listing, status, restore, pin, legal hold, and administrator
exemption controls.

## Current implementation map

| Area | Current reality |
| --- | --- |
| Policy | `tenant_storage_allocations` stores the validated mode and days. |
| Lifecycle identity | `storage_lifecycle_items` stores tenant/category/source identity, size metadata, activity, state, dependencies, and protections. |
| Audit | `storage_retention_runs` and `storage_retention_decisions` record previews and archive decisions. |
| Archive | `storage_archive_manifests` records reversible metadata state; source rows and objects remain. |
| Reconciliation | Category adapters compare source data with lifecycle metadata; mismatch blocks automatic archive. |
| Quota safety | `storage_quota_reservations` provides idempotent capacity reservations for supported writes. |
| Recovery | Lease and cursor/checkpoint fields allow a later worker to recover an expired scan. |
| Event safety | New DeepSpace events may link to a run; legacy events without a link are preserved. |
| DeepSpace UI | Archived conversations are hidden from the normal list, visible in Archived history, and restorable. |

## What counts as meaningful activity

Direct durable writes currently record lifecycle activity for conversations,
messages and notes, queues, DeepSpace runs/checkpoints, documents and Library
files, artifact jobs/results, memory and preferences, grounded queries,
collections and collection chat, and task records.

The following do **not** reset retention:

- page navigation, reload, or list refresh;
- Storage-page polling;
- SSE reconnects and worker heartbeats;
- metrics or background reads;
- Redis cache reads.

An explicit user-open/read event is not inferred from a generic GET request. If
the product later chooses to count an intentional Open action, it must be a
separate authorized and debounced activity hook.

## Data classification

| Class | Examples | Policy |
| --- | --- | --- |
| Eligible user content | Chats, notes, documents, Library files, memory, queries, collections, artifacts, tasks | May be archived only when identity, activity, dependencies, tenant ownership, and reconciliation are safe. |
| Active execution state | Runs, queue turns, approvals, retries, checkpoints, uploads, schedules | Protected while active, referenced, recoverable, or uncertain. |
| Critical configuration | Provider profiles, MCP connections, encrypted credentials, security and encryption metadata | Protected by default; not handled by this policy. |
| Temporary infrastructure | Redis, live fan-out, transient broker data, short-lived transport data | Uses its existing TTL/recovery policy. |
| Security and audit | Authentication, authorization, audit, compliance, deletion-request records | Uses separate retention rules. |
| Unknown legacy data | Rows, events, or objects without reliable identity | Preserved; the system does not guess. |

## Safety invariants

1. Archive changes lifecycle metadata and creates a restore manifest; it does
   not delete source database rows or object-storage objects.
2. Every read and write is tenant-scoped and uses existing authentication and
   ownership checks.
3. Active, paused, waiting, retryable, queued, uploaded, scheduled, pinned,
   held, exempt, or referenced work is protected.
4. Reconciliation mismatch blocks automatic archive.
5. Unknown or unlinked legacy events are preserved.
6. Retention runs outside the live chat/SSE, provider, MCP, queue, steering,
   pause/resume, and explicit-delete contracts.
7. There is no automatic permanent purge worker, route, or setting.

## Scheduling: two separate jobs

These jobs must not be confused:

| Job | Schedule | Behavior |
| --- | --- | --- |
| `maintenance.retention_cleanup` | Daily at 02:00 UTC | Existing technical cleanup for transient/idempotency/deletion-request and separate audit policies; it does not remove chat history. |
| `maintenance.storage_retention_scan` | First day of each month at 04:00 UTC | Tenant-scoped reconciliation and preview; optional metadata-only archive only when the guarded environment flag and all safety checks allow it. |

The environment flag is
`AKS_STORAGE_RETENTION_AUTOMATIC_ARCHIVE_ENABLED=true`, but code also requires
the environment to be development, test, or staging. Production/VPS cannot
enable this path through the flag. Permanent purge has no flag or schedule.

## Remaining release gates

Before production/VPS archive is considered, the following must be completed
in isolated staging:

1. Apply migrations through
   `20260928_0001_retention_protections_and_run_links`.
2. Restore matching PostgreSQL and object-storage backups into disposable
   targets.
3. Run active chat, queue, retry, approval, reload, archive, restore, and
   cross-tenant denial scenarios.
4. Review reconciliation, lease-recovery, error, and audit metrics.
5. Keep permanent purge disabled.

## Effect on existing behavior

Normal DeepSpace chat, streaming, model/provider selection, MCP, queue order,
pause/resume, steering, memory, authentication, tenant isolation, and explicit
manual deletion remain separate contracts. Retention only adds lifecycle
metadata, guarded background processing, and authorized archive/restore views.
