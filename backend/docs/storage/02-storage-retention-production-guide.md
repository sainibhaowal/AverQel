# 02. Storage retention lifecycle: production guide

**Status:** implemented locally; local/staging automatic archive is opt-in; production automatic archive is disabled
**Audience:** application developers, reviewers, operators, and support engineers
**Last reviewed:** 2026-09-23

## 1. Purpose

This is the canonical operational and engineering guide for AverQel's
tenant-scoped Storage retention lifecycle. It consolidates the retention
design, implemented behavior, safety boundaries, deployment procedure, and
release gates.

The product offers users one simple Storage setting:

| Setting | Result |
| --- | --- |
| Off | No automatic archive candidates are created for that tenant. This is the default. |
| 30 days | Eligible inactive tenant-owned content may be archived after 30 days. |
| 60 days | Eligible inactive tenant-owned content may be archived after 60 days. |
| 90 days | Eligible inactive tenant-owned content may be archived after 90 days. |

The internal implementation is intentionally more conservative than the
setting suggests. It protects active work, uses tenant-scoped lifecycle
metadata, and archives before any future deletion decision.

## 2. Current release state

### Implemented

- Tenant-scoped `off` / `30` / `60` / `90` retention policy.
- Additive lifecycle registry, decision audit records, scan leases, and
  resumable scan checkpoints.
- Direct activity recording for durable writes in chat, DeepSpace runs and
  queues, documents, Library files, artifact jobs/results, memory,
  preferences, queries, collections, collection chat, and tasks.
- Tenant-scoped policy and preview APIs.
- Monthly reconciliation and preview scan.
- Optional metadata-only archive for local and staging environments.
- DeepSpace Archived history, restore, owner pinning, and tenant-admin legal
  hold / retention exemption controls.
- Nullable event-to-run relationship for new DeepSpace run events; unknown
  legacy events remain protected.

### Deliberately not enabled

- Permanent purge of chat, files, objects, or lifecycle source rows.
- Automatic archive in production or VPS environments.
- Any retention policy for provider credentials, encryption material,
  authentication records, security records, audit records, or global caches.
- Passive page-view activity tracking. A page refresh, list refresh, SSE
  reconnect, metrics read, or background worker status read does **not** reset
  retention activity.

### Release gates still required

1. Deploy the code and migrations to an isolated staging environment.
2. Restore a real PostgreSQL backup and matching object-storage backup into
   disposable staging targets.
3. Run staging E2E checks for active chat, queue, retry, approval, reload,
   archive, restore, and cross-tenant denial.
4. Review staging reconciliation and lease-recovery metrics.
5. Keep production archive disabled unless all of the above are accepted.

Local test evidence is valuable but is not a substitute for this external
staging proof.

## 3. Non-negotiable safety invariants

The retention system must satisfy every rule below.

1. **Archive first.** The implemented archive path changes only lifecycle
   metadata and creates a restore manifest. It never deletes a source database
   row or object-storage object.
2. **Unknown means preserve.** An item with incomplete identity, dependency,
   or run information is never guessed safe for archive or purge.
3. **Tenant isolation is authoritative.** Every lifecycle item, preview,
   archive decision, restore, and object reference is scoped to the
   authenticated tenant.
4. **Active work wins.** A run, queue, retry, approval, upload, scheduled job,
   pin, legal hold, administrator exemption, or active dependency blocks
   automatic archive.
5. **Retention is outside the live chat path.** It must not alter SSE,
   model selection, provider credentials, tool execution, queue ordering,
   pause/resume/steering, or explicit deletion behavior.
6. **Background reads do not extend retention.** Only durable writes and
   explicitly designed interaction events may advance meaningful activity.
7. **Purge is unavailable.** There is no production worker, API, or setting
   that permanently purges user content through this lifecycle feature.

## 4. Data classification

Retention behavior is driven by data class, not by the location of a table.

| Data class | Examples | Lifecycle behavior |
| --- | --- | --- |
| User content | chats, notes, documents, Library files, memory, queries, collections, artifacts, tasks | May participate in the user-selected archive policy only after the safety checks pass. |
| Active execution state | agent runs, queue turns, approvals, retries, checkpoints, uploads, schedules | Always protected while non-terminal or referenced by active work. |
| Critical account configuration | provider profiles, MCP connections, encrypted credentials, encryption metadata, security settings | Protected by default. This policy must not archive or delete it. |
| Temporary infrastructure | Redis cache, live fan-out, transient broker data, short-lived tool transport data | Uses its own TTL/recovery policy. It is not tenant user-content retention. |
| Security and audit | authentication, authorization, audit, compliance, deletion-request records | Uses separate security/audit retention rules; never the user Storage policy. |
| Unknown legacy data | old rows or objects without a reliable lifecycle identity | Preserved until a separate, reviewed migration can classify it safely. |

Private model chain-of-thought is not collected by this feature. Visible tool
activity and safe summaries may be stored according to existing runtime
behavior; secret values remain redacted.

## 5. Architecture

Storage is not a second copy of user data and is not a per-user disk mount.
The existing PostgreSQL, object storage, and Redis systems continue to own
their appropriate data. The lifecycle registry records safe metadata about
tenant-owned durable content.

```text
Authenticated durable write
        |
        +--> existing source store (PostgreSQL / object storage)
        |
        +--> quota enforcement and reservation where applicable
        |
        +--> lifecycle activity metadata
                  |
                  +--> monthly tenant-scoped reconcile + preview
                            |
                            +--> optional local/staging metadata archive
                                      |
                                      +--> DeepSpace Archived view / Restore
```

The registry stores identity and policy metadata, not a duplicate of private
content:

- tenant ID, owner ID, category, source type, source ID;
- logical or exact size where available;
- `last_meaningful_activity_at`;
- lifecycle state and archive/restore timestamps;
- dependency and protection metadata;
- policy version, scan lease/checkpoint, and audit decision reason.

It does not return chat text, memory values, API keys, encrypted secret
material, or object-storage keys to the Storage UI or retention APIs.

## 6. Meaningful activity

### Events that currently reset activity

The following durable write paths record activity directly:

- creating or changing conversations, messages, notes, queue turns, agent
  runs, run checkpoints, and task state;
- document creation/status/metadata changes;
- Library writes, uploads, copies, and version creation;
- artifact job creation and durable artifact persistence;
- saved memory and preference changes;
- grounded query creation and saved result changes;
- collection creation, document membership, collection chat, and metadata
  changes.

### Events that do not reset activity

- browser navigation, reload, or switching between AverQel pages;
- automatic Storage-page polling or list refresh;
- SSE reconnects and worker heartbeat observations;
- background reads, metrics collection, and Redis cache reads.

This distinction prevents a hidden browser tab or monitoring process from
keeping all tenant content alive forever. If product policy later requires an
explicit user **Open** action to extend retention, it must be implemented as a
separate authorized, debounced interaction endpoint; it must not be inferred
from generic GET requests.

## 7. Lifecycle states and protection

```text
active --> eligible --> archived --> (future, separately approved purge state)
                 ^          |
                 |          +--> restore --> active
                 |
       new meaningful activity or a protection condition
```

The current release stops at `archived`.

Before an item can become eligible or archived, the lifecycle service checks
for:

- running, cancelling, awaiting-user, or awaiting-approval agent runs;
- queued, running, stopping, paused, retryable, or recovery-claimed turns;
- pending approvals, questions, uploads, retries, or dependent schedules;
- pinned items, legal holds, and administrator retention exemptions;
- referenced artifacts or other active dependencies;
- incomplete/unknown event identity or legacy data;
- tenant mismatch or reconciliation mismatch.

Any uncertain condition is an exclusion, not a reason to archive.

## 8. User experience

### Storage settings

The authenticated Storage page shows the current plan allocation, metered
usage, inventory categories, and retention policy. The API is tenant-scoped:

| Method and route | Purpose |
| --- | --- |
| `GET /api/v1/storage/retention` | Read the active tenant's policy. |
| `PUT /api/v1/storage/retention` | Set `off`, `30`, `60`, or `90`. This cannot enable purge. |
| `GET /api/v1/storage/retention/preview` | Return aggregate candidate/protection counts and policy metadata. |
| `POST /api/v1/storage/reconcile` | Run authenticated reconciliation/reporting for the requesting tenant. |

The Storage meter is logical quota accounting. It combines exact durable
object sizes with safe estimates for durable tenant-owned database content. It
does not claim PostgreSQL index/WAL/row overhead, backup space, or global cache
space as a user's allocation.

### DeepSpace archived history

When an eligible DeepSpace conversation is archived in allowed local/staging
mode, it is hidden from the normal history list. Its messages, runtime data,
and source objects remain unchanged. The owner can open Archived history and
restore the conversation.

| Route | Authorization |
| --- | --- |
| `GET /api/v1/deepspace/chats/archived` | Conversation owner in the authenticated tenant. |
| `GET /api/v1/deepspace/chats/retention/{conversation_id}` | Conversation owner in the authenticated tenant. |
| `POST /api/v1/deepspace/chats/{conversation_id}/restore` | Conversation owner in the authenticated tenant. |
| `PATCH /api/v1/deepspace/chats/{conversation_id}/retention/protection` | Owner may set a pin; tenant admin is required for legal hold or administrator exemption. |

These controls are separate from the composer, stream, queue, and steering
controls. Archive/restore never sends a model request or cancels a run.

## 9. Scheduling and configuration

Two distinct worker processes must not be confused.

| Task | Schedule | Scope |
| --- | --- | --- |
| `maintenance.retention_cleanup` | Daily, 02:00 UTC | Existing technical cleanup: transient idempotency/deletion-request records and separate audit policy. It does not remove chat history. |
| `maintenance.storage_retention_scan` | Monthly, day 1 at 04:00 UTC | Reconcile and preview each tenant against its selected policy. |

Automatic archive is guarded in code by both conditions:

```text
AKS_STORAGE_RETENTION_AUTOMATIC_ARCHIVE_ENABLED=true
AND environment is development, test, or staging
```

Production/VPS environments are excluded even if an operator accidentally sets
the flag. Permanent purge has no configuration flag and no scheduled task.

## 10. Schema and code ownership

The implementation is additive. Existing source tables remain authoritative.

| Area | Primary location | Responsibility |
| --- | --- | --- |
| Lifecycle models | `app/system/models/storage_lifecycle.py` | Registry identity, archive manifests, scan runs, and decisions. |
| Lifecycle policy/service | `app/system/services/storage_lifecycle.py` | Activity, policy, candidate selection, protection, archive, restore, leases, and checkpoints. |
| Source reconciliation | `app/system/services/storage_lifecycle_adapters.py` | Reconcile known quota categories and preserve mismatches. |
| Worker | `app/system/workers/tasks_retention.py` | Monthly tenant-scoped reconcile/preview and guarded local/staging metadata archive. |
| Storage API | `app/system/api/storage.py` | Authenticated policy, preview, and reconciliation endpoints. |
| DeepSpace API | `app/deepspace/api/chats.py` | Archived list, restore, protection status, and protection updates. |
| Event/run identity | `app/deepspace/models/agent_runtime.py`, `app/deepspace/services/run_events.py` | Nullable `run_id` for new events; legacy NULL rows stay protected. |
| DeepSpace UI | `frontend/app/components/dashboard/ChatSidebar.tsx` | Archived history, restore, pin, and authorized retention controls. |

Required additive migrations, in order:

1. `20260924_0001_tenant_storage_allocations`
2. `20260925_0001_storage_retention_lifecycle`
3. `20260926_0001_storage_reservations_archive_reconciliation`
4. `20260927_0001_retention_checkpoints`
5. `20260928_0001_retention_protections_and_run_links`

Do not manually edit `alembic_version`, delete migration rows, or reorder
migration files.

## 11. Deployment procedure

Run this procedure only in an approved change window and begin with an
isolated staging environment.

1. Capture matching PostgreSQL and object-storage backups, checksums, image
   versions, and Alembic revision.
2. Deploy the application image containing the migrations and lifecycle code.
3. From the backend environment, apply migrations:

   ```bash
   cd /home/ravi/Projects/AverQel/backend
   source .venv/bin/activate
   ./.venv/bin/alembic current
   ./.venv/bin/alembic upgrade head
   ```

4. Confirm the application, scheduler, maintenance worker, DeepSpace worker,
   PostgreSQL, Redis, and object storage are healthy.
5. Keep automatic archive disabled and run tenant-scoped preview/reconciliation
   first.
6. Restore a matching backup pair into disposable targets and verify tenant
   prefixes, source records, archive restore, and migration revision.
7. In staging only, enable metadata-only archive for a synthetic or approved
   isolated tenant. Confirm archive and restore without source-row/object loss.
8. Review reconciliation, exclusion, lease-recovery, and error metrics.
9. Do not enable production archive until the release gates in section 13 pass.

Never point a backup restore at the active production database or object-store
volume. A failed restore must stop writes and be investigated; it must never be
"fixed" by deleting unknown data.

## 12. Verification

Run focused checks from the repository root:

```bash
backend/.venv/bin/pytest -q backend/tests/integration/test_storage_retention_workflow.py
backend/.venv/bin/ruff check backend/app/system backend/app/deepspace backend/app/documents backend/app/query
cd frontend && pnpm exec tsc --noEmit && pnpm test -- --run
git diff --check
```

The focused retention workflow test covers direct durable-write lifecycle
identities, read-only reconciliation, archive/restore reversibility,
DeepSpace archived-history visibility, and tenant authorization boundaries.

Required staging scenarios:

1. A normal active DeepSpace chat survives navigation, reload, and stream
   reconnect.
2. Queued, paused, failed-retryable, approval-waiting, and active runs are
   excluded from archive.
3. A known inactive conversation archives only in enabled staging mode, moves
   to Archived history, and restores with unchanged messages.
4. A second tenant cannot list, pin, hold, archive, or restore the first
   tenant's data.
5. A worker lease expires mid-scan and a later worker resumes safely without
   duplicate archive decisions.
6. Reconciliation mismatch blocks automatic archive.
7. PostgreSQL and object storage restore together into disposable targets.

## 13. Production go/no-go checklist

Do not enable automatic archive for production until every item is true:

- [ ] All migrations through `20260928_0001_retention_protections_and_run_links`
      are applied and verified.
- [ ] A representative staging tenant has completed preview with reviewed
      reconciliation results.
- [ ] PostgreSQL and matching object-storage backups were restored into an
      isolated staging target successfully.
- [ ] Archive/restore, queue/retry/approval, reload, provider/profile, and
      cross-tenant denial E2E scenarios passed in staging.
- [ ] Worker lease expiry/recovery was tested.
- [ ] Metrics and audit decisions are retained and reviewed.
- [ ] Rollback image and validated recovery pair are available.
- [ ] Permanent purge remains disabled.

## 14. Incident response and rollback

| Symptom | Immediate action |
| --- | --- |
| Reconciliation mismatch | Leave automatic archive disabled for that tenant; inspect the adapter/category mismatch. Do not delete source data. |
| Unexpected archive | Use the authorized restore route; source messages/files should still be present. Record the lifecycle decision ID. |
| Worker failure during scan | Allow the lease to expire or recover it through the service; do not manually modify lifecycle state in SQL. |
| Suspected cross-tenant data access | Disable archive feature flag, preserve logs, rotate affected credentials if needed, and follow the security incident process. |
| Failed migration | Stop rollout, preserve the migration error, return to the previous application image, and do not modify `alembic_version` by hand. |
| Failed backup restore | Keep target isolated, stop writes, retain evidence, and retry only into a new disposable target. |

Archive is reversible in the implemented release. No incident procedure may use
permanent deletion as a remediation shortcut.

## 15. Examples

### Inactive chat

```text
Tenant policy: 30 days
Conversation has no durable write activity for 40 days.
No run, queue, approval, pin, hold, exemption, or active dependency exists.
Staging scan reconciles without mismatch.
→ Lifecycle metadata can become archived.
→ The conversation appears in DeepSpace Archived history.
→ Messages and objects remain unchanged.
```

### Old conversation with active work

```text
Conversation has been quiet for 90 days.
An agent run is waiting for user approval.
→ The protection check excludes it.
→ No archive occurs, regardless of the selected retention age.
```

### User reloads the page

```text
An agent is running. The user opens Settings, reloads, then returns to DeepSpace.
→ The worker and durable run continue server-side.
→ The browser reconnects to the existing conversation/run.
→ This navigation neither archives nor deletes anything.
```

## 16. Related documents

- [DeepSpace retention and cleanup policy](../deepspace/07-deepspace-retention-policy.md)
- [DeepSpace operations runbook](../deepspace/05-deepspace-operations-runbook.md)
- [DeepSpace plans and tenant storage](../deepspace/06-deepspace-plan-storage.md)
- [Storage backup and disaster recovery policy](01-storage-backup-and-disaster-recovery.md)
- [End-to-end implementation and release handoff](../release/01-end-to-end-handoff.md)

The older design notes in the repository root `Docs/` directory are historical
planning records. This guide is the canonical source for the implemented
Storage retention lifecycle and its current production release status.
