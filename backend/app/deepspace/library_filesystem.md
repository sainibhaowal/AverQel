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
- `GET /files/{id}/versions` lists revisions and
  `POST /files/{id}/versions/{version}/restore` restores one.
- ZIP entries are listed after safe bounds/path validation and can be read
  through `/files/{id}/archive/{entry_name}`. Entries are never executed.

The Library UI accepts multiple files from the picker, drag-and-drop, or the
browser clipboard. It uploads up to three files concurrently through the same
authenticated route, reports per-file byte progress and aggregate percentage,
and keeps successful files when another upload fails. The 25 MB client limit
and server-configured upload limit apply to each individual file.

PDF, DOCX, XLSX, and CSV imports use the existing bounded ingestion extractors
when available. Extraction failures do not discard a valid stored binary; the
preview receives an explicit extraction warning instead.

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
