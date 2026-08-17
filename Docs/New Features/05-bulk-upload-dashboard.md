# Bulk Upload Progress Dashboard

## What to do

Allow users to select many supported files, submit them with per-file idempotency, and monitor
validation, scan, storage, indexing, retry, and completion states in one queue.

## Why to do it

The current Dropzone handles one file clearly. High-volume users need visibility without opening
each document or triggering a full-page reload.

## Already have

- Supported-format endpoint and quota limits.
- Per-file upload and SSE document updates.
- Dashboard pipeline and Workspace Pulse metrics.

## Where and how

Frontend: `BulkUploadQueue.tsx`, `UploadQueueRow.tsx`, and a queue hook under
`frontend/app/dashboard/documents/`. Keep `POST /documents/upload` canonical; an optional
`POST /documents/upload/batch` must be only a bounded wrapper returning per-file results.

Required states: `waiting`, `validating`, `scanning`, `stored`, `queued`, `indexing`, `complete`,
`blocked`, `failed`, and `cancelled`. Add concurrency limits, pause/resume, retry-one, retry-failed,
clear-completed, and quota projection.

## Tests and safety

Test partial success, duplicate idempotency keys, reconnect, quota exhaustion, cancellation,
tenant isolation, and no duplicate jobs. One failed file must not roll back successful files.
