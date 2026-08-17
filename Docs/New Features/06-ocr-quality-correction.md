# OCR Quality and Correction Tools

## What to do

Expose OCR confidence by page/region, let users correct extracted text, and preserve both the
original extraction and the approved correction as separate revisions.

## Why to do it

OCR fallback makes scanned documents searchable, but low-confidence names, numbers, and tables
need human review before becoming trusted knowledge.

## Already have

- `ocr_service.py`, extraction coverage, OCR/vision flags, warnings, and quality metrics.
- Safe text preview and re-ingestion.

## Where and how

| Layer | Proposed location / contract |
|---|---|
| Model | `DocumentOcrReview`, `DocumentTextRevision` |
| API | `GET /documents/{id}/ocr/quality`, `PATCH /documents/{id}/ocr/corrections`, `POST /documents/{id}/ocr/reindex` |
| Service | `backend/app/ingestion/services/ocr_review_service.py` |
| UI | `frontend/app/components/dashboard/documents/OcrReviewPanel.tsx` |
| Tests | Preserve original, permissions, concurrent edits, reindex failure, XSS-safe text |

Corrections must be escaped as untrusted text, audit logged, versioned, and explicitly submitted
for reindex. Never overwrite the original file or silently change the source download.
