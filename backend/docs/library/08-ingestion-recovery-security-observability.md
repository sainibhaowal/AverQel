# 08. Ingestion recovery, security, and observability

This document describes the durable operational contract behind Documents Hub
processing. It is intentionally separate from the UI capability catalog so
operators can diagnose a stalled or failed document without guessing.

## State model

The authoritative document status is persisted in PostgreSQL. Worker progress
is represented by the document status, ingestion job, stage progress,
checkpoint, attempt count, last error code/message, and terminal timestamps.
The frontend may receive faster SSE updates, but a REST refresh always wins
after reconnect or a missed event.

Typical stages are:

```text
queued -> security_scan -> downloading -> parsing -> chunking -> embedding -> indexed
                         \-> quarantined
                         \-> failed/dead_lettered
```

The exact stage names are backend-owned. Clients must treat unknown stages as
non-terminal and display the server-provided message rather than inventing a
healthy state.

## Recovery contract

1. A worker writes a checkpoint only after the stage's durable output is safe.
2. A retry increments the attempt count and preserves the prior error.
3. A resume starts at `recovery_stage` or the next incomplete unit, not at
   upload.
4. A repeated failure becomes terminal/dead-lettered according to configured
   attempt limits.
5. Authorized users can resume one document or use bulk retry/resume.
6. Every action remains tenant-scoped and idempotency-aware.

The recovery UI must show the reason, last checkpoint, remaining work, and a
clear action. “Processing” must never be shown when the API reports a terminal
failure or an unavailable recovery checkpoint.

## Security scan behavior

Uploads are scanned before they become available for normal retrieval. Scan
receipts contain the result, scanner metadata, and timestamp without storing
the file contents in logs. If ClamAV is unavailable, the configured policy
determines whether the document is quarantined or the upload fails; the system
must not silently mark an unscanned file healthy.

The security boundary includes:

- authenticated tenant and user context;
- tenant-scoped database queries and object-storage keys;
- encrypted provider/webhook secrets;
- path-safe filenames and bounded upload size;
- no prompt, file body, token, or bearer share token in logs;
- explicit authorization for download, preview, sharing, comments, and bulk
  operations.

## Quality and page diagnostics

The quality report exposes extraction method, coverage score, OCR/vision usage,
warning codes, total chunks, low-quality chunks, detected page numbers, and
missing pages. These are observations, not invented confidence claims. A low
score or fallback warning remains visible after embedding and indexing.

Operators should inspect, in order:

1. security result and quarantine reason;
2. extraction method and warning codes;
3. OCR confidence/page coverage;
4. chunk count and low-quality chunks;
5. embedding/indexing terminal state;
6. provider, queue, and storage health.

## Observability

`GET /api/v1/documents/ops/observability` returns tenant-safe aggregate counts
for status, active jobs, failures, quarantine, indexed documents, total
documents, and storage bytes. `GET /api/v1/documents/duplicates` returns
duplicate-group information without exposing another tenant's content.

The admin metrics endpoint remains separate from document content. Metrics may
contain low-cardinality operational labels, but must not contain prompts,
answers, extracted text, filenames, secrets, or raw provider reasoning.

## Operational checklist

- Confirm `alembic current` is at `20261009_0001` or later.
- Confirm API, worker, ingestion-worker, maintenance-worker, and scheduler
  use the same release and environment configuration.
- Check `/api/v1/health/live` and `/api/v1/health/ready`.
- Inspect failed/dead-lettered jobs and recovery checkpoints.
- Confirm ClamAV, PostgreSQL, Redis, and object storage are reachable.
- Check queue depth, failure rate, processing latency, and storage quota.
- Re-run the affected document with resume/retry before deleting it.
- Preserve the document ID, trace ID, error code, and checkpoint time for
  support; never copy file contents or credentials into an incident ticket.
