# Native OCR Providers and Quality Correction

## What to do

Make OCR a first-class provider capability. Administrators should configure native OCR engines in
Provider Settings, and users should choose an approved OCR mode in the Documents upload flow.

Initial native engine: **PaddleOCR**. The contract must support future engines such as Tesseract,
EasyOCR, OCRmyPDF, or a controlled remote OCR API without changing upload routes or document
security rules.

## Why to do it

Different documents need different OCR strengths: PaddleOCR for local multilingual recognition,
Tesseract for lightweight CPU fallback, OCRmyPDF for searchable PDFs, and optional remote engines
for specialized layouts. Provider selection must never create uncontrolled external data sharing.

## Already have

- `backend/app/ingestion/services/ocr_service.py` with native PaddleOCR execution.
- `backend/app/ingestion/services/extractors/image_ocr_extractor.py` for image uploads.
- PDF OCR fallback through the ingestion pipeline.
- Environment controls in `backend/app/core/config.py`: `ocr_enabled`, `ocr_engine`, device,
  timeout, page/pixel limits, languages, confidence threshold, and retries.
- Provider control plane under `backend/app/providers/`: configs, assignments, secrets, health,
  encrypted secret storage, and `/providers/*` APIs.
- Upload capabilities at `GET /capabilities` and the format-aware upload UI.
- Existing quality fields: coverage, OCR/vision flags, warnings, and re-ingestion.

## Target provider architecture

OCR providers use a dedicated capability contract. Do not place OCR engines in the LLM, embedding,
or reranking provider lists.

```text
Provider Settings
  -> OCR provider config + encrypted secret + health check
  -> tenant/workspace OCR assignment and fallback order
  -> OCRProviderRegistry
  -> OcrService
  -> image/PDF extractor
  -> quality record + chunks + embeddings
```

Proposed interface: `OcrProvider.extract(request) -> OcrResult`, returning text, page/region
confidence, detected language, layout blocks, tables when available, engine/version, and warnings.
Each provider declares local/remote mode, languages, PDF/layout/table support, CPU/GPU mode,
payload limits, and estimated cost.

## Exact implementation plan

| Area | Existing / proposed location |
|---|---|
| Provider model | Extend `backend/app/providers/models/provider_config.py` with OCR capability metadata, or add `ProviderCapability` if shared flags become too broad |
| Assignment | Extend provider assignments with feature scope `ocr` and ordered fallback priority |
| Registry | Add `backend/app/ingestion/services/ocr_provider_registry.py` |
| Adapters | Add `backend/app/ingestion/services/ocr_providers/paddleocr_provider.py`, `tesseract_provider.py`, and future tested adapters |
| OCR service | Refactor `backend/app/ingestion/services/ocr_service.py` to resolve approved assignment, enforce limits, and record the selected provider |
| Provider API | Extend `backend/app/providers/api/providers.py` and schemas with OCR capability/config validation |
| Settings UI | Extend `frontend/app/dashboard/settings/providers/` with OCR category, health, language/device/model controls, and fallback order |
| Upload UI | Extend `UploadModal.tsx` and `Dropzone.tsx` with Workspace default, PaddleOCR, approved fallback, and Auto modes |
| Metadata | Add `ocr_provider`, `ocr_model_version`, `ocr_languages`, and `ocr_mode` to document status/metadata |
| Quality review | Add `DocumentOcrReview`, `DocumentTextRevision`, `ocr_review_service.py`, and `OcrReviewPanel.tsx` |
| APIs | `GET /documents/{id}/ocr/quality`, `PATCH /documents/{id}/ocr/corrections`, `POST /documents/{id}/ocr/reindex` |
| Migration | Add a reversible Alembic migration; existing rows use `legacy_unknown` provider metadata |
| Tests | Provider contract, PaddleOCR, fallback, health, selection, policy, timeout, limits, correction, reindex, and XSS tests |

## Upload behavior

1. The UI loads approved OCR capabilities from `/capabilities` and provider assignment APIs.
2. The user selects an allowed mode or keeps the workspace default.
3. The request carries an OCR preference, never credentials or arbitrary provider URLs.
4. The backend validates tenant policy, file limits, MIME, archive safety, and ClamAV first.
5. The worker resolves the provider server-side and records the actual engine used.
6. Auto mode may use only the configured fallback order.
7. The document records confidence, warnings, engine/version, and fallback usage.

## Security and privacy rules

- Local PaddleOCR/Tesseract processing remains the default for private documents.
- Remote OCR is disabled by default and requires tenant/admin allowlisting, data-region policy,
  health checks, cost limits, and an audit event.
- Never accept a provider URL or model path from the upload form.
- Provider secrets remain encrypted and masked through the existing provider secret service.
- OCR output is untrusted text: escape previews/notes and sanitize correction input.
- Preserve the original file and original extraction; corrections create a new text revision.
- Query, full-text, download, and correction routes use existing accessibility checks.

## Must not break

- `POST /documents/upload` remains compatible; OCR preference is optional.
- Existing PaddleOCR environment configuration continues to work during migration.
- ClamAV scanning always happens before OCR and storage acceptance.
- OCR failure cannot create a searchable partial document.
- PDF/image extraction, quality scores, re-ingestion, SSE status, and raw downloads remain available.
- Admin-only provider settings stay restricted; users only choose policy-approved modes.

## Release gates

Before enabling an engine: reproducible package/container, model checksum verification, license
review, cold-start and memory measurements, CPU/GPU compatibility, timeout tests, poisoned-input
tests, language fixtures, tenant-isolation tests, health checks, migration rollback, and a canary
with remote OCR disabled.
