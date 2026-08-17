# AverQel Documents Hub — Advanced Feature Plan

## Purpose

This folder defines the next production update for Documents Hub. It is a delivery plan, not an
implementation claim. Every feature must pass the shared security, tenancy, migration, and release
rules in [00-architecture-and-delivery-plan.md](00-architecture-and-delivery-plan.md).

## Current production foundation

- Authenticated, tenant-scoped upload and document access.
- Idempotent uploads with quota, MIME, extension, archive-safety, and ClamAV checks.
- Private object storage, background extraction/indexing, OCR fallback, chunks, embeddings, SSE
  status updates, versions, raw download, deletion cleanup, and re-ingestion.
- PDF/image preview, safe text preview, DeepSpace note append, and user/editor workspace parity.
- Existing contracts: `backend/app/documents/api/documents.py`,
  `backend/app/ingestion/services/ingestion_service.py`,
  `backend/app/ingestion/services/security/malware_scan_service.py`,
  `frontend/app/dashboard/documents/`, and `frontend/app/dashboard/page.tsx`.

## Release sequence

| Order | Feature | Release intent |
|---:|---|---|
| 1 | Resumable uploads | Reliability for large files |
| 2 | Persistent scan history | Security evidence and auditability |
| 3 | Scan progress events | Transparent live processing |
| 4 | Version comparison | Safe document change review |
| 5 | Bulk upload dashboard | High-volume workspace operations |
| 6 | OCR correction | Better extraction quality |
| 7 | Controlled sharing | Explicit collaboration permissions |
| 8 | Retention and restore | Recoverable lifecycle management |
| 9 | Search and duplicate detection | Faster, cleaner knowledge retrieval |
| 10 | Job monitoring and replay | Operator-grade recovery |

## Non-negotiable outcome

No feature may weaken tenant isolation, user ownership, collection permissions, private storage,
ClamAV fail-closed behavior, encryption, idempotency, existing routes, existing worker contracts,
or the current user/editor/admin permission model.
