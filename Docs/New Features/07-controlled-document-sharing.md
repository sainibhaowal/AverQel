# Controlled Document Sharing

## What to do

Share documents through explicit collection membership and permission roles, with optional
expiring links only when an administrator enables them.

## Why to do it

Teams need collaboration, but a share must never bypass tenant, user, or collection boundaries.

## Already have

- Collection membership and permissions in `backend/app/documents/models/collection.py` and
  `backend/app/documents/repositories/collections.py`.
- Accessibility checks used by document read, full-text, chunks, download, and query flows.

## Where and how

Prefer collection sharing as the primary model. Add:

- `POST /collections/{id}/documents/{document_id}` to attach an accessible document.
- `GET /documents/{id}/shares` and `PUT /documents/{id}/shares/{user_id}` for explicit roles.
- `DELETE /documents/{id}/shares/{user_id}`.
- Optional `POST /documents/{id}/share-links` with expiring, revocable, hash-only tokens.

Touchpoints: collection repository, accessibility service, RBAC, query retrieval filters,
document share dialog, audit logs, and tenant-isolation tests.

## Must not break

Admin settings remain admin-only. User/editor workspace actions stay equal. Public links are off by
default, never expose storage keys, and cannot access deleted, quarantined, or unindexed content.
