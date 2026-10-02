# 09. Documents Hub user guide

This guide describes what a user sees and how the complete Documents Hub
workflow behaves. It is the user-facing companion to the implementation and
API contract in [`07-documents-hub-workflows.md`](07-documents-hub-workflows.md)
and the ingestion operations guide in
[`08-ingestion-recovery-security-observability.md`](08-ingestion-recovery-security-observability.md).

## Before and now

### Before

The original surface provided a basic document list and upload entry point,
simple preview, basic processing status, and limited metadata. It did not
provide a complete quarantine review, webhook delivery history, expiring
share-link workflow, citation-to-page preview, or full organization controls.

### Now

Documents Hub is a tenant-scoped document workspace. A user can move through
the full lifecycle:

```text
upload -> security scan -> extraction/OCR -> chunking -> embedding -> indexing
       -> preview -> organize -> ask AI -> share/collaborate -> monitor/recover
```

The existing authentication, tenant isolation, permission, storage,
encryption, retrieval, realtime, provider, and DeepSpace chat boundaries stay
in place.

## What users see

### Documents Hub home

The home screen provides:

- document search and filters;
- filename, file type, owner, date, status, OCR, and quality information;
- progress and current pipeline stage;
- indexed, failed, queued, processing, and quarantined counts;
- quarantine indicators and a quarantine-review entry point;
- bulk selection and bulk action controls;
- organization controls for tags, folders, saved views, smart collections,
  classification rules, schedules, and webhooks;
- operational observability for document, queue, failure, quarantine, and
  storage state.

Loading, empty, error, processing, quarantined, failed, and indexed states are
visually distinct. Realtime updates refresh the screen, while an API refresh
after reconnect remains authoritative.

### Upload and drag-and-drop

Users can upload one file, multiple selected files, or a batch dragged onto
the upload area. Before starting, the interface shows the selected filenames,
count, supported-format validation, size errors, and unsupported-file errors.

During upload, each file has its own progress, cancel, retry, and result state.
The user can continue using the workspace while the batch is processed. Every
accepted file enters the same secure ingestion and Library lifecycle; a file
is not treated as complete until the backend confirms its state.

### Processing and recovery

The status pipeline shows validation, security scan, malware scan, private
storage, extraction/OCR, chunking, embedding, and indexing. It also shows the
percentage, active stage, failure reason, and checkpoint when available.

If a worker, server, scanner, provider, or network problem pauses processing,
the UI exposes a resume or retry action at the last durable checkpoint. The
system does not require the user to re-upload or repeat completed extraction
or embedding work. Resume is idempotent and remains protected by the same
tenant and permission checks.

### Document detail

The detail screen contains Reader Mode and Technical Fragments. It exposes:

- extracted and OCR-derived content;
- extraction method, OCR/vision usage, and coverage;
- warnings, anomalies, and page diagnostics;
- chunks, embeddings, and indexing state;
- SHA-256 fingerprint and tenant-isolation status;
- version history and comparison/restore controls;
- security, storage, and recovery information.

### PDF and rich preview

For supported PDFs, users can open page thumbnails, navigate pages, zoom with
bounded controls, and open a larger page preview. An AI citation can be
selected to open its source page and chunk context. When exact page/text
mapping is unavailable, the UI shows a source-mapping warning instead of
inventing a highlight.

### OCR and quality

Native text is preferred. OCR is used when native page text is insufficient.
The result preserves OCR usage, coverage, confidence/warnings where provided,
page numbers, missing-page diagnostics, and extraction anomalies. Reader Mode
and Technical Fragments use the same extracted/indexed source so the preview
does not display unrelated or fabricated content.

### AI document actions

Users can run grounded actions such as summarization, question answering,
structured extraction, document comparison, and quality review. Results show
the answer, processing state, citations, page/chunk references, and persisted
action history where available. Actions remain document- and tenant-scoped.

### Organization, plan access, and bulk workflows

The API and UI enforce these Documents Hub organization tiers:

| Access level | Organization features |
| --- | --- |
| Free/user | Tags and folders |
| Editor | Free features plus saved views, classification rules, and automation schedules |
| Admin | Editor features plus webhook administration/delivery history and administrative document controls |

Admins can create Smart Collections with `all` or `any` conditions such as
failed status, quarantine state, OCR coverage, filename/content type, tag, or
folder. The collection is evaluated when opened, so membership updates as
documents change; it does not copy or move documents.
Bulk actions support retry, resume,
reprocess, export, move, tag, and quarantine review. Each selected document is
authorized independently and the result reports accepted and rejected items.

The Documents Hub cards are quick controls. Each organization capability also
has a dedicated management page:

- `/dashboard/documents/organization/tags` — create labels and select files to tag.
- `/dashboard/documents/organization/folders` — create folders and select files to move.
- `/dashboard/documents/organization/saved-views` — manage reusable views.
- `/dashboard/documents/organization/classification-rules` — configure and remove rules.
- `/dashboard/documents/organization/automation-schedules` — configure and remove schedules.
- `/dashboard/documents/organization/smart-collections` — define live all/any conditions and inspect matching counts.
- `/dashboard/documents/organization/webhooks` — manage endpoints and inspect delivery history.

The same backend permission and tenant checks protect both the quick controls
and dedicated pages.

Duplicate detection groups matching content/fingerprints. Version controls
show previous versions, comparisons, and restore. Restore creates a controlled
new lifecycle state; it does not silently overwrite unrelated documents.

### Sharing and comments

Users can grant direct access or create an expiring share link. Links can be
revoked and resolved only while valid. The raw bearer token is not stored as
plain data, and a link cannot grant access to unrelated tenant documents.

Users can add comments, edit or delete their permitted comments, and use
validated mentions where enabled. Sharing and comment operations remain
permission-checked and auditable.

### Webhooks and automation

Admin-only organization controls show configured webhooks and their delivery history,
including event type, status, HTTP response code, attempt count, retry state,
failure details, and a durable retry timeline. Admins can edit an endpoint,
pause/resume delivery, and queue a signed test delivery. A newly created
webhook displays its secret once in an AverQel secure copy dialog; the secret
is encrypted at rest and is never returned by later list or update calls.

Classification rules and schedules let users apply repeatable processing or
organization behavior. Automation runs through the existing background-job
and permission boundaries rather than bypassing normal ingestion.

### Quarantine review

Users can filter quarantined documents, inspect the reason and security state,
then approve/release, reject/purge, or review multiple items in a batch.
Destructive actions retain confirmation. A quarantined item is not presented
as healthy merely because no failure was recorded.

### Folder explorer

The Folders page is a file-explorer workspace rather than a folder settings
form. The sidebar shows nested folders and an Unfiled files root. Users can
create, rename, and delete folders, open a folder to see its files, select
multiple files, move them by named destination, and open each file through the
existing Documents Hub preview route. The Add files and Add here controls
support multi-file uploads. Local files can also be dropped into the open
folder or directly onto a sidebar folder; existing document rows can be
dragged onto a folder to move them. Upload and move operations continue to use
the existing tenant-scoped upload and bulk-move APIs.

### Responsive visual behavior

The UI adapts to desktop, tablet, mobile, narrow panels, light mode, and dark
mode. Controls use semantic theme tokens, readable contrast, centered icons,
wrapped content, rounded tooltips, accessible names, and restrained hover and
click motion. All user input, confirmation, secret-copy, and error dialogs use
the native AverQel themed modal surface; browser-native prompt/confirm/alert
popups are not used. The layout avoids unnecessary horizontal scrolling.

## What remains unchanged

The Documents Hub does not replace or weaken existing platform behavior:

- authentication and session handling;
- tenant isolation and authorization;
- encryption, secret handling, and cryptographic boundaries;
- object-storage and quota contracts;
- ingestion, OCR, embedding, retrieval, and realtime events;
- existing API compatibility and background jobs;
- provider and MCP connections;
- DeepSpace chat, composer, Library attachment, and queue behavior.

## Production operation

The feature set is locally verified with backend pytest, frontend Vitest,
Playwright browser tests, Ruff, mypy, ESLint, TypeScript, production build,
Python compilation, and whitespace checks. Deployment still requires the
environment-specific release gates: `alembic upgrade head`, healthy workers,
real object storage, OCR, malware scanning, external provider credentials,
and authenticated staging validation.

See [`../platform/04-end-to-end-verification.md`](../platform/04-end-to-end-verification.md)
for the current evidence and [`../release/01-end-to-end-handoff.md`](../release/01-end-to-end-handoff.md)
for release procedures.
