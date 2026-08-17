# Document Version Comparison

## What to do

Compare two accessible versions of the same document and show additions, removals, changed
sections, metadata changes, and extraction differences.

## Why to do it

Version history currently proves that versions exist. A diff lets users review changes before
trusting a new index or sharing an updated source.

## Already have

- `GET /documents/{id}/versions`.
- `parent_document_id`, `version`, and SHA-256 on `Document`.
- Full-text and chunk preview routes.

## Where and how

| Layer | Proposed location / contract |
|---|---|
| API | `GET /documents/{id}/versions/diff?from={uuid}&to={uuid}&mode=semantic` |
| Service | `backend/app/documents/services/version_diff_service.py` |
| DTO | `DiffSummary`, `DiffHunk`, `MetadataChange` in `backend/app/documents/schemas/` |
| UI | `frontend/app/components/dashboard/documents/DocumentVersionDiff.tsx` |
| Large files | Celery job with a cached, expiring result |
| Tests | Same-root validation, access control, deleted versions, text/binary fallback |

Use line diff for text and chunk/section diff for extracted documents. Never compare or reveal a
version the current user cannot access.

## Must not break

Existing version upload, retrieval, query, and download behavior remains unchanged.
