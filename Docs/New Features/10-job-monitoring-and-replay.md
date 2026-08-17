# Background Job Monitoring and Failure Replay

## What to do

Create an operator view for ingestion jobs, attempts, stage duration, errors, dead letters, and
safe replay without duplicating documents or bypassing security gates.

## Why to do it

The pipeline already records retries, stages, attempt counts, and dead-letter state. Operators need
one reliable view to diagnose and recover failures.

## Already have

- `IngestionJob` and `IngestionJobsRepository`.
- Celery ingestion worker, retry backoff, dead-letter state, and re-ingestion route.
- Dashboard active-job and pipeline metrics.

## Where and how

Add admin-only routes:

- `GET /admin/ingestion/jobs` with tenant-safe filters and pagination.
- `GET /admin/ingestion/jobs/{id}` with stage timeline and safe error details.
- `POST /admin/ingestion/jobs/{id}/replay` with idempotency and reason.
- `POST /admin/ingestion/jobs/{id}/cancel` where cancellation is safe.

Touchpoints: `backend/app/ingestion/repositories/ingestion_jobs.py`, worker tasks, metrics,
`backend/app/system/api/admin.py`, `frontend/app/dashboard/admin/`, and audit logging.

Replay must preserve the original error, enforce access, and use the existing queue. Never let a
replay create a second document, bypass ClamAV, or expose another tenant's filenames/content.
