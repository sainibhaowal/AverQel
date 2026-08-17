# Retention, Trash, and Restore

## What to do

Introduce a recoverable trash state, tenant-configurable retention windows, legal hold, and a
verified purge worker.

## Why to do it

Current deletion protects access and cleans storage. Retention adds recovery and predictable
lifecycle control for business users.

## Important compatibility decision

This changes deletion semantics. Release behind a tenant feature flag and a documented policy:
delete-to-trash first, permanent purge after the retention window. Never change current delete
behavior silently.

## Where and how

Add nullable `deleted_at`, `purge_after`, `restored_at`, and `legal_hold` fields; model
`DocumentRetentionPolicy`; and a maintenance purge job. Proposed routes:
`GET /documents/trash`, `POST /documents/{id}/restore`, `DELETE /documents/{id}/purge`, and
admin-only policy routes under `/admin/documents/retention`.

Touchpoints: `Document`, `deletion_service.py`, `storage_cleanup_jobs`, maintenance worker,
document filters, confirmation dialogs, audit logs, and migration/backfill tests.

Purge must remove chunks, embeddings, raw storage, versions, scan records, and derived caches only
after authorization, retention-expiry, and legal-hold checks. Every purge is idempotent and audited.
