# Advanced Search and Duplicate Detection

## What to do

Provide permission-aware filters, facets, saved searches, exact duplicate detection, and optional
near-duplicate suggestions.

## Why to do it

Documents Hub already supports vector and full-text retrieval. Users need faster narrowing and a
cleaner knowledge base before adding more content.

## Already have

- Vector and BM25 methods in `backend/app/documents/repositories/chunks.py`.
- SHA-256 on every document and tenant/accessibility filters.
- Query grounding through existing document retrieval.

## Where and how

Add `GET /documents/search` with bounded parameters: `q`, status, content type, owner, collection,
created range, updated range, OCR flag, warning flag, and duplicate group. Add
`POST /documents/{id}/duplicate-actions` for review/keep/archive decisions.

Services: `advanced_search_service.py`, `duplicate_detection_service.py`; models:
`DocumentDuplicateGroup`, `SavedDocumentSearch`; UI: `DocumentSearchBar.tsx`, filter drawer,
duplicate review panel, and URL-synced state.

Exact duplicates use SHA-256. Near duplicates use normalized text fingerprints or embeddings only
as a review suggestion; never auto-delete. Search results must apply the same access check as full
text and query retrieval.
