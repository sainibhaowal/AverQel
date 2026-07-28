# AverQel OCR

AverQel uses PaddleOCR's current OCR pipeline for image OCR and scanned PDF
pages. The current PaddleOCR pipeline selects the latest PP-OCR model family
(PP-OCRv6) by default.

## Scope

The OCR replacement is intentionally limited to the OCR adapter:

```text
image or scanned PDF page -> PaddleOCR/PP-OCRv6 -> extracted text
```

The following remain unchanged:

- native PDF text extraction with `pypdf`;
- Markdown, text, and code extraction;
- DOCX, PPTX, and XLSX parsers;
- legacy Office conversion;
- malware scanning, storage, tenant isolation, and ingestion jobs;
- chunking, embeddings, and RAG indexing.

Normal text PDFs are not sent through OCR because direct extraction preserves
text and symbols more accurately. OCR is used when a PDF page has insufficient
native text and is rendered as an image.

## Runtime requirements

The default device is CPU (`ocr_device=cpu`). MKL-DNN is disabled by default
(`ocr_enable_mkldnn=false`) for compatibility across CPU runtimes. The
PaddleOCR model is loaded lazily by the ingestion worker on the first OCR
request and reused by later requests in that worker process. Model
initialization is not included in the per-image OCR timeout. OCR errors preserve the existing
`OCR_UNAVAILABLE`, `OCR_TIMEOUT`, and `OCR_FAILED` error contract.

PaddleOCR downloads its model the first time it is used. Production images
should be allowed to reach the configured model source during deployment, or
the official PP-OCR model files should be preloaded into the runtime model
cache before workers process uploads.

## Validation

Before deployment, test representative:

- clean and noisy image scans;
- scanned and born-digital PDFs;
- multilingual pages;
- large and dimension-limited images;
- failed, timed-out, and empty OCR results.

The OCR adapter must continue returning text, confidence, and warnings through
the existing `OcrResult` contract so downstream chunking, embeddings, and RAG
behavior do not change.
