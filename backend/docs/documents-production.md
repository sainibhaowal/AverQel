# Documents Hub production contract

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

Document text actions use `POST /deepspace/chats/{conversation_id}/append-content` to append safely
to the authenticated user's active DeepSpace note. If the browser has no valid active note, the
client creates one with `POST /deepspace/chats`. Both routes enforce tenant, user, and conversation
kind ownership.

## Supported formats

The source of truth is `ExtractorRouter.describe_supported_formats()` and the `/documents/supported-formats`
endpoint. Do not hard-code a smaller browser list. Current formats are PDF, TXT, Markdown, OCR image
formats, DOCX/PPTX/XLSX, legacy DOC/PPT/XLS conversion, and the configured code/text extensions.
Unsupported binary, archive, audio, and video payloads are rejected.

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
