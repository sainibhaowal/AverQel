# Storage retention: complete production specification

> **Historical companion specification.** The active implementation and
> release state are maintained in the [Storage retention lifecycle production guide](../02-storage-retention-production-guide.md).

This document is retained because it captures the complete product model. It
does not override the canonical backend guide, current code, migration state,
or deployment gates.

## Product contract

The user has one tenant-scoped setting:

```text
Off | 30 days | 60 days | 90 days
```

The selected period applies only to known, durable, tenant-owned user content
with no meaningful activity and no protection condition. It permits reversible
archive; it does not permit permanent deletion.

```text
eligible item -> archived lifecycle state + restore manifest -> active again
```

Source PostgreSQL rows and object-storage objects remain in place in the current
release. Permanent purge is disabled.

## Data classes

### Eligible user content

Chats, notes, documents, Library files, memory, grounded queries, collections,
artifacts, and task records may participate only when their identity, activity,
dependencies, tenant ownership, and reconciliation state are known.

### Always protected

- active, paused, waiting, retryable, or recovery-claimed runs and queues;
- approvals, questions, checkpoints, uploads, retries, and active schedules;
- referenced artifacts and newer dependencies;
- pinned items, legal holds, and administrator exemptions;
- provider profiles, MCP connections, encrypted credentials, security and
  encryption metadata;
- authentication, audit, compliance, and legal records;
- unknown categories, legacy records, and unlinked event data.

Redis, live fan-out, transient transport data, and short-lived upload chunks
continue to follow their own infrastructure TTL/recovery behavior. They are
not converted into durable user-content retention items by this policy.

## Activity rules

Current direct durable-write hooks cover conversations/messages/notes, queues,
DeepSpace runs and checkpoints, documents and Library files, artifact jobs and
results, memory and preferences, grounded queries, collections and collection
chat, and tasks.

These events do not reset activity:

- generic GET requests and list reads;
- browser navigation, reload, polling, and Storage-page refresh;
- SSE reconnects, worker heartbeats, metrics, and Redis reads.

If intentional user Open/read activity is added later, it must use a dedicated,
authorized, debounced event. It must not be inferred from generic read traffic.

## Implemented architecture

The application keeps each type of data in its existing source store. Storage
retention is a metadata and policy layer, not a second copy of the application:

```text
authenticated durable write
  -> existing PostgreSQL/object-storage source
  -> quota/reservation where applicable
  -> tenant lifecycle metadata
  -> monthly reconcile + preview
  -> guarded local/staging metadata archive
  -> DeepSpace Archived history and Restore
```

The implemented registry records tenant/category/source identity, owner,
logical or exact size, activity, state, dependencies, protection flags, policy
version, leases/checkpoints, and audit decisions. It does not copy chat text,
memory values, secrets, private reasoning, or object-storage keys.

## Lifecycle and protection

```text
active -> eligible -> archived -> restore -> active
```

The current release stops at `archived`. A preview or archive operation is
tenant-scoped and rechecks protection state. New activity, a newer dependency,
or an uncertain condition prevents archive. Reconciliation mismatch also
prevents automatic archive.

The current migration sequence ends at:

```text
20260928_0001_retention_protections_and_run_links
```

The migration is additive. It does not move or delete existing user data.

## Current routes

| Method and route | Purpose |
| --- | --- |
| `GET /api/v1/storage/retention` | Read policy. |
| `PUT /api/v1/storage/retention` | Set `off`, `30`, `60`, or `90`. |
| `GET /api/v1/storage/retention/preview` | Preview candidates/protections. |
| `POST /api/v1/storage/reconcile` | Reconcile one authenticated tenant. |
| `POST /api/v1/storage/archives/{item_id}` | Archive an eligible item without source deletion. |
| `POST /api/v1/storage/archives/{item_id}/restore` | Restore an archived item. |
| `GET /api/v1/deepspace/chats/archived` | List archived DeepSpace history for the owner. |
| `GET /api/v1/deepspace/chats/retention/{conversation_id}` | Read retention status. |
| `POST /api/v1/deepspace/chats/{conversation_id}/restore` | Restore a conversation. |
| `PATCH /api/v1/deepspace/chats/{conversation_id}/retention/protection` | Set owner pin or authorized admin hold/exemption. |

No retention action is added to the live streaming route, and archive/restore
does not send a model request or cancel queue work.

## Scheduling and release state

The daily 02:00 UTC technical cleanup is separate from the monthly first-day
04:00 UTC Storage retention scan. The daily job does not remove chat history.

Automatic archive is enabled only when the environment flag is true **and** the
environment is development, test, or staging. The tenant policy must also be
non-`Off`, reconciliation must have no mismatch, and protection checks must
pass. Production/VPS automatic archive remains disabled.

Local verification and disposable PostgreSQL/object-storage restore proofs are
complete. External staging deployment, real external backup/restore, and
authenticated staging E2E remain release gates. This document must not be read
as a production/VPS readiness certificate.

## Explicit non-goals

This release does not change:

- DeepSpace chat execution, SSE, provider selection, MCP, or model calls;
- queue ordering, pause/resume, steering, retries, or crash recovery;
- authentication, tenant isolation, encryption, or secret handling;
- existing manual deletion behavior;
- temporary Redis or infrastructure TTL policies;
- private model chain-of-thought handling.

Permanent purge is intentionally absent. Any future purge proposal requires a
separate approved policy, backup/disaster-recovery decision, grace period,
legal-hold behavior, audit design, object-storage ordering, restore proof, and
production change review.
