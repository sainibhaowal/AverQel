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
- **Preferences:** `/api/v1/notifications/preferences` stores email opt-in, immediate/daily/weekly cadence, and muted event domains. Muted domains remain durable in storage, are omitted from the user’s application-notification listing, and do not enqueue email. Collection notifications retain their existing controls.
- **Email outbox:** notifications and opted-in email deliveries are recorded in the same database transaction. Celery claims due rows with `SKIP LOCKED`, releases database locks before SMTP, groups digest messages, and retries with exponential backoff up to eight attempts. Delivery is at-least-once: an SMTP server may accept a message just before a worker crash, so retries can duplicate it. A stable Message-ID helps mail clients deduplicate but cannot guarantee exactly-once delivery. Configure `AKS_NOTIFICATION_SMTP_HOST`, `AKS_NOTIFICATION_SMTP_PORT`, `AKS_NOTIFICATION_SMTP_USERNAME`, `AKS_NOTIFICATION_SMTP_PASSWORD`, and `AKS_NOTIFICATION_SMTP_FROM`; deploy a worker and Celery beat. Email remains unavailable in the UI until host and sender are configured.
- **Query/provider/system alerts:** Query execution failures produce content-free user alerts; authenticated API 5xx failures produce a notification containing only the trace reference. An explicit provider health-test failure alerts the provider owner (or initiating user) and platform administrators. These producers never persist prompt text, provider secrets, or exception contents.
- **Storage/role-plan alerts:** quota checks generate deduplicated 80%, 90%, and 100% usage warnings for the initiating user; a detected role-derived allocation increase generates a plan notice. This product has no paid-subscription entity or billing integration, so payment, renewal, cancellation, and failed-payment events do not exist and are not fabricated.
- **Submission protection:** support creation and attachment upload share an authenticated per-user/per-tenant hourly budget; feedback submissions have a separate hourly budget. Configure with `AKS_RATE_LIMIT_SUPPORT_SUBMISSIONS_PER_HOUR` and `AKS_RATE_LIMIT_FEEDBACK_SUBMISSIONS_PER_HOUR`.
- **Retention:** a weekly worker purges only notifications users already dismissed after `AKS_NOTIFICATION_RETENTION_DAYS` (365 by default). Undismissed notifications remain durable. Successfully delivered outbox rows are removed after `AKS_NOTIFICATION_DELIVERY_RETENTION_DAYS` (90 by default); permanently failed delivery rows remain for operational follow-up.
- **Notification Center:** `/dashboard/notifications` combines the durable application and existing collection feeds, supports read/dismiss, and refreshes every 30 seconds. The header drawer links to this page.

The shared realtime event stream remains an ephemeral invalidation/online event channel, not a durable notification source. This work does not create an always-on provider health probe: provider alerts currently follow explicit health tests. Team-based assignment and business-hours SLA calendars are not implemented. SMTP delivery depends on deployment configuration, a running worker, and Celery beat. Subscription lifecycle alerts require a billing system and are deliberately absent until such a source of truth exists.

## Security and reliability notes

- New preferences, delivery rows, and attachment metadata have tenant RLS policies. User reads remain tenant/user scoped; cross-tenant admin queries use the existing server-side bypass only after platform-admin permission checks.
- Attachments are not served from public URLs. The API resolves metadata by ticket, tenant, and attachment ID, then performs a tenant-prefix-guarded object read.
- Email is opt-in. No email is sent inline in an API transaction.
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
  tests/unit/test_deepspace_run_events.py \
  tests/unit/test_closure_remaining_modules.py
```

### Rollout verification record

On 2026-10-03, the running AverQel Docker environment was migrated from `20261012_0009` to `20261012_0011`. PostgreSQL reported `FORCE ROW LEVEL SECURITY` enabled for `user_notifications`, `support_ticket_messages`, `app_feedback_messages`, `user_notification_preferences`, `notification_deliveries`, and `support_ticket_attachments`. The support SLA columns were present after migration.

After rebuilding the frontend and restarting the API and Celery services, `/api/v1/health/live`, `/dashboard/notifications`, and `/dashboard/admin/support` returned HTTP 200. Celery beat loaded `notifications-email-outbox`, `notifications-support-sla`, and `notifications-retention-cleanup`; the maintenance worker registered their three corresponding tasks. The regression selection above passed with 47 tests. Frontend lint, TypeScript, and the production Docker build completed successfully; lint reported two unrelated existing warnings in `QueryPageClient.tsx`.

Email delivery was **not** live-tested because the active deployment has no `AKS_NOTIFICATION_SMTP_HOST`, `AKS_NOTIFICATION_SMTP_FROM`, username, or password configured. In-app delivery remains available. Configure SMTP credentials in the deployment secret store and restart the API, maintenance worker, and scheduler to enable email. Configure `AVERQEL_PUBLIC_ORIGIN` (or `AVERQEL_DOMAIN`) for absolute email links; production validates this when SMTP delivery is configured.

The checked-out product has role-derived storage plans but no paid-subscription/billing source of truth, so payment lifecycle events cannot be emitted. Provider notifications are produced when explicit health tests fail; no periodic health-probe service is configured. SLA targets use elapsed UTC time, not business-hour calendars, and `waiting_user` does not pause the resolution clock.
