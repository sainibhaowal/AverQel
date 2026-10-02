# 07. Documents Hub workflows

**Status:** implemented in the current worktree; local API, frontend, and
browser verification completed on 2026-09-27.

The Documents Hub is the tenant-scoped document control plane. It combines
ingestion, extraction, OCR, embeddings, previews, organization, sharing,
comments, AI actions, automation, webhooks, and operational recovery without
changing the existing authentication, storage, or retrieval boundaries.

## Access tiers

The API enforces organization access; frontend visibility is not the security
boundary. Free users have tags and folders. Editors additionally have saved
views, classification rules, and automation schedules. Admins additionally
manage webhooks and delivery history. All operations remain tenant-scoped.

## Capability coverage

| Capability | User value | Durable backend state |
| --- | --- | --- |
| Search and filters | Find documents by text, status, quarantine state, and metadata | Document query and status fields |
| Tags, folders, saved views | Organize documents and preserve repeatable views | `document_tags`, `document_folders`, `document_saved_views` |
| Smart collections | Dynamic rule-based document groups | `document_smart_collections` and live evaluation |
| Duplicate detection | Identify repeated content before it creates noisy retrieval | SHA-256/content duplicate groups |
| Versions | Compare and restore modified uploads | Version and parent-document metadata |
| AI actions | Summarize, extract, compare, and ask grounded questions | Persisted document action records and citations |
| Sharing | Share a controlled document without granting tenant access | Hashed bearer token, expiry, revocation |
| Comments | Discuss documents with tenant-safe mentions | Comment records and mention validation |
| Bulk operations | Retry, resume, reprocess, export, tag, and move many files | Per-document authorization and operation result |
| Quality diagnostics | Explain extraction, OCR, page, and warning quality | Quality report, page numbers, warnings |
| Rich previews | Inspect PDF pages, thumbnails, zoom, and source citations | Authenticated page/thumbnail access |
| Automation | Apply classifications and run scheduled maintenance | Rules and schedule records |
| Webhooks | Notify external systems and inspect delivery attempts | Tenant-scoped durable outbox, signed/idempotent deliveries, retries, status, response code |
| Observability | See queue, failure, quarantine, duplicate, and storage health | Tenant-scoped operational aggregates |

## Backend locations

- `backend/app/documents/api/documents.py` — document list, upload, status,
  recovery, quality, chunks, full text, versions, AI actions, comments,
  sharing, bulk operations, events, and observability.
- `backend/app/documents/api/organization.py` — tags, folders, saved views,
  smart collections, classification rules, and automation schedules.
- `backend/app/documents/models/document.py` — document metadata, versions,
  extraction status, security state, and processing fields.
- `backend/app/documents/models/organization.py` — organization records.
- `backend/app/documents/services/classification_service.py` — shared,
  idempotent rule matching, preview, upload application, and paginated runs.
- `backend/app/documents/services/webhook_security.py` — production endpoint
  validation and SSRF protection.
- `backend/app/documents/workers/` — classification, automation, webhook,
  and document background work.
- `backend/app/ingestion/` — malware scan, extraction, OCR, chunking,
  embedding, checkpointing, and terminal failure handling.
- `frontend/app/dashboard/documents/page.tsx` — list, filters, quarantine
  mode, bulk toolbar, observability counters, upload entry points, and
- `frontend/app/dashboard/documents/organization/` — dedicated organization
  pages for tags, folders, saved views, classification, schedules, webhooks,
  and smart collections.
- `frontend/app/dashboard/documents/organization/SavedViewsPanel.tsx` — saved
  view filter builder, descriptions, readable filter chips, edit/delete,
  access-scoped evaluation results, and Documents Hub navigation.
- `frontend/app/dashboard/documents/organization/ClassificationRulesPanel.tsx` —
  action-aware rule editor, enable/disable, preview, manual run polling, and
  run history.
- `frontend/app/dashboard/documents/organization/AutomationSchedulesPanel.tsx` —
  schedule editor with rule selection, cadence/timezone controls, manual runs,
  enable/disable, and aggregate run history.
- `frontend/app/dashboard/documents/organization/SmartCollectionsPanel.tsx` —
  multi-condition editor, live paginated preview, edit/enable/disable,
  Documents Hub navigation, and evaluation history.
- `frontend/app/dashboard/documents/DocumentOrganizationPanel.tsx` — tags,
  folders, saved views, rules, schedules, webhook management, and delivery
  history.
- `frontend/app/dashboard/documents/[id]/DocumentDetailClient.tsx` — quality
  diagnostics, reader/technical fragments, versions, AI actions, comments,
  share links, thumbnails, page preview, citation navigation, and zoom.
- `frontend/app/share/` — token-resolved shared-document view.

## API contract map

All routes are under `/api/v1`, require the existing authenticated tenant
context unless explicitly marked public, and retain the existing permission
checks.

### Document and processing routes

```text
GET    /documents
POST   /documents/upload
GET    /documents/{document_id}
GET    /documents/{document_id}/status
GET    /documents/{document_id}/quality
GET    /documents/{document_id}/chunks
GET    /documents/{document_id}/full-text
GET    /documents/{document_id}/pages/{page}/thumbnail
GET    /documents/{document_id}/pages/{page}
GET    /documents/{document_id}/download
GET    /documents/events/ticket
GET    /documents/events/stream
POST   /documents/{document_id}/resume
POST   /documents/{document_id}/reingest
```

### Organization and classification routes

```text
GET|POST|PATCH|DELETE /documents/organization/tags[/{tag_id}]
GET|POST|PATCH|DELETE /documents/organization/folders[/{folder_id}]
GET|POST|PATCH|DELETE /documents/organization/saved-views[/{view_id}]
GET    /documents/organization/saved-views/{view_id}/documents
GET|POST /documents/organization/classification-rules
POST   /documents/organization/classification-rules/{rule_id}/preview
POST   /documents/organization/classification-rules/{rule_id}/run
GET    /documents/organization/classification-rules/runs/{run_id}
GET    /documents/organization/classification-rules/{rule_id}/runs
GET    /documents/organization/classification-rules/documents/{document_id}/history
GET|POST /documents/organization/automation-schedules
PATCH|DELETE /documents/organization/automation-schedules/{schedule_id}
POST   /documents/organization/automation-schedules/{schedule_id}/run
GET    /documents/organization/automation-schedules/{schedule_id}/runs
GET    /documents/organization/automation-schedules/runs/{run_id}
GET|POST /documents/organization/smart-collections
PATCH|DELETE /documents/organization/smart-collections/{collection_id}
GET    /documents/organization/smart-collections/{collection_id}/documents
POST   /documents/organization/smart-collections/{collection_id}/evaluate
GET    /documents/organization/smart-collections/{collection_id}/evaluations
```

Saved views persist the supported Documents Hub filter contract: filename
search (`q`), status, content type, OCR state, quarantine state, tag, and
created-date range. Evaluation uses the same access-scoped repository search
as `GET /documents`, so it never expands tenant or user visibility. The UI can
run a view in place or open it in Documents Hub with `?saved_view={id}`.

Classification rules match normalized filenames with a case-insensitive glob
and may require an exact MIME type. The UI requires at least one visible action:
applying a tenant tag or assigning a tenant folder. Uploads evaluate enabled
rules immediately; manual and scheduled runs process every document in
paginated batches. Preview is read-only. Manual and scheduled execution writes
durable run counters and per-document application history, shown on the rule
page and on an accessible document's classification-history panel. A failure
for one document is isolated and does not block ingestion.

Schedules remain backward-compatible with interval-only records. New schedules
can target all enabled rules or an explicit tenant-owned rule set, run hourly,
daily, or weekly in a validated IANA timezone, and expose a preferred local
time. Manual and dispatcher-triggered schedule runs store aggregate counters
and failure details while the underlying rule runs retain their per-rule and
per-document audit trail.

Smart Collections accept up to twelve validated conditions in all/any mode.
Tag and folder references are verified against the active organization. Live
evaluation processes accessible documents in bounded batches and returns
paginated results, so previews do not materialize an entire library in memory.
Explicit preview evaluations persist scanned/matched counts, duration, status,
and failure details. The Documents Hub can open a collection through its
tenant-safe `smart_collection_id` filter; this never expands the viewer's
existing document access.

### Versions, AI, comments, and sharing

```text
GET    /documents/{document_id}/versions
GET    /documents/{document_id}/versions/diff?compare_to={version_id}
POST   /documents/{document_id}/versions/{version_id}/restore
POST   /documents/{document_id}/actions
GET    /documents/actions/{action_id}
GET|POST /documents/{document_id}/comments
PATCH|DELETE /documents/comments/{comment_id}
GET|POST /documents/{document_id}/shares
DELETE /documents/{document_id}/shares/{share_id}
POST   /documents/{document_id}/share-links
GET    /documents/{document_id}/share-links
DELETE /documents/share-links/{share_id}
GET    /documents/share-links/{share_id}/resolve
GET    /documents/share-links/{share_id}/pages/{page}?token={token}
GET    /documents/share-links/{share_id}/download?token={token}
```

Share-link resolution validates the hashed token, tenant-independent link
identity, expiry, and revocation state. The raw token is not stored. A share
link does not grant API access to the tenant or expose unrelated documents.
The page route applies the same token, expiry, and revocation checks before
rendering a PDF, image, or LibreOffice-supported Office/OpenDocument page.
The share download route uses the same checks and returns the original source
file for download/text-fallback formats.

### Bulk, diagnostics, webhooks, and operations

```text
POST   /documents/bulk/retry
POST   /documents/bulk/resume
POST   /documents/bulk/reprocess
POST   /documents/bulk/export
POST   /documents/bulk/tag
POST   /documents/bulk/move
GET    /documents/duplicates
GET    /documents/ops/observability
GET|POST /documents/webhooks
PATCH|DELETE /documents/webhooks/{webhook_id}
POST   /documents/webhooks/{webhook_id}/test
POST   /documents/webhooks/{webhook_id}/rotate-secret
GET    /documents/webhooks/{webhook_id}/deliveries?limit=50&cursor=<opaque>
POST   /documents/webhooks/{webhook_id}/deliveries/{delivery_id}/retry
```

Bulk requests are authorized per document and return accepted/rejected
identifiers rather than silently widening access. Export uses the existing
storage authorization path. Webhook secrets are encrypted at rest; deliveries
are written to a durable outbox before queueing, retried with backoff, recorded,
and visible with status, attempt count, response status, and failure details.
Endpoint creation and every send reject private, loopback, link-local, reserved,
and cloud-metadata addresses; production endpoints must use HTTPS and cannot
contain credentials or fragments. A delivery is unique per tenant,
subscription, and source event ID. Requests include:

```text
X-AverQel-Event-Id
X-AverQel-Timestamp
X-AverQel-Signature-Version: 2
X-AverQel-Signature: sha256=HMAC(secret, timestamp + "." + raw_body)
X-AverQel-Signature-Legacy: sha256=HMAC(secret, raw_body)
```

Receivers should reject timestamps outside a short tolerance (for example five
minutes), verify the raw body with constant-time comparison, and deduplicate
`X-AverQel-Event-Id`. Admins can rotate secrets, retry failed deliveries, pause
or resume subscriptions, and inspect the opaque cursor-paginated history. Ten
consecutive failures or an invalid endpoint automatically pauses a subscription
and exposes the disable reason in the admin UI.

## Ingestion and recovery behavior

The pipeline remains:

```text
upload -> security scan -> extraction/OCR -> chunking -> embedding -> indexed
```

Each recoverable stage writes a checkpoint. A worker failure, provider outage,
ClamAV outage, or process restart records the failure and exposes a resume
action at the last safe checkpoint. Resume is idempotent and does not repeat
completed extraction or embedding work. Terminal failures remain inspectable
and can be retried by an authorized user or bulk operation.

Security scanning, tenant-scoped object keys, encryption, and existing
storage quota enforcement remain mandatory for every upload and recovery path.

## Preview, OCR, and citations

Native PDF text is preferred. OCR is used for pages with insufficient native
text and its method, confidence, warnings, and page coverage are preserved in
the quality report. The detail view exposes reader mode and technical
fragments from the same extracted/indexed content.

PDF thumbnails are fetched through authenticated document routes. A grounded
AI action returns citations with page/chunk metadata. Selecting a citation
opens the matching page preview, loads its thumbnail, and supports bounded
zoom. Missing page mappings remain an explicit citation warning rather than a
fabricated highlight.

## Frontend interaction requirements

- Upload and processing state must remain realtime, but API state remains
  authoritative after reconnect.
- Loading, empty, error, quarantined, and indexed states must be distinct.
- Bulk actions require selected document IDs and preserve per-item results.
- Destructive actions retain confirmation and existing permission checks.
- Light/dark themes use existing semantic tokens; no document metadata is
  rendered outside its authorized tenant or share-link scope.

## Migration order

Apply the ordered migrations through `20261011_0003_webhook_delivery_hardening`.
The Documents Hub additions are:

```text
20261001_0001_document_security_scan_receipts
20261002_0001_ingestion_checkpoints
20261003_0001_document_organization
20261004_0001_document_shares
20261005_0001_document_webhooks
20261006_0001_document_links_and_ai
20261007_0001_document_automation
20261008_0001_comment_mentions
20261009_0001_document_webhook_deliveries
20261010_0001_document_smart_collections
20261011_0001_webhook_attempt_history
20261011_0002_smart_collection_evaluations
20261011_0003_webhook_delivery_hardening
```

Never start workers against an unmigrated database. Use `alembic upgrade head`
from the release image and verify the resulting head before serving traffic.

## Verification

The dedicated browser suite is
`frontend/e2e/documents-hub-workflows.spec.ts`. It covers quarantine review,
webhook delivery history, secure share-link resolve, and citation page
preview/zoom. It runs with deterministic API contract fixtures so the browser
workflow is repeatable without mutating a real tenant; backend integration
tests cover the live API and persistence contracts. Webhook-specific backend
coverage is in `backend/tests/unit/test_webhook_security.py`,
`backend/tests/unit/test_webhook_worker.py`, and
`backend/tests/integration/test_webhooks_security.py`.

The local verification completed on 2026-09-27:

- Playwright: **10 passed, 0 skipped**.
- Frontend Vitest: **88 files, 325 tests passed**.
- Backend pytest: **full serial suite passed**.
- Frontend production build: passed.
- Python compilation and `git diff --check`: passed.

For deployment validation, repeat the same checks against an isolated staging
tenant with real storage, workers, OCR, malware scanning, and provider
credentials. Do not claim external production proof from fixture-backed UI
tests alone.
