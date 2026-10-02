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
- API/queue: chat endpoints normalize at most ten UUID references; queued turns
  persist those references through retry and worker dispatch.
- Worker/service: `DeepSpaceChatService.stream_turn` resolves every reference
  again by tenant, authenticated user, and current conversation before it adds
  attachment metadata to durable user-message history.
- Storage: bytes, malware scanning, quota checks, encryption/storage settings,
  previews, and document extraction remain owned by the existing Library upload
  endpoints. Every composer upload is visible in the Library and can be
  attached again through the existing Library picker. No public URL, file
  bytes, or cross-tenant lookup is introduced.

## Operational behavior

Sending is disabled while an item uploads or is scanned. A completed item is
marked “Saved to Library”; the Library drawer receives a browser update event
and refreshes. Attachment-only messages use a safe default review request.
Unsupported or oversized files continue to be rejected by the existing secure
Library policy. Verify migration `20260930_0001_deepspace_turn_attachments`
before enabling the release. The Documents Hub attachment and preview
contracts are documented in
[`../library/07-documents-hub-workflows.md`](../library/07-documents-hub-workflows.md).
