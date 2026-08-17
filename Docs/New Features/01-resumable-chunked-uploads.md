# Resumable and Chunked Uploads

## What to do

Support large files through an authenticated upload session and fixed-size parts, then assemble
the object server-side before the existing validation, ClamAV, storage, and ingestion flow.

## Why to do it

Large uploads fail when a browser loses connectivity. Resuming only missing parts improves
reliability without weakening the current upload contract.

## Already have

- `POST /documents/upload` with `Idempotency-Key`.
- Quota and maximum-size validation in `IngestionService`.
- Private storage via `StorageService`.
- Frontend `Dropzone.tsx`.

## Where and how

| Layer | Proposed location / contract |
|---|---|
| Models | `DocumentUploadSession`, `DocumentUploadPart` in `backend/app/documents/models/` |
| API | `POST /documents/uploads`, `PUT /documents/uploads/{id}/parts/{number}`, `POST /documents/uploads/{id}/complete`, `DELETE /documents/uploads/{id}` |
| Service | `backend/app/documents/services/resumable_upload_service.py` |
| UI | `frontend/app/components/dashboard/documents/ResumableUploadQueue.tsx` |
| Tests | Replay, missing part, checksum mismatch, expiry, abort, quota, tenant isolation |

## Safe flow

1. Create a session with filename, size, content type, SHA-256, part size, and expiry.
2. Upload each part with checksum and idempotent part number.
3. Complete only when all parts exist and the assembled SHA-256 matches.
4. Run existing MIME, archive, and ClamAV checks on the assembled stream.
5. Create the normal document/job only after those checks pass.

## Must not break

The current single-request upload remains supported. An incomplete session must not appear in
Documents Hub, count as permanent storage, or become downloadable.
