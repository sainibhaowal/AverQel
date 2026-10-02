# 07. DeepSpace retention and cleanup policy

> **Canonical guide:**
> [Storage retention lifecycle: production guide](../storage/02-storage-retention-production-guide.md)
> is the authoritative implementation, deployment, safety, and release-gate
> reference. This document remains a concise DeepSpace-specific policy summary.

## Purpose

This document describes what AverQel currently removes automatically and what
must remain available. Changing pages, refreshing the browser, or leaving a
DeepSpace conversation is not a retention event and must not delete a run,
message, queue item, tool result, or activity timeline.

## Current automatic schedules

The Celery beat task `maintenance.retention_cleanup` runs every day at 02:00
UTC. The current defaults are:

- `transient_record_retention_days`: 30 days;
- `audit_log_retention_days`: 90 days.

The daily technical cleanup removes only these completed/temporary records:

- old idempotency keys;
- old completed or failed data-deletion request rows.

Unknown/legacy `deepspace_run_events` and durable context epochs are preserved:
they have no authoritative lifecycle identity and may belong to reconnectable or
retryable work.

The 90-day audit setting applies to old audit events through `AuditService`.

## Records not removed by the current 30-day job

The current retention job does not delete:

- DeepSpace conversations;
- user or assistant chat messages;
- active or queued DeepSpace turns;
- active agent runs;
- saved tool results or artifacts;
- completed chat answers.

Runtime step history is bounded separately by the runtime store's per-run
retention limit. That limit is a storage bound, not a page-navigation cleanup.

## Meaning of “active”

An active run is a run with a live worker heartbeat and a non-terminal runtime
status. Active or queued work must not be deleted because the user visits
another page, reloads, or temporarily loses the browser SSE connection. The
browser is only a viewer; the server worker and durable database records own
the run.

## Storage inactivity policy

Storage now exposes one tenant-scoped setting:

- Off;
- 30 days;
- 60 days;
- 90 days.

The selected age is used by the monthly non-destructive lifecycle scan. The
broader policy is:

> Review data automatically after 30 days with no user activity, tool-call
> activity, queue activity, or active run. Preserve active data and never
> remove it as part of retention cleanup.

The safe foundation is implemented through the Storage policy API, lifecycle
registry, activity hooks, protected preview decisions, and monthly scan.
Metadata-only source archival is enabled only in local/staging when the
explicit `AKS_STORAGE_RETENTION_AUTOMATIC_ARCHIVE_ENABLED=true` flag is set.
It hides eligible DeepSpace conversations from the default history list and
provides a reversible restore action. No source row or object is deleted by
this policy. Production/VPS remains disabled until deployment and external
staging restore verification are complete. Permanent purge is disabled.

1. whether “cleanup” means archive, soft-delete, or permanent deletion;
2. the inactivity timestamp and all activity types that update it;
3. exemptions for active runs, queued turns, approvals, user questions,
   pinned conversations, legal holds, and referenced artifacts;
4. tenant-scoped preview, audit, restore, and rollback behavior;
5. migration, staging, and production tests.

Chat history, files, memory, queries, collections, and artifacts remain in
their source tables and object storage. Existing explicit delete actions remain
the only destructive content actions.

## Operational verification

After changing this policy, run the retention tests and verify that:

- an active run and its event history are preserved;
- a queued turn is preserved;
- a conversation touched by a tool call is preserved;
- an untouched eligible record is handled according to the configured policy;
- cleanup is tenant-scoped and produces an auditable count;
- browser navigation and reload do not trigger cleanup.
