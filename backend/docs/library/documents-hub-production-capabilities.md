# Documents Hub production capabilities

The Documents Hub uses tenant-scoped APIs and existing ingestion checkpoints.
The additive organization, sharing, AI action, webhook, automation, comment,
security receipt, and delivery records are migrated through
`20261009_0001_document_webhook_deliveries`.

Key contracts:

- Share links are bearer tokens whose SHA-256 hashes are stored; expiry and revocation are checked on every resolve.
- Webhook secrets remain encrypted at rest. Delivery is HMAC signed, retried, and disabled after repeated failures.
- Classification rules run on upload and scheduled automation re-applies them idempotently.
- Comment mentions accept only user IDs belonging to the current tenant.
- PDF thumbnails and page previews use the existing authenticated document access path.
- Recovery actions continue from persisted ingestion checkpoints rather than restarting extraction.

The complete route, component, migration, preview, quality, bulk-operation,
and verification map is maintained in
[`07-documents-hub-workflows.md`](07-documents-hub-workflows.md). Operational
failure handling and checkpoint diagnosis are in
[`08-ingestion-recovery-security-observability.md`](08-ingestion-recovery-security-observability.md).

Before release, run the backend test suite from a checkout that includes
`backend/tests` and the frontend Vitest and Playwright suites. The production
API image intentionally does not package test sources. The historical local
evidence is recorded in [`platform/04-end-to-end-verification.md`](../platform/04-end-to-end-verification.md);
use the [current release index](../release/03-current-worktree-change-index.md)
for newer local and environment status.
