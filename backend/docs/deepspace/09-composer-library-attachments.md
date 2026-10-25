# DeepSpace composer Library attachments

## What and why

The chat composer accepts device-selected files, drag/drop, and clipboard file
paste (including screenshots). Multiple selected files and batch drops are
staged independently. Each item is first created in the existing
conversation Library, then the chat turn carries only the completed Library
file ID. This gives the user a familiar attachment workflow without creating a
second storage path or exposing private uploads to browsers or providers.

## Contract and boundaries

- Frontend: `DeepSpaceComposer.tsx` stages thumbnails, upload progress,
  cancel/retry state, processing state, drag/drop, clipboard paste, camera
  capture where supported, and a blurred preview dialog.
  `DeepSpaceChatClient.tsx` sends `attachment_file_ids`.
- Each completed Library file has its own stable UUID, independent of its name
  or content. The upload session ID is temporary; after completion the
  composer replaces it with the Library file ID returned as `file_id`.
- API/queue: chat endpoints normalize at most ten UUID references; queued turns
  persist those references in the user's selection order through retry and
  worker dispatch. Duplicate references are removed without reordering.
- Worker/service: `DeepSpaceChatService.stream_turn` resolves every reference
  again by tenant, authenticated user, and current conversation before it adds
  attachment metadata to durable user-message history.
- The model receives an ordered attachment manifest with each file's
  attachment number, stable ID, exact name, MIME type, size, and available
  extraction status. Supported images sent to a vision-capable selected model
  also receive a `visual_input_number`; those image parts are sent in that
  order before any later tool-supplied image parts. The model can refer to
  “Attachment 2” or “Image 1” without relying on a filename being unique.
  Non-image files are read through the Library tools using their stable IDs;
  their bytes are not appended as image inputs.
- Storage: bytes, malware scanning, quota checks, encryption/storage settings,
  previews, and document extraction remain owned by the existing Library upload
  endpoints. Every composer upload is visible in the Library and can be
  attached again through the existing Library picker. No public URL, file
  bytes, or cross-tenant lookup is introduced.

## Repeated filenames

Composer uploads opt into server-side name disambiguation. If the selected
conversation folder already has the same name, or another upload has reserved
it, the Library assigns the next readable suffix before the upload starts (for
example, `screenshot (2).png`). It rechecks the reservation when publishing the
file to handle a concurrent Library write. This policy compares names, not file
contents: uploading the same bytes twice still creates two independent Library
records with different file IDs. The normal Library upload API keeps its
existing conflict response unless the caller explicitly opts in. Rename,
move, and write operations continue to enforce the folder's unique-name rule.

## Operational behavior

Sending is disabled while an item uploads or is scanned. A completed item shows
whether text was extracted, OCR was used, no readable text was found, or
extraction was unavailable; older items without a recorded status keep the
“Saved to Library” label. The Library drawer receives a browser update event and
refreshes. Attachment-only messages use a safe default review request.
Unsupported or oversized files continue to be rejected by the existing secure
Library policy. Verify migration `20260930_0001_deepspace_turn_attachments`
before enabling the release. The Documents Hub attachment and preview
contracts are documented in
[`../library/07-documents-hub-workflows.md`](../library/07-documents-hub-workflows.md).

## Model-aware image routing

Before opening a provider stream, DeepSpace checks the selected model's cached
`supports_image_in`, `supports_vision`, or input-modality metadata. It normalizes
catalog shapes such as `architecture.input_modalities`, and recognizes known
visual model IDs when a provider omits modality metadata. An explicit provider
capability declaration takes precedence over model-name inference. This works
across provider adapters; it does not send a probe image or a paid test prompt.

For a model identified as vision-capable, DeepSpace sends supported image bytes
directly to the selected model and does not wait for or add server OCR text to
that prompt. The Library may still run background extraction for search,
preview, and future text-only requests. JPEG, PNG, WebP, and GIF are the current
direct provider image formats. For a text-only, unknown, or otherwise
image-incompatible route, DeepSpace uses saved Library OCR; if background
extraction is still pending, it gives the worker a short head start and then
uses the same bounded Library extractor before sending the prompt. The original
image bytes are not sent to that text-only model. On-demand OCR reads no more
than 25 MiB of attachment bytes per request.

If a provider explicitly rejects image input before returning output, DeepSpace
performs one retry without image bytes, using saved or on-demand Library OCR.
If extraction is unavailable or finds no readable text, the user receives a
clear limitation instead of a visual guess. Other provider failures are not
retried as OCR fallbacks. For opaque model IDs whose provider catalog supplies
no modality capability, DeepSpace conservatively uses OCR; provider metadata is
needed to identify an unrecognized vision model without sending a probe.

The Library accepts more formats than the provider image-input contract. Other
files keep their own IDs and MIME types in the manifest. DeepSpace reads
extracted text through the Library tools when the configured extractor supports
the format; ZIP inspection and bounded data analysis use the authorized sandbox
tools. Upload support alone does not mean that a model can decode the original
bytes: for example, DeepSpace does not automatically transcribe audio or extract
video frames. If neither a supported visual input nor readable extracted/tool
output is available, the assistant must say so rather than infer file contents
from the name or format.
