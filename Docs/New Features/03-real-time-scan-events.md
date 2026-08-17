# Real-Time Security and Ingestion Events

## What to do

Publish versioned security events so the UI shows actual backend transitions instead of a
client-only animation.

## Why to do it

Users need to know whether a file is validating, scanning, stored, queued, blocked, or indexed.
The existing document SSE is the correct secure transport.

## Already have

- Redis-backed ticket at `GET /documents/events/ticket`.
- Secure stream at `GET /documents/events/stream`.
- Stages: queued, downloading, parsing, chunking, embedding, indexed.

## Where and how

Extend the event payload with `schema_version`, `phase`, `status`, `progress`, `document_id`,
`scan_id`, `updated_at`, and safe `message_code` fields. Add phases:
`validating`, `scanning`, `stored`, `queued`, `indexing`, `blocked`, `completed`, `failed`.

Touchpoints: `IngestionService`, `MalwareScanService`, Redis publisher, document status schema,
`DocumentsPage`, `DocumentDetailClient`, and SSE integration tests.

## Accuracy rules

- Emit `scanning` only after the backend enters ClamAV scanning.
- Do not fabricate percentage during a scanner operation without byte-level progress.
- Reconnect from the last event ID and finish from `/documents/{id}/status`.
- Old clients ignore unknown phases; new clients recover through polling.

## Must not break

Tickets remain short-lived, one-time, tenant-bound, and free of bearer tokens in URLs.
