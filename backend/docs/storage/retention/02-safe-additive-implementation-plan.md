# Storage retention: safe additive implementation plan

> **Historical implementation record.** The implementation is now present in
> the local codebase. The [Storage retention lifecycle production guide](../02-storage-retention-production-guide.md)
> is the active source of truth for deployment and release status.

## Purpose

The plan was to add archive-first retention without changing normal DeepSpace
chat, provider profiles, authentication, queue ordering, steering,
pause/resume, or existing manual deletion. That additive implementation is now
complete locally. This file explains what was added and what still requires
external release evidence.

## Implemented components

| Component | Current implementation |
| --- | --- |
| Tenant policy | `tenant_storage_allocations` stores validated `off`, `30`, `60`, or `90` day policy state. |
| Lifecycle registry | `storage_lifecycle_items` stores tenant/category/source identity, size metadata, activity, state, dependencies, and protection flags. |
| Preview/audit | `storage_retention_runs` and `storage_retention_decisions` record policy version, candidate/protection decisions, and reasons. |
| Archive/restore | `storage_archive_manifests` records reversible lifecycle state; source rows and object-storage objects are not deleted. |
| Reconciliation | `storage_lifecycle_adapters.py` reconciles known quota categories and reports mismatches. Unknown data is preserved. |
| Quota reservations | `storage_quota_reservations` supports idempotent capacity reservation for supported writes. |
| Resumability | `storage_retention_runs` carries lease and checkpoint state; expired leases can be reclaimed safely. |
| Run identity | New DeepSpace run events may carry a nullable `run_id`; legacy NULL-linked events remain protected. |
| Protections | Pinned items, legal holds, administrator exemptions, active work, dependencies, and unresolved data block automatic archive. |
| DeepSpace UI | Archived conversations are hidden from the normal history list and available through Archived history with Restore. |
| Policy APIs | Storage policy, preview, reconciliation, archive, and restore routes are authenticated and tenant-scoped. |

## Policy and worker behavior

The user sees one setting: `Off`, `30`, `60`, or `90` days. The default is
`Off`. Durable writes record meaningful activity; background reads, polling,
reloads, SSE reconnects, and metrics reads do not.

The scheduler has two unrelated jobs:

- `maintenance.retention_cleanup` remains the daily technical cleanup for
  transient and separate audit policies; it does not delete chat history.
- `maintenance.storage_retention_scan` runs on the first day of each month at
  04:00 UTC to reconcile and preview tenant lifecycle data.

Automatic archive is allowed only when:

```text
AKS_STORAGE_RETENTION_AUTOMATIC_ARCHIVE_ENABLED=true
AND environment ∈ {development, test, staging}
AND reconciliation has no mismatch for that tenant
```

The enabled path changes lifecycle metadata and creates a restore manifest. It
does not delete source rows or object-storage objects. Production and VPS
automatic archive remain disabled. Permanent purge has no route, worker, or
configuration flag.

## API contract

All routes use the `/api/v1` prefix and existing authentication/tenant checks.

| Method and route | Behavior |
| --- | --- |
| `GET /api/v1/storage/retention` | Read the active tenant policy. |
| `PUT /api/v1/storage/retention` | Set `off`, `30`, `60`, or `90`. |
| `GET /api/v1/storage/retention/preview` | Preview candidates and exclusions without deleting source data. |
| `POST /api/v1/storage/reconcile` | Reconcile the authenticated tenant. |
| `POST /api/v1/storage/archives/{item_id}` | Archive an eligible item owned by the caller/admin. |
| `POST /api/v1/storage/archives/{item_id}/restore` | Restore an archived item. |
| `GET /api/v1/deepspace/chats/archived` | List the authenticated owner's archived DeepSpace conversations. |
| `GET /api/v1/deepspace/chats/retention/{conversation_id}` | Read authorized retention status. |
| `POST /api/v1/deepspace/chats/{conversation_id}/restore` | Restore an authorized archived conversation. |
| `PATCH /api/v1/deepspace/chats/{conversation_id}/retention/protection` | Owner pin; tenant-admin hold or exemption. |

Retention is not added to the streaming endpoint and does not send a model
request.

## Migration sequence

The additive migrations are ordered and must not be manually reordered:

1. `20260924_0001_tenant_storage_allocations`
2. `20260925_0001_storage_retention_lifecycle`
3. `20260926_0001_storage_reservations_archive_reconciliation`
4. `20260927_0001_retention_checkpoints`
5. `20260928_0001_retention_protections_and_run_links`

Existing source data is not moved or deleted by these migrations. Do not edit
`alembic_version` manually or remove migration rows.

## Protection and race rules

Before an item is archived, the service excludes:

- running, cancelling, awaiting-user, or awaiting-approval runs;
- queued, running, stopping, paused, retryable, or recovery-claimed turns;
- pending approvals, questions, uploads, retries, or active schedules;
- pinned items, legal holds, and administrator exemptions;
- referenced artifacts and newer dependencies in the same group;
- unknown categories, legacy unlinked events, and reconciliation mismatches.

The scan is tenant-leased and checkpointed. If a worker stops, a later worker
can reclaim an expired lease and continue. New durable activity or a newly
discovered protection condition prevents archive. Archive and restore are
idempotent metadata transitions.

## Verification completed locally

The local verification includes the focused retention workflow, tenant
authorization, direct lifecycle hooks, reconciliation, reservation idempotency,
archive/restore, DeepSpace archive visibility, explicit protections, and lease
recovery. The full local backend/frontend and restore evidence are recorded in
the active release handoff.

## External release gates still open

Local proof does not equal staging proof. Before enabling production/VPS
automatic archive, deploy the exact migration/code set to isolated staging and:

1. restore matching PostgreSQL and object-storage backups into disposable
   targets;
2. run active-chat, queue, retry, approval, reload, archive, restore, and
   cross-tenant E2E scenarios;
3. verify worker lease recovery and reconciliation mismatch blocking;
4. review audit, error, and retention metrics;
5. keep permanent purge disabled.

## Non-regression contract

The implementation does not intentionally alter DeepSpace message content,
SSE streaming, provider selection, MCP policy, model calls, queue order,
pause/resume/steering, memory behavior, authentication, encryption, tenant
isolation, or explicit user deletion. Any future change to those contracts
requires a separate design and regression review.
