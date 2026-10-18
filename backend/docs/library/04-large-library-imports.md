# 04. Large Library imports and safe data previews

## Purpose

This feature lets users import supported files up to the configured 25 MiB
limit without allowing a large CSV, TSV, JSON, spreadsheet, or document to
block DeepSpace chat, the API, or the browser interface.

## What happens

```mermaid
flowchart LR
    U[User selects a file] --> B[Chunked browser upload]
    B --> S[Private upload chunks]
    S --> Q[Dedicated library_uploads queue]
    Q --> W[Fast file-publication worker]
    W --> O[Private object storage]
    W --> X[Completed Library attachment]
    X --> E[Separate extraction and media queues]
    E --> P[Bounded extracted preview]
    P --> L[Library preview / RAG]
    O --> D[Authenticated download / sandbox]
```

1. The browser uploads in 2 MiB resumable chunks.
2. Files larger than 2 MiB upload one at a time from a browser tab. Small
   batches retain limited parallel upload behavior.
3. The `library-worker` assembles and stores the verified original, then marks
   the upload complete. It does not run OCR or document parsers and does not
   keep the upload database row locked during object-storage I/O.
4. OCR, document extraction, and media manifests run on the separate
   `library-processing-worker`. A slow parser cannot keep an image or file
   stuck in the upload state or block cancellation.
5. Text data over 512 KiB is retained as a private object rather than copied
   into PostgreSQL and browser editor state. The original can still be
   downloaded or used by the authorized sandbox.
6. CSV previews show at most 200 rows, 50 columns, and 512 KiB of text.
   This prevents a million-row file from creating millions of browser DOM
   elements. The interface clearly labels such a view as a safe preview.

## User experience

- The attachment becomes available to chat as soon as its bytes are safely
  stored. The composer may show **Uploaded · reading text** while optional
  extraction continues; supported images can be sent to a vision-capable model
  during OCR.
- A 4–25 MiB CSV shows upload completion independently from its profile and
  extraction status while the rest of AverQel remains usable.
- The Library displays a compact first-page table, rather than trying to
  render the complete dataset.
- Large files are read-only in the in-browser editor. Use **Download** for
  the original file or ask DeepSpace to analyze the authorized file through
  the sandbox.
- Small text and CSV files remain directly editable as before.

## Security and limits

1. Existing authentication, tenant, user, conversation, and folder ownership
   checks run before every upload, status read, preview, download, and
   sandbox hand-off.
2. File size remains capped by `AKS_UPLOAD_MAX_BYTES` (25 MiB by default).
3. Data stays in tenant-scoped private object storage; no storage URL is sent
   to the browser.
4. Extraction of large CSV/TSV/JSON inputs is bounded to a completed record
   near the 512 KiB limit. This is enough for preview/RAG context while the
   complete source remains available to the sandbox.
5. Upload chunks are deleted after completion, cancellation, or failure.

## Verification

1. Upload an image and a 9 MiB CSV. Both should become attachable after secure
   storage; OCR/extraction status can finish separately without freezing the
   DeepSpace tab.
2. Open the large CSV. Confirm that the banner says it is a safe preview and
   no more than 200 rows are rendered.
3. Download the same file and verify its checksum/size matches the original.
4. Ask: `Analyze the uploaded CSV and calculate the average of column X.`
   The sandbox should access the authorized original file, not the preview.
5. In another browser session or tenant, request the file ID. It must return
   `404` rather than exposing data.
