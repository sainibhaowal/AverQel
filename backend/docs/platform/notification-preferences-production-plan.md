# Notification preferences production-hardening plan

## Goal

Make the notification preference controls match the notification sources that
the product actually emits, and make email opt-out, category muting, and
scheduled delivery behave consistently across the API, database, UI, and
worker. Preserve the existing in-app notification formats, collection push
workflow, and tenant/user authorization rules.

## What already exists

- Authenticated `GET` and `PUT /api/v1/notifications/preferences` routes store
  email opt-in, cadence, and muted domains in
  `user_notification_preferences`, which has tenant RLS.
- Application notifications are persisted in `user_notifications`; the
  global notification drawer merges that feed with the separate
  `collection_notifications` feed.
- SMTP-enabled application notifications create transactional
  `notification_deliveries`. Celery beat schedules the outbox worker, which
  leases rows, sends SMTP mail, retries failures with bounded backoff, and
  records delivery state.
- The settings screen already exposes email availability, cadence, and muted
  categories. Deployment environment examples currently leave SMTP host and
  sender blank, so email is disabled until an operator configures it.

## Gaps to close

- The preference category list omits emitted `documents` and `deepspace`
  domains. Collection activity uses a separate notification feed and currently
  bypasses the muted-category preference.
- Changing email opt-in or muting a category does not suppress already queued
  outbox rows, and the worker does not recheck the current preference before
  sending.
- Daily and weekly cadence currently schedules individual rows and the worker
  groups only the claimed batch by email address. This can split one digest and
  combine separate accounts that happen to share an email address.
- Digest schedule time is implicit UTC and is not visible or configurable.
- The settings screen can remain in a loading state after a fetch error, uses
  generic save errors, and disables the email checkbox even when a user needs
  to turn off a previously enabled preference while SMTP is unavailable.
- Terminal outbox rows need bounded retention; existing cleanup removes only
  delivered rows.
- Existing integration coverage checks one muted application category and
  immediate email dispatch, but not category completeness, collection-feed
  muting, opt-out after enqueue, account-scoped digest behavior, or worker
  retry/suppression boundaries.

## Implementation map

| Area | Files / interfaces |
| --- | --- |
| Category catalog and validation | `backend/app/system/schemas/notifications.py`; `GET/PUT /api/v1/notifications/preferences`; category values include `support`, `feedback`, `query`, `provider`, `storage`, `plan`, `system`, `documents`, `deepspace`, `collection_moderation`, and in-app-only `collections` |
| Preference persistence / tenant scope | `backend/app/system/api/notifications.py`; `backend/app/system/models/user_notification_preference.py`; new Alembic migration after current head `20261012_0013` |
| Application and collection feed filters | `backend/app/system/api/notifications.py`; `backend/app/documents/api/collections.py`; `backend/app/documents/repositories/collection_notifications.py` |
| Enqueue and suppression | `backend/app/system/services/user_notifications.py`; `backend/app/system/models/notification_delivery.py`; preference-update transaction cancels eligible pending rows |
| Dispatch, digest, retry, retention | `backend/app/system/workers/tasks_notifications.py`; `backend/app/platform/worker/celery_app.py`; deployment queue configuration in `backend/docker-compose.yml` and `backend/docker-compose.prod.yml` |
| User interface | `frontend/app/dashboard/settings/notifications/page.tsx`; authenticated notification drawer in `frontend/app/components/layout/NotificationCenter.tsx` |
| Evidence and operating guidance | `backend/tests/integration/test_support_notifications_api.py`; new notification preference/outbox integration coverage; frontend notification-settings tests; `backend/docs/platform/05-feedback-support-notifications.md`; this plan |

## Safe implementation

1. Add the new database fields and supported terminal delivery state with an
   additive migration. Keep existing preference rows, notification rows,
   Celery task names, API paths, and collection push deliveries compatible.
2. Publish the server-owned category catalog in the preference response so
   the UI and request validator use the same supported categories. Apply the
   `collections` mute only to the global collection notification inbox; keep
   explicit collection activity/history routes and push delivery unchanged.
3. Update preferences transactionally. Reject malformed/null values with a
   validation response, handle concurrent first-time saves, suppress pending
   deliveries when email is disabled or their category becomes muted, and
   recalculate pending due times when cadence/time zone changes.
4. Dispatch one account at a time under a preference-row lock. Recheck current
   consent and mute state before sending; immediate notifications remain
   individual messages, while daily/weekly rows due for the same account are
   sent as one digest. Do not group across accounts by email address. Release
   database locks before SMTP. Keep bounded retry/backoff and at-least-once
   delivery semantics; a message already handed to SMTP cannot be recalled.
5. Make the settings page show real loading, retry, save, validation, and
   unavailable states. Allow users to disable email even when SMTP is no
   longer configured. Clearly show the time zone used for scheduled delivery.
6. Add integration and frontend tests for authorization/RLS, all categories,
   collection mute behavior, preference update and queued delivery suppression,
   account-scoped digests, retries, configuration-disabled behavior, and UI
   error/retry/save states. Run the focused suite repeatedly and update the
   operator guide with verified results and external rollout requirements.

## Risks and compatibility boundaries

- Muting an in-app category hides it from the global notification inbox but
  does not delete the underlying activity history.
- A delivery already being handed to SMTP may arrive after a user saves an
  opt-out. Queued and retrying rows will be suppressed; the UI must state this
  in-flight boundary accurately.
- SMTP credentials, provider acceptance, bounce handling, and staging are
  deployment concerns. Local tests can verify queue behavior with a fake
  sender, but cannot prove live mailbox delivery.
- Account authentication, user email identity, support/feedback event
  creation, notification read/dismiss routes, and collection push behavior
  must remain unchanged.

## Validation plan

- Run focused backend integration and worker tests with the isolated test DB.
- Run frontend preference-page tests and TypeScript validation.
- Run Ruff and `git diff --check`.
- Confirm Alembic has one head and the integration DB reaches it through the
  migration bootstrap.
- Do not claim staging/production delivery proof without configured SMTP,
  deployed worker/beat, and an actual staging smoke test.
