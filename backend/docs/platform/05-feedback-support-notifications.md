# Feedback, support, and durable in-app notifications

## User workflows

- **Feedback** is product input. Users choose a product area, describe it, and can follow status changes and public replies from Feedback Center.
- **Support** is a request for help, a complaint, or a time-sensitive issue. A submitted ticket gets an `AQ-XXXXXXXX` reference, an in-thread receipt acknowledgment, status/priority, and a reply history.
- Public admin replies are visible to the submitter and create an in-app notification. Admin-only notes are retained in the conversation but are excluded from user API responses.
- A user reply reopens a resolved/closed ticket. Admin status transitions are recorded in the message history.

Feedback categories: `suggestion`, `bug`, `achievement`, `ux_improvement`, `documents_collections`, `query_quality`, `deepspace_agent`, `provider_integrations`, `billing_plan`, `performance`, `reliability`, `accessibility`, `security_privacy`, `positive_feedback`, `other`.

Support categories: `query`, `feedback`, `complaint`, `technical_issue`, `account_access`, `billing_plan`, `documents_storage`, `query_results`, `deepspace_agent`, `provider_integrations`, `security_privacy`, `feature_request`, `other`.

Feedback states: `new`, `triaged`, `planned`, `in_progress`, `completed`, `declined`. Support states: `open`, `in_progress`, `waiting_user`, `resolved`, `closed`; priorities: `low`, `normal`, `high`, `urgent`.

## API surface

User support endpoints are under `/api/v1/support/tickets`: create/list, `GET /{ticket_id}`, and `POST /{ticket_id}/messages`. Admin ticket endpoints are `/api/v1/support/admin/tickets`, `GET /{ticket_id}`, `PATCH /{ticket_id}`, and `POST /{ticket_id}/messages`.

User feedback endpoints are `/api/v1/app-feedback/submit`, `/mine`, `/mine/{feedback_id}`, and `/mine/{feedback_id}/messages`. Admin submissions are `/api/v1/app-feedback/admin/submissions`, `GET /{feedback_id}`, `PATCH /{feedback_id}`, and `POST /{feedback_id}/messages`. Campaign endpoints remain available.

Feedback campaigns are platform-wide prompts created by authorized platform support staff; they are not tenant-specific. A tenant user's actual feedback submission and conversation remain scoped to that tenant and user. The Feedback Center's campaign panel is empty when no active campaign exists; users can still submit general feedback.

The Admin Feedback queue refreshes every 30 seconds while visible and supports manual refresh. Queue access failures are shown as errors instead of an empty queue; the conversation opens in a viewport-level overlay outside the dashboard's clipped content area, with loading/error states and a scrollable message history. User replies use a multiline input.

The authenticated notification feed is `/api/v1/notifications`: list (maximum 100 per page, with an offset), mark one/all read, and dismiss one/all. The collection notification list accepts an offset as well; its existing routes and push-delivery workflow remain intact. The dashboard notification drawer merges both feeds, polls every 15 seconds while visible, and can load older pages.

## Security and persistence

- User list/detail/reply queries constrain both tenant and authenticated user. Ticket/message and notification tables enforce tenant RLS. Cross-user resource lookups return 404.
- Feedback text is stored so the submitter and authorized platform support staff can read and discuss it. Access is protected by user/tenant checks, PostgreSQL RLS, and the platform-admin allowlist; this is not end-to-end encryption, because the support team must be able to read and reply to submissions.
- Admin routes keep their existing `admin:support:*` / `admin:feedback:*` permission checks and platform-admin email allowlist verification. Admin messages set visibility explicitly.
- Feedback/ticket changes and their user/admin notifications are written in the same database transaction, so a committed submission cannot lose its in-app receipt alert.
- The global admin-notification lookup temporarily switches to the existing `bypass` tenant context and restores the caller's context before returning. The bypass is not exposed to user input.
- Tenant context is transaction-local. Endpoints build response data before committing when they need RLS-protected messages; they do not refresh RLS rows after the context has been cleared.

## Operations added in migration `20261012_0011`

- **Support queue:** `GET /api/v1/support/admin/queue` supports status, priority, search, assignee, overdue, limit, and offset filters. It returns queue totals plus open and overdue counts. Admin updates can assign or unassign a ticket. Assignment is restricted to active platform administrators in the configured allowlist.
- **SLA tracking:** ticket rows store first-response and resolution deadlines, actual first public response, and resolution time. Normal tickets target 8 hours for first response and 72 hours for resolution; priority changes apply corresponding targets. A Celery task checks overdue tickets every five minutes and emits deduplicated alerts to platform administrators and the assignee. Existing open tickets start the SLA clock at migration rollout to avoid retroactive alert storms. These are elapsed UTC hours, not business-hours calendars; `waiting_user` currently does not pause the resolution clock.
- **Attachments:** users can add PDF, PNG, JPEG, and UTF-8 text files up to 5 MiB to an owned ticket. Uploads are byte-sniffed, scanned through the configured malware scanner, counted against workspace storage quota, stored in private object storage below a tenant-prefixed key, and served only after ticket ownership or platform-admin authorization is checked. The raw object key is never returned to clients.
- **Preferences:** `/api/v1/notifications/preferences` stores email opt-in, immediate/daily/weekly cadence, an IANA time zone, and muted event domains. The API returns the supported category catalog and channel availability. The catalog covers support, feedback, query, provider, storage, plan, system, documents, DeepSpace, collection moderation, and collection activity. Muted application events are hidden in the global notification feed; muting collection activity also hides it from the global collection notification feed, while collection history and collaboration delivery remain unchanged. Muting or opting out suppresses pending and claimed-but-not-yet-dispatched email rows. The email worker checks the current preference again immediately before SMTP submission. A message already accepted by SMTP cannot be recalled.
- **Email outbox:** notifications and opted-in email deliveries are recorded in the same database transaction. Celery claims due rows with `SKIP LOCKED`, releases database locks before SMTP, and keeps account/tenant deliveries separate even when accounts share an email address. Immediate cadence sends one event per message; daily and weekly digests are scoped to the owning account. Digest boundaries use 08:00 in the saved IANA time zone (weekly on Monday). If SMTP is not configured, queued rows remain pending instead of being repeatedly failed. Delivery is at-least-once: an SMTP server may accept a message just before a worker crash, so retries can duplicate it. A stable Message-ID helps mail clients deduplicate but cannot guarantee exactly-once delivery. Configure `AKS_NOTIFICATION_SMTP_HOST`, `AKS_NOTIFICATION_SMTP_PORT`, `AKS_NOTIFICATION_SMTP_USERNAME`, `AKS_NOTIFICATION_SMTP_PASSWORD`, and `AKS_NOTIFICATION_SMTP_FROM`; deploy a worker and Celery beat. Email remains unavailable in the UI until host and sender are configured.
- **Query/provider/system alerts:** Query execution failures produce content-free user alerts; authenticated API 5xx failures produce a notification containing only the trace reference. An explicit provider health-test failure alerts the provider owner (or initiating user) and platform administrators. These producers never persist prompt text, provider secrets, or exception contents.
- **Storage/role-plan alerts:** quota checks generate deduplicated 80%, 90%, and 100% usage warnings for the initiating user; a detected role-derived allocation increase generates a plan notice. This product has no paid-subscription entity or billing integration, so payment, renewal, cancellation, and failed-payment events do not exist and are not fabricated.
- **Submission protection:** support creation and attachment upload share an authenticated per-user/per-tenant hourly budget; feedback submissions have a separate hourly budget. Configure with `AKS_RATE_LIMIT_SUPPORT_SUBMISSIONS_PER_HOUR` and `AKS_RATE_LIMIT_FEEDBACK_SUBMISSIONS_PER_HOUR`.
- **Retention:** a weekly worker purges only notifications users already dismissed after `AKS_NOTIFICATION_RETENTION_DAYS` (365 by default). Undismissed notifications remain durable. Delivered and suppressed outbox rows are removed after `AKS_NOTIFICATION_DELIVERY_RETENTION_DAYS` (90 by default); permanently failed rows remain for operational follow-up.
- **Notification Center:** `/dashboard/notifications` combines the durable application and existing collection feeds, supports read/dismiss, and refreshes every 30 seconds. The header drawer links to this page.

The shared realtime event stream remains an ephemeral invalidation/online event channel, not a durable notification source. This work does not create an always-on provider health probe: provider alerts currently follow explicit health tests. Team-based assignment and business-hours SLA calendars are not implemented. SMTP delivery depends on deployment configuration, a running worker, and Celery beat. Subscription lifecycle alerts require a billing system and are deliberately absent until such a source of truth exists.

## Security and reliability notes

- New preferences, delivery rows, and attachment metadata have tenant RLS policies. User reads remain tenant/user scoped; cross-tenant admin queries use the existing server-side bypass only after platform-admin permission checks.
- Attachments are not served from public URLs. The API resolves metadata by ticket, tenant, and attachment ID, then performs a tenant-prefix-guarded object read.
- Email is opt-in. No email is sent inline in an API transaction.
- Preference writes are tenant/user scoped, serialize concurrent first writes, validate IANA time zones, and suppress eligible pending deliveries when the user opts out or mutes a category.
- When SMTP is unavailable, the UI presents in-app preferences only, hides email cadence/time-zone controls and email channel labels, and still lets a user turn off a previously saved email opt-in. Digest times are local to the saved time zone. Collection collaboration history is not altered by notification muting.
- Email is sent to the address on the user account. OAuth login requires the identity provider's verified-email claim, but this codebase does not persist a verified-email state for password accounts. Before enabling notification email for password-created accounts, deploy an email ownership verification flow or another explicit verified-address policy; the staging smoke test must include this policy.
- Database uniqueness keys deduplicate event notifications and one delivery per notification/channel. SMTP delivery remains at-least-once.
- Provider error text, query contents, and internal ticket notes are excluded from notifications and email bodies.

## Validation

Focused integration and regression coverage checks feedback and ticket submission, user/admin ownership, public versus internal replies, ticket assignments, SLA behavior, notification preferences and outbox delivery, attachment validation/download, quota/storage behavior, and plan/storage regressions. Run the verified selection with:

```bash
cd backend
./.venv/bin/pytest -o addopts= -q \
  tests/integration/test_plans_api.py \
  tests/integration/test_storage_retention_workflow.py \
  tests/integration/test_support_notifications_api.py \
  tests/integration/test_app_feedback_api.py \
  tests/unit/test_notification_preferences.py \
  tests/unit/test_deepspace_run_events.py \
  tests/unit/test_closure_remaining_modules.py
```

### Rollout verification record

On 2026-10-03, the running AverQel Docker environment was migrated from `20261012_0009` to `20261012_0011`. PostgreSQL reported `FORCE ROW LEVEL SECURITY` enabled for `user_notifications`, `support_ticket_messages`, `app_feedback_messages`, `user_notification_preferences`, `notification_deliveries`, and `support_ticket_attachments`. The support SLA columns were present after migration.

After rebuilding the frontend and restarting the API and Celery services, `/api/v1/health/live`, `/dashboard/notifications`, and `/dashboard/admin/support` returned HTTP 200. Celery beat loaded `notifications-email-outbox`, `notifications-support-sla`, and `notifications-retention-cleanup`; the maintenance worker registered their three corresponding tasks. The regression selection above passed with 47 tests. Frontend lint, TypeScript, and the production Docker build completed successfully; lint reported two unrelated existing warnings in `QueryPageClient.tsx`.

Email delivery was **not** live-tested because the active deployment has no `AKS_NOTIFICATION_SMTP_HOST`, `AKS_NOTIFICATION_SMTP_FROM`, username, or password configured. In-app delivery remains available. Configure SMTP credentials in the deployment secret store and restart the API, maintenance worker, and scheduler to enable email. Configure `AVERQEL_PUBLIC_ORIGIN` (or `AVERQEL_DOMAIN`) for absolute email links; production validates this when SMTP delivery is configured.

The checked-out product has role-derived storage plans but no paid-subscription/billing source of truth, so payment lifecycle events cannot be emitted. Provider notifications are produced when explicit health tests fail; no periodic health-probe service is configured. SLA targets use elapsed UTC time, not business-hour calendars, and `waiting_user` does not pause the resolution clock.

## Notification preferences hardening verification

On 2026-10-05, the notification preference hardening was checked locally. `alembic heads` reports the single head `20261012_0014`. The local Docker database was upgraded from `20261012_0013` to `20261012_0014`; the API live-health route returned HTTP 200, the frontend notification-settings route returned HTTP 200, and the maintenance worker loaded `notifications.dispatch_email_outbox`. The focused backend selection (`test_notification_preferences.py`, `test_support_notifications_api.py`, and `test_collection_moderation_admin.py`) passed twice with 11 tests per run. Frontend ESLint and TypeScript checks passed, the production frontend image built successfully, and the notification-preferences page suite passed twice with 3 tests per run. The backend integration test bootstrap also applied migrations to its isolated test database. The SMTP integration test sends through a local SMTP sink and verifies the worker marks both deliveries sent.

This verifies the local Docker stack, not the VPS rollout. The host shell has no `AKS_DATABASE_URL`, so migration status was checked and upgraded from inside the local API container. The local runtime uses in-app notifications and does not configure SMTP; the email control remains unavailable. SMTP was exercised only by the isolated integration test sink, which verifies outbox transport behavior without contacting external recipients. SMTP setup and external email delivery are optional and are not required for the in-app notification feature. If email is enabled in a future deployment, configure its SMTP credentials and sender, verify the deployed worker and beat schedule, and stage-test delivery and suppression before release.

The settings page was also updated for the in-app-only deployment state: it no longer promises email delivery or displays email-only cadence, time-zone, and channel controls when SMTP is unavailable. Its UI tests cover the in-app-only state and turning off an existing email opt-in.
