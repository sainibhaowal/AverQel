# Storage retention: decision gates and high-risk changes

> **Historical decision record.** The active safeguards and release checklist
> are consolidated in the [Storage retention lifecycle production guide](../02-storage-retention-production-guide.md).

## Purpose and current status

Retention changes data visibility and user expectations, so the system uses a
conservative archive-first design. The local implementation includes policy,
reconciliation, reservations, reversible archive/restore, DeepSpace archived
history, event-to-run links, pins, legal holds, administrator exemptions, and
tenant scan lease/checkpoint recovery.

The remaining gates are external release evidence:

- deploy the exact code and migrations to isolated staging;
- restore real PostgreSQL and object-storage backups into disposable targets;
- run authenticated staging E2E for chat, queue, retry, approval, reload,
  archive, restore, and cross-tenant denial;
- review reconciliation, lease, audit, and error metrics.

Production/VPS automatic archive remains disabled. Permanent purge remains
disabled everywhere in this feature.

## Settled decisions

| Topic | Current decision | Why |
| --- | --- | --- |
| User control | One tenant-scoped `Off/30/60/90` Storage setting. | Simple user experience; complexity belongs in the protected lifecycle service. |
| Archive behavior | Archive changes lifecycle metadata and creates a restore manifest. | Reversible and does not remove source rows or objects. |
| Permanent purge | No worker, route, setting, or enabled phase. | Irreversible deletion requires a separate policy, legal review, backup plan, and approval. |
| Default | `Off` for existing and new tenants. | Prevents unexpected behavior when the feature is deployed. |
| Unknown data | Preserve unknown categories and legacy unlinked events. | The system must not guess that evidence or content is safe to remove. |
| Active work | Runs, queues, retries, approvals, uploads, schedules, dependencies, pins, holds, and exemptions block archive. | Work in progress and protected content must remain available. |
| Provider/security data | Provider profiles, MCP connections, encrypted credentials, security, audit, and authentication records are outside user-content retention. | Configuration and security records must not disappear because they were not recently used. |
| Activity | Durable writes reset activity; generic reads, polling, reloads, reconnects, and metrics do not. | Background traffic must not keep everything alive or change behavior unexpectedly. |
| Storage model | Lifecycle metadata is additive; PostgreSQL, object storage, and Redis remain the source stores for their own data. | Storage is not a second duplicate database or per-user disk mount. |

## High-impact changes that remain separately gated

### Production automatic archive

The code path is guarded to development, test, and staging. Production/VPS
enablement requires all staging checks to pass, a reviewed reconciliation
report, rollback evidence, monitoring, and an approved change window.

### Permanent purge

Permanent purge is not part of the current release. Any future proposal must
define the grace period, backup interaction, legal holds, restore limits, audit
record, operator authorization, object-storage order, and verified rollback or
disaster-recovery procedure before code is written.

### Intentional Open/read activity

Current generic GET routes do not reset retention. If product policy later says
that a user intentionally opening an item should reset its timer, add a
dedicated authorized and debounced activity event. Do not infer it from page
loads, list queries, polling, or SSE reconnects.

## Components treated as contracts

Retention must remain additive around these existing contracts:

| Component | Contract to preserve |
| --- | --- |
| `backend/app/deepspace/api/chats.py` streaming path | Live chat/SSE behavior, reconnect, message ordering, and queue controls. Retention routes are separate handlers. |
| `backend/app/deepspace/services/chat_service.py` | Provider/tool execution, model selection, prompt construction, and response behavior. |
| `backend/app/deepspace/services/turn_queue.py` | Durable ordering, pause/resume, steering, retry, and crash recovery. Retention only reads protection state. |
| `frontend/app/dashboard/deepspace/_components/DeepSpaceChatClient.tsx` | Runtime stream and reconnect state. Archived history is additive UI state. |
| `frontend/app/dashboard/deepspace/_components/DeepSpaceComposer.tsx` | Sending, model search, queue, and steering. No retention action is mixed into submission. |
| Provider, profile, authentication, RLS, encryption, and tenant helpers | Authorization and secret-handling boundaries. Retention reuses them and never bypasses them. |

## Go/no-go checklist

Do not enable automatic archive for production/VPS until all are true:

- [ ] Migrations through `20260928_0001_retention_protections_and_run_links`
      are applied and verified in isolated staging.
- [ ] Matching PostgreSQL and object-storage backups restore into disposable
      staging targets.
- [ ] Active chat, queue, retry, approval, reload, archive, restore, and
      cross-tenant denial E2E tests pass.
- [ ] Reconciliation mismatch blocks automatic archive.
- [ ] Worker lease expiry and recovery are verified without duplicate archive.
- [ ] Every decision has tenant, reason, policy version, and audit context.
- [ ] Rollback image and recovery procedure are available.
- [ ] Permanent purge remains disabled.

## Plain-language scenarios

### Old but active DeepSpace work

An agent run waits for approval on day 31. The selected policy is 30 days.
The run, conversation, events, and checkpoint remain protected. Reloading the
browser does not cancel the run or cause archive.

### Truly inactive conversation

A tenant selects 30 days. A known conversation has no durable activity for 40
days, no active dependency, no hold, no pin, and no reconciliation mismatch.
Only in an allowed local/staging environment does the scan archive its
lifecycle metadata. Messages and objects remain, Archived history shows it,
and Restore returns it to the normal list.

### Cross-tenant request

Tenant A attempts to inspect or restore Tenant B's archived conversation. The
existing authenticated tenant and ownership checks deny the request without
returning content or metadata.

## Evidence boundary

Local tests and disposable restore proofs establish code behavior in the local
environment. They do not certify VPS deployment, external credentials, or
staging infrastructure. Those remain explicitly documented release gates.
