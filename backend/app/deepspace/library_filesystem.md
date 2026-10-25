# DeepSpace Library filesystem

The Library is a tenant-, user-, and conversation-scoped workspace. It is not
the host filesystem and no Library operation can access a server path.

## Storage model

- Text and source files remain in PostgreSQL for low-latency editing.
- Binary payloads (documents, media, and archives) are stored in the private
  MinIO bucket. PostgreSQL stores the object key, checksum, MIME type, size,
  and extracted text.
- Every saved revision is an immutable row in
  `deepspace_workspace_file_versions`.
- `expected_version` on updates prevents a stale tab from overwriting a newer
  save.

## Explorer API

All routes are under `/api/v1/deepspace/library/{conversation_id}` and require
the existing authenticated `queries:run` permission plus conversation
ownership checks.

- `GET /entries?parent_folder_id=...` lists one folder page.
- `POST /folders`, `PATCH /folders/{id}`, and
  `DELETE /folders/{id}?recursive=true` manage folders.
- `POST /files/upload` imports a multipart file. The JSON file route remains
  compatible with existing text/data-URL clients.
- `POST /files/{id}/copy` copies a file into another folder; pass
  `mode: "move"` to move it instead.
- `GET /files/{id}/content` streams the authenticated file payload.
- `GET /files/{id}/preview` returns a bounded visual derivative for PDF, raster
  images, SVG/AVIF, and LibreOffice-readable documents. Raster images are
  resized to a maximum 2560px edge; files above 100 MiB and images above 40
  megapixels are rejected for in-app preview. GIF and multi-page TIFF previews
  show their first frame/page.
- `GET /files/{id}/versions` lists revisions and
  `POST /files/{id}/versions/{version}/restore` restores one.
- ZIP entries are listed after safe bounds/path validation and can be read
  through `/files/{id}/archive/{entry_name}`. Entries are never executed.

The Library UI accepts multiple files from the picker, drag-and-drop, or the
browser clipboard. It uploads up to three files concurrently through the same
authenticated route, reports per-file byte progress and aggregate percentage,
and keeps successful files when another upload fails. The 25 MB client limit
and server-configured upload limit apply to each individual file.

PDF, Office/ODF, CSV, and supported image imports use the existing bounded
ingestion extractors when available. Image OCR supports PNG, JPG/JPEG, TIFF,
WebP, BMP, and GIF. OCR is background work; opening an older file with missing
extraction data queues it once instead of running OCR inside the file request.
AVIF and SVG have visual previews but are not supported by the image OCR
extractor. Extraction failures do not discard a valid stored binary.

PDF files use the browser PDF viewer. LibreOffice-readable Writer, Calc,
Impress, and Draw files are converted to PDF when LibreOffice is installed;
without that renderer, the UI reports the preview limitation and can still show
extracted text when available. Small XLSX files retain the interactive table
preview. Other supported spreadsheet formats use the visual PDF preview. CSV
continues to use bounded, paged table rendering. Images are rendered through a
private authenticated endpoint; supported raster inputs include BMP, GIF,
JPEG, PNG, TIFF, and WebP. AVIF is sent in its native format for Chromium-based
clients. SVG is served only as an image preview. These paths do not claim that
every uploaded binary type is renderable.

## Safety boundaries

Uploads are bounded by the configured upload limit. File/folder names are
validated, archive traversal is rejected, archive entry count and expansion
are capped, and all reads/writes/deletes verify tenant, user, and conversation
ownership. Recursive folder deletion removes private object-storage payloads
before the database cascade.

The editor is intentionally offered only for text/source files. Binary files
use authenticated preview/download, while document extraction provides a
readable representation without pretending that a PDF or DOCX is natively
editable in the text editor.
