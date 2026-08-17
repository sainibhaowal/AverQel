# Shared Architecture and Delivery Rules

## What to do

Add the ten features as small, reversible vertical slices. Each slice must include its migration,
service, API contract, UI state, tests, documentation, metrics, and rollback flag before release.

## Why

Documents Hub already handles private files and asynchronous work. Advanced features must extend
that pipeline without creating a second storage, authorization, or job system.

## Existing contracts to extend

| Area | Current location | Rule |
|---|---|---|
| Document API | `backend/app/documents/api/documents.py` | Keep `/documents/*` compatibility |
| Document model | `backend/app/documents/models/document.py` | Add nullable fields first; backfill safely |
| Ingestion | `backend/app/ingestion/services/ingestion_service.py` | Preserve stage and retry semantics |
| Jobs | `backend/app/ingestion/models/ingestion_job.py` | Reuse tenant-scoped job identity |
| Storage | `backend/app/system/services/storage_service.py` | Never expose raw object keys |
| Security | `backend/app/ingestion/services/security/` | Fail closed when required |
| Events | `/documents/events/ticket`, `/documents/events/stream` | Keep short-lived tickets; no bearer URLs |
| Frontend | `frontend/app/dashboard/documents/` | Preserve safe previews and partial loading |
| Migrations | `backend/alembic/versions/` | One reversible migration per schema slice |

## Standard request flow

```text
authenticated request
  -> tenant scope + permission check
  -> domain service
  -> transaction and idempotency record
  -> private storage / Celery job / Redis event
  -> response DTO
  -> audit event + metrics
```

## Required safety checks

- Every query includes tenant scope and the existing accessibility rule.
- Collection shares must use collection permissions; do not invent an unscoped document ACL.
- All object names remain server-generated and private.
- Every mutating route accepts an idempotency key where retries can duplicate work.
- Large payloads are streamed or bounded; never load untrusted unlimited data into memory.
- New events are additive and versioned. Unknown events must be safely ignored by old clients.
- Rollouts use feature flags and metrics. Backfills are resumable and do not delete source data.

## Release gates

Backend unit/integration tests, frontend tests, migration upgrade/downgrade checks, Ruff,
TypeScript, production build, Compose validation, tenant-isolation tests, storage-failure tests,
worker retry tests, and manual browser scenarios must pass before tagging.
