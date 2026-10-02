# 05. Documents Hub production contract

This contract is the ingestion and storage baseline. The complete additive
Documents Hub feature map—organization, sharing, AI actions, comments,
webhooks, automation, diagnostics, previews, and browser verification—is in
[`07-documents-hub-workflows.md`](07-documents-hub-workflows.md).

The Documents Hub is a tenant-scoped upload, extraction, indexing, preview, and query pipeline.

## Runtime path

1. `POST /api/v1/documents/upload` validates the idempotency key, quota, extension, detected MIME
   type, archive safety, and ClamAV result.
2. The original payload is written to private MinIO storage and a database document plus ingestion
   job are committed.
3. Celery processes extraction, OCR/vision fallback, chunking, and embeddings.
4. The document list receives status updates through a short-lived Redis-backed event-stream ticket
   and SSE. Bearer tokens are not placed in the stream URL.
5. Read, preview, full-text, chunk, version, and download routes enforce tenant and per-user or
   collection accessibility.
6. Delete removes searchable data immediately and deletes the original object. If storage is
   temporarily unavailable, a durable `storage_cleanup_jobs` retry is created.

The upload dialog shows the real request lifecycle at the user boundary: local validation, the
ClamAV security gate, private object storage, and the background indexing queue. The security gate
finishes before the upload response is accepted; a successful upload therefore means the original
file passed the required scan. Existing documents show that gate as the first completed step in the
detail-page ingestion timeline.

The Documents Hub browser can stage one or many files by file picker or drag-and-drop. It validates
each item against the live capability extension list, per-file limit, and estimated tenant quota,
then submits accepted files sequentially. Each request retains its own idempotency key and follows
the exact same authenticated upload, malware scan, audit, and indexing path as a single upload.
Stopping a batch aborts the current browser request and leaves unstarted files staged for retry.

The inventory endpoint also supports additive tenant-scoped filtering through `q`, `status`,
`content_type`, `ocr_used`, `quarantined`, `owner_id`, `created_from`, `created_to`, `skip`, and
`limit`. Filtering never bypasses the existing uploaded-by-user or collection-permission access
query.

## Grounded document queries and cache safety

`POST /api/v1/queries` and `POST /api/v1/queries/stream` run the authenticated user's grounded
query path: accessible documents are resolved first, indexed chunks are searched with the selected
semantic/keyword/hybrid strategy, optional reranking and neighboring-chunk expansion are applied,
and the answer is returned with persisted citations and trace metadata. The query UI uses the same
streaming contract and does not bypass document authorization.

The synchronous RAG cache is intentionally permission-scoped. Its identity includes the tenant,
authenticated user, accessible-document set and document `updated_at` versions, embedding model,
answer model, filters, and search mode. Follow-up turns with conversation history bypass this cache
so prior chat context cannot be replaced by a standalone cached answer. Permission changes,
document deletion, reprocessing, or indexed-content updates therefore select a new cache identity;
old Redis entries expire normally and are never used for the changed scope.

## Organization, versions, actions, and operations

The following capabilities are additive and do not alter the original upload or query contract:

- `GET /documents/duplicates` groups only accessible documents by persisted SHA-256 hash.
- `GET/POST /documents/organization/tags`, `/folders`, and `/saved-views` provide tenant-scoped
  organization primitives. Assignment writes are protected by the same tenant and document
  accessibility checks as inventory reads.
- `GET /documents/{id}/versions/diff?compare_to={id}` compares stored chunk text from the same
  filename lineage. `POST /documents/{id}/versions/{version_id}/restore` creates a new immutable
  ingestion version from the private source object; it never mutates historical content.
- `POST /documents/{id}/actions` provides grounded `summarize`, `extract`, `faqs`, and `compare`
  actions through the existing query/citation pipeline. Each action is persisted with status,
  confidence, citations, and trace identifier and can be retrieved from `/documents/actions/{id}`.
- `GET/POST /documents/{id}/comments` stores tenant-scoped document discussion using the existing
  comment model and validates parent threads. Authors can edit or delete their own comments through
  `/documents/comments/{comment_id}`; cross-user mutation is rejected.
- `GET/POST /documents/{id}/shares` and `DELETE /documents/{id}/shares/{share_id}` manage explicit
  direct reader grants. Only the owner can grant or revoke access; recipients must be active users
  in the same tenant. Shared documents enter the same repository access scope as uploaded and
  collection documents, so download, preview, OCR text, quality, and AI actions remain consistent.
- `POST/GET /documents/{id}/share-links`, `DELETE /documents/share-links/{id}`, and the bearer-only
  resolver `/documents/share-links/{id}/resolve` provide expiring read-only links. Only token hashes
  are persisted; revoked or expired tokens return a generic 404.
- `GET /documents/share-links/{id}/pages/{page}?token=...` uses the same secure PDF/image and
  LibreOffice-to-PDF visual renderer for shared previews without exposing the private source.
- `GET /documents/{id}/quality` reports persisted extraction/OCR/vision evidence, warnings, chunk
  quality, and page gaps. It does not infer quality from configured providers.
- `GET /documents/{id}/pages/{page}` renders an authenticated PDF page from private storage.
- `POST /documents/bulk/resume` preserves committed checkpoints; `POST /documents/bulk/reprocess`
  explicitly starts a clean reprocessing pass; `POST /documents/bulk/tag` and `/bulk/move` are
  idempotent organization writes; `POST /documents/bulk/retry` retries failed states while
  preserving checkpoints; and `POST /documents/bulk/export` creates a private ZIP with a
  50 MiB source-size safety limit.
- `GET /documents/ops/observability` exposes tenant-scoped status counts, active jobs, failures,
  quarantine count, indexed count, and persisted storage totals.
- `GET/POST /documents/webhooks` and `DELETE /documents/webhooks/{webhook_id}` manage tenant-scoped
  document lifecycle subscriptions. Secrets are encrypted with the existing connector-secret
  crypto backend and returned only once at creation. Production endpoints require HTTPS. Events are
  signed with HMAC-SHA256, delivered by the maintenance Celery queue with bounded exponential
  retries, and automatically disabled after repeated failures. Webhook delivery is best-effort and
  cannot fail or roll back ingestion.

Bulk operations are bounded (100 IDs for mutations, 50 IDs for export), return per-document
failures, and never disclose inaccessible IDs beyond a generic failure. Reprocess is intentionally
separate from resume so an operator cannot accidentally delete committed progress.

## Metadata Inspector

`GET /api/v1/documents/{document_id}/status` is the inspector's single source of truth. It is
tenant- and user-scoped, requires `documents:read`, and returns only persisted document, ingestion
job, chunk, and embedding records: file identity, SHA-256 fingerprint, MIME type, size, detected
language, revision and timestamps; extraction method/coverage/fallback flags and warnings; live
job stage/progress/retries/errors; and extracted versus embedded chunk counts with recorded average
chunk quality. The browser refreshes this endpoint while a job is non-terminal. Missing persisted
values must be shown as “Not recorded” or “Not measured”; never substitute a configured provider,
pipeline name, or health value as if it were document-specific evidence.

## Durable ingestion recovery

Embedding progress is committed per batch. Each ingestion job stores a tenant-scoped checkpoint
stage, cursor, timestamp, pause reason, and resume count. `GET /api/v1/documents/{document_id}/status`
reports `recovery_available`, the committed and remaining chunk counts, and the last checkpoint.
When recovery is available, `POST /api/v1/documents/{document_id}/resume` reuses the existing job,
preserves committed chunks and vectors, and queues only missing embeddings. The operation is
idempotent at the chunk level and is protected by the same tenant and `documents:upload`
authorization checks as upload/reingest. Full reingest remains the explicit operation that starts
over and deletes existing chunks/vectors.

## OCR-backed previews

OCR is performed during ingestion for supported image sources and as a fallback for low-text or
image-backed PDF pages when `AKS_OCR_ENABLED=true`. Sparse image-heavy DOCX/PPTX/XLSX files are
also rendered through LibreOffice and sent through the same PDF OCR path. The worker image includes
PaddleOCR's OpenCV runtime libraries
(`libgl1` and `libglib2.0-0`). OCR output follows the same sanitized extraction, chunking,
embedding, and tenant-scoped retrieval path as native text. Reader Mode reconstructs stored chunks
with visible boundaries so OCR text cannot be joined into invented words; Technical Fragments shows
the persisted extraction mode and page metadata when available. While a document is processing,
the detail page uses live events plus bounded reconciliation to refresh both preview modes.

Document text actions use `POST /deepspace/chats/{conversation_id}/append-content` to append safely
to the authenticated user's active DeepSpace note. If the browser has no valid active note, the
client creates one with `POST /deepspace/chats`. Both routes enforce tenant, user, and conversation
kind ownership.

## Supported formats

The source of truth is `ExtractorRouter.describe_supported_formats()` and the `/documents/supported-formats`
endpoint. Do not hard-code a smaller browser list. Current formats are PDF, TXT, Markdown, OCR image
formats, DOCX/PPTX/XLSX, legacy DOC/PPT/XLS conversion, and the configured code/text extensions.
Apple iWork (`.pages`, `.numbers`, `.key`) and WPS (`.wps`, `.dps`, `.et`)
payloads are accepted as download/text-fallback formats. Their package or
binary payload is inspected read-only with strict entry and byte bounds; any
readable text is indexed, while files without safe text are retained as
download-only documents with durable extraction warnings. The original bytes
remain available through the authenticated download route. Unsupported
formats outside the configured allowlist are still rejected.

## Required production services

Production Compose runs `clamav/clamav:1.4.3` on the private network. Set:

```env
AKS_MALWARE_SCAN_ENABLED=true
AKS_MALWARE_SCAN_REQUIRED=true
AKS_MALWARE_SCAN_HOST=clamav
AKS_MALWARE_SCAN_PORT=3310
AKS_MALWARE_SCAN_TIMEOUT_SECONDS=15
```

The readiness endpoint fails when required ClamAV is unavailable. Uploads also fail closed if the
scanner becomes unavailable after startup.

## Safety invariants

- Never remove tenant filters or accessibility checks from document routes.
- Treat extracted content as untrusted text. Escape it before inserting it into note HTML and do
  not render arbitrary extracted HTML in the browser.
- Keep original blobs private; use authenticated download/view routes only.
- Keep idempotency and job/database commits ordered so a queue failure cannot create an untracked
  document.
- Run the focused document tests and the full backend/frontend checks before release.
