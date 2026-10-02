# DeepSpace document attachments and conversion roadmap

**Status:** future roadmap; not a claim that all requested features are
implemented.

This document records three related ideas: direct document context in the
DeepSpace composer, document/PPTX conversion, and richer code or diff display.
It does not replace the current Documents Hub, Library, or DeepSpace contracts.

## Current system truth

### Document context

DeepSpace can already read and compare authorized Library/workspace files
through its existing tools. The Library pipeline remains the source of truth
for upload, malware scanning, extraction, indexing, versions, and access
checks.

A general ChatGPT-style composer attachment workflow that uploads an arbitrary
file and injects its complete raw text into one model request is **not** the
current contract. It must not be added by bypassing the Library or by placing
unbounded document text into a prompt.

Current relevant implementation:

- `backend/app/deepspace/api/library.py`
- `backend/app/deepspace/services/chat_service.py`
- `frontend/app/dashboard/deepspace/_components/DeepSpaceComposer.tsx`
- `frontend/app/dashboard/deepspace/_components/DeepSpaceLibraryDrawer.tsx`
- [`../library/05-documents-production.md`](../library/05-documents-production.md)
- [`../capabilities/02-document-intelligence.md`](../capabilities/02-document-intelligence.md)

### PPTX and document export

PPTX export already exists for supported DeepSpace note/conversation and
Library export flows. The current implementation is not a new generic
`document_convert` tool contract.

Current implementation:

- `backend/app/deepspace/api/export.py`
- `backend/app/deepspace/integrations/export_service.py`
- `backend/app/deepspace/api/library.py`
- `frontend/app/dashboard/deepspace/_components/DeepSpaceEditor.tsx`

Any future conversion feature must extend these existing export paths rather
than create a second storage or conversion system.

### Version and diff behavior

The system already has message/file versions and an authorized
`document_compare` capability that produces bounded exact line comparisons.
A dedicated Documents Hub version-diff screen and semantic version-diff API
described by the former plan are not currently part of the release contract.

Existing relevant behavior includes:

- message version activation in DeepSpace;
- Library file version listing and restore;
- bounded document comparison for authorized files;
- code/text file rendering and diff media types where supported.

## If this roadmap is implemented later

### 1. Safe direct attachments

Use a Library-backed attachment session:

```text
composer selects file
  -> authenticated upload/session
  -> existing MIME, quota, safe-archive inspection, and ClamAV checks
  -> existing extraction and bounded preview
  -> request-scoped authorized context reference
  -> DeepSpace tool/context layer
```

The model must receive only bounded, authorized context. Large documents must
use retrieval, section selection, or an explicit summary flow. Never promise
“100% accurate” raw-document reasoning and never bypass tenant isolation,
malware scanning, quota, or provider context limits.

Potential touchpoints:

- `backend/app/deepspace/api/library.py`
- `backend/app/deepspace/services/chat_service.py`
- `backend/app/ingestion/services/ingestion_service.py`
- `frontend/app/dashboard/deepspace/_components/DeepSpaceComposer.tsx`
- additive upload/attachment schemas and integration tests

### 2. Conversion extensions

Add a conversion only when its input/output contract, size limits, MIME rules,
storage ownership, and worker retry behavior are defined. Reuse the existing
export service and durable artifact/Library job path. Do not add arbitrary
provider URLs, unbounded in-memory conversion, or a second object store.

### 3. Version comparison UI

If a dedicated diff screen is needed, add it as a read-only view over existing
authorized versions. Validate that both versions belong to the same accessible
document/root and bound text, binary, and extracted-content comparisons. Never
show a version the current tenant/user cannot access.

## Required safety and release gates

- Existing single-request uploads and Library flows remain unchanged.
- Uploads remain tenant-scoped, quota-checked, MIME-validated, archive-safe,
  and ClamAV-gated.
- Direct context is bounded and provider-aware.
- Existing DeepSpace queue, streaming, provider, memory, and MCP behavior is
  unchanged.
- New routes use existing authentication and accessibility checks.
- New jobs are idempotent, retryable, and auditable.
- Backend/frontend tests, migration upgrade/rollback checks, tenant-isolation
  tests, storage-failure tests, and browser scenarios pass before release.

## Decision

No implementation should be started from the former plan text alone. The
current implementation documents linked above are authoritative. This file is
only a controlled roadmap for a future, Library-integrated feature.
