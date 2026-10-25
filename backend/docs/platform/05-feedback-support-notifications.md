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

The public landing-page contact form uses unauthenticated `GET /api/v1/contact/status`,
`POST /api/v1/contact/verification/request`, `POST /api/v1/contact/verification/confirm`, and
`POST /api/v1/contact` routes. A visitor must receive and enter a one-time email code before the
message fields unlock. The status response reports only whether the required sender, SMTP,
recipient, Redis, and verification-key configuration is present; it never returns the recipient. It
does not probe SMTP or Redis health. Contact messages are sent directly through the configured SMTP
service and are not persisted in the AverQel database or written to application logs. Visitors can
use these routes without an account.

### Configure Resend for public contact

The public form sends a message from the configured AverQel address to the private inbox in
<code>AKS_PUBLIC_CONTACT_RECIPIENT</code>. The visitor's email is set as Reply-To, so a reply from
the receiving mailbox targets the visitor. The private recipient remains backend-only. Set the
sender to <code>contact@averqel.com</code> if that is the public address visitors should see.

Resend must show <code>averqel.com</code> as verified for sending. Store credentials only in the
backend deployment secret store:

| Setting | Resend value |
| --- | --- |
| <code>AKS_NOTIFICATION_SMTP_HOST</code> | <code>smtp.resend.com</code> |
| <code>AKS_NOTIFICATION_SMTP_PORT</code> | <code>465</code> |
| <code>AKS_NOTIFICATION_SMTP_USERNAME</code> | <code>resend</code> |
| <code>AKS_NOTIFICATION_SMTP_PASSWORD</code> | Resend API key |
| <code>AKS_NOTIFICATION_SMTP_FROM</code> | Existing application-notification sender |
| <code>AKS_NOTIFICATION_SMTP_STARTTLS</code> | <code>false</code> |
| <code>AKS_NOTIFICATION_SMTP_IMPLICIT_TLS</code> | <code>true</code> |
| <code>AKS_PUBLIC_CONTACT_RECIPIENT</code> | Private inbox that receives messages and forwards |
| <code>AKS_PUBLIC_CONTACT_FROM</code> | <code>AverQel Contact &lt;contact@averqel.com&gt;</code> |
| <code>AKS_PUBLIC_CONTACT_VERIFICATION_FROM</code> | <code>verify@averqel.com</code> on the verified sending domain |
| <code>AKS_PUBLIC_CONTACT_ADDRESS</code> | <code>contact@averqel.com</code> |
| <code>AKS_PUBLIC_CONTACT_RESEND_API_KEY</code> | Resend API key allowed to read received mail and send forwards |
| <code>AKS_PUBLIC_CONTACT_RESEND_WEBHOOK_SECRET</code> | Resend webhook signing secret (<code>whsec_...</code>) |

Resend SMTP uses the API key as its password and supports implicit TLS on port 465. The SMTP TLS
settings must select exactly one encrypted mode. These SMTP settings are also shared with AverQel's
optional notification email worker. After changing deployment secrets, restart or redeploy the API
and any worker that sends notification email.

The public contact sender is separate from the shared application-notification sender. The backend
sends contact messages from <code>AKS_PUBLIC_CONTACT_FROM</code> and sends a six-digit code from
<code>AKS_PUBLIC_CONTACT_VERIFICATION_FROM</code> using the same authenticated SMTP connection. Use
both senders on the domain verified with Resend. Verification messages include a branded HTML email
with the AverQel logo embedded inline and a plain-text alternative for clients that do not display
HTML. A code is valid for 10 minutes and allows up to five attempts; the resulting verification
token is single-use and expires after 30 minutes. Redis is required for challenge and token state;
verification fails closed if Redis is unavailable. The backend stores only keyed HMAC fingerprints
for the address and code in Redis, not the raw code or address. Requests are rate-limited by source
IP and an HMAC of the email address. Google OAuth is unrelated to this anonymous email-ownership
check.

### Forward mail sent directly to contact@

Resend Receiving stores direct mail addressed to <code>contact@averqel.com</code>; it does not
forward it to the private inbox by itself. To forward it through AverQel, configure a Resend webhook
for the <code>email.received</code> event at
<code>https://averqel.com/api/v1/contact/resend-inbound</code>. Copy that webhook's signing secret
to <code>AKS_PUBLIC_CONTACT_RESEND_WEBHOOK_SECRET</code>. The endpoint verifies Resend's signature,
accepts only the configured contact address, fetches the message from Resend, and forwards a
plain-text copy to <code>AKS_PUBLIC_CONTACT_RECIPIENT</code> using a Resend API idempotency key.
Message contents are not stored in the AverQel database or written to application logs. Attachments
remain available in Resend and are not included in the forwarded copy.

The deployed endpoint must be publicly reachable by Resend. A local form can send outbound email
when its backend has SMTP configuration and internet access, but Resend cannot deliver webhook
events to a plain localhost URL. <code>GET /api/v1/contact/status</code> reports whether the needed
configuration is present; it does not test SMTP credentials, Redis connectivity, webhook setup, or
delivery. Test the deployed form and direct-mail forwarding separately. Never put API keys, the
webhook secret, or the private recipient in frontend configuration or source control.

To reply without showing a private Gmail address, configure the mail client to send as
<code>contact@averqel.com</code> through Resend SMTP, and choose that address in the From field.
Replies to <code>contact@averqel.com</code> are delivered through the inbound webhook to the private
recipient.

There is no platform staff-role assignment endpoint. Legacy
`support_manager` and `feedback_manager` role rows may remain in existing
databases, but they grant no access to support or feedback queues. Only an
allowlisted platform administrator can pass the queue API access gate; the
current browser queue also requires the platform-key owner to unlock the key.
The
`collection_moderator` role remains separately permissioned for tenant-scoped
Qel Connect moderation; it does not grant platform administration access.

Reads of the platform support queue, ticket history, ticket details, support
attachments, and app-feedback submissions are recorded as metadata-only audit
events. Message and status changes are also audited without copying message
bodies into those audit events. Allowlisted platform administrators with the
appropriate route permission can request ticket content, attachments, or
feedback across tenants through these APIs. Decrypting message bodies also
requires the platform-key owner's account and unlocked private key; the current
admin UI cannot open a queue under a different administrator account. Admin
access is limited to the support or feedback that a user submitted; it does not
grant access to that user's chats, documents, or other workspace content. The
feedback API omits submitter email addresses and user IDs, while the backend
keeps the account link needed to deliver in-app replies.

Feedback campaigns are platform-wide prompts created by an allowlisted platform
administrator; they are not tenant-specific. A tenant user's actual feedback
submission and conversation remain scoped to that tenant and user. The Feedback
Center's campaign panel is empty when no active campaign exists; users can
still submit general feedback.

The Admin Feedback queue refreshes every 30 seconds while visible and supports manual refresh. Queue access failures are shown as errors instead of an empty queue; the conversation opens in a viewport-level overlay outside the dashboard's clipped content area, with loading/error states and a scrollable message history. User replies use a multiline input.

The authenticated notification feed is `/api/v1/notifications`: list (maximum 100 per page, with an offset), mark one/all read, and dismiss one/all. The collection notification list accepts an offset as well; its existing routes and push-delivery workflow remain intact. The dashboard notification drawer merges both feeds, polls every 15 seconds while visible, and can load older pages. If a feed fails, the drawer keeps its last loaded items, identifies which feed could not refresh, and retries with a bounded delay that grows to two minutes until both feeds recover.

## Security and persistence

Support/feedback encryption protects message content in storage while allowing
the submitting user and the platform-key owner to read the thread. The platform
private key is currently owned by the single administrator account that
created it; another allowlisted administrator cannot retrieve that private-key
backup or decrypt the message body. This is separate from TOTP MFA: the user
passphrase unlocks a browser-held private key and does not authenticate the
account. The platform key owner creates the platform key once; each user
creates a personal key once. The browser retains an unlocked key across
Support and Feedback navigation for up to four hours of inactivity, then locks
it. Sign-out, login-session expiry, reload, or closing the page also clears the
in-memory unlock. This is a rolling idle timeout, not a fixed 12-hour period.

If no platform public key is initialized, the authenticated
`GET /api/v1/support/encryption/admin-public-key` returns `503`; encrypted
submission is unavailable until an authorized platform admin creates the key.
`GET /api/v1/support/encryption/me` returns `404` when the user's personal key
has not been set up. The first visit to Support or Feedback then offers key
creation. During legacy migration, records for users without a personal key are
skipped and can be retried after setup. Ordinary setup cannot replace an
existing user or platform key (`409`); key recovery is separate.

The platform key is tied to its creator's account. Only that same account can
retrieve and unlock its encrypted private-key backup; another administrator
receives `403`. Keep the owner account active and preserve its passphrase. The
current product has no platform-key transfer or recovery workflow: losing the
passphrase or erasing the owner account can make existing messages encrypted to
the platform key unreadable in AverQel. Do not erase or replace that account
until an approved recovery plan exists.

For the six admin modules and their access gates, see
[`06-platform-administration.md`](06-platform-administration.md).

- User list/detail/reply queries constrain both tenant and authenticated user. Support ticket/message/attachment and feedback/message tables enforce tenant RLS; cross-tenant and cross-user resource lookups return 404.
- New support and feedback bodies are encrypted in the browser with a random AES-256-GCM content key. Each content key is wrapped to the submitter's RSA-3072 key and the single platform-key owner's RSA-3072 key; internal notes are wrapped only to that administrator key. Support attachment bytes, filenames, and content types are encrypted before storage. Private keys are stored on the server only as AES-GCM ciphertext derived from a user-entered passphrase with PBKDF2-SHA256 (600,000 iterations); the passphrase is never sent to the API. After unlocking, a private key stays in browser memory across Support and Feedback navigation and is cleared after four hours without user activity, on logout, or when the authenticated session expires. A full page reload or tab close also clears the in-memory unlock. The API validates envelope structure, recipient key IDs, key fingerprints, and the RSA public-key parameters, but it does not receive or decrypt message content.
- Conversation responses include each visible participant's avatar once, then refer to that profile from its messages. Support admin views also include participant display names. Feedback admin views retain submitter anonymity and return avatars without names or email addresses. User views keep staff identified as the AverQel team and continue to exclude internal notes and their authors. The server returns profiles only for the submitter and authors in the authorized thread.
- A browser-based migration is available on both admin management pages. The platform-key owner must create or unlock that key; each affected user must create their own passphrase-protected key by opening Support or Feedback once. Only the platform-key owner can decrypt the administrator copy or run this migration. The migration encrypts legacy ticket/feedback content in that administrator's browser and only replaces database plaintext after the API validates the ciphertext. Support attachment replacement stores the encrypted object and queues the old object for cleanup in the same database transaction. Records whose owners have not initialized a key are reported as skipped, not failed; after those users complete setup, the key owner can retry the migration. On later visits, the application decrypts content in the browser after the relevant recipient unlocks their own key; there is no separate server-side decrypt action. Losing a passphrase can make that recipient's encrypted copy unreadable. Older backups can retain plaintext until their configured expiry; the application cannot rewrite already-created backup snapshots.
- The service still sees account/tenant IDs, support email, category, status, timestamps, assignment and SLA state, attachment size, and event routing metadata. The platform-key owner is an intended decryption recipient; ordinary queue access by another allowlisted administrator does not give that account the private key. Since this is a web application, a compromised live server could serve changed JavaScript or substitute recipient keys; compromised clients can expose plaintext after decryption. The key bootstrapping design has no out-of-band key verification, and this application scheme has not received an independent cryptographic audit. It does not make all AverQel data end-to-end encrypted.
- Encrypted attachments cannot be scanned by server-side ClamAV. The browser encrypts them before upload, so users should only download files they trust. Existing plaintext attachments were scanned under the prior upload path; a migration encrypts them client-side before replacing the stored object.
- Platform-admin feedback replies omit the submitter email and account ID. Allowlisted platform administrators reviewing support can see the submitter email because it is needed to answer that ticket.
- Support-management routes require platform-admin allowlisting and the `admin:support:read` or `admin:support:write` permission. Feedback management requires platform-admin allowlisting and the `admin:feedback:read` or `admin:feedback:write` permission. Legacy `support_manager` and `feedback_manager` roles do not grant cross-tenant content access. Admin messages set visibility explicitly.
- Qel Connect moderation uses the separate `collection_moderator` role with `collections:moderation:read` and `collections:moderation:write`. Its report and history queries remain scoped to the active tenant. The general `admin` role does not imply moderation access. Legacy `feedback_manager` and `support_manager` role rows can remain in the database, but do not grant support or feedback content permissions. The Admin Users screen and backend API do not provide staff-role assignment controls. Existing role rows are not automatically deleted.
- Feedback submission alerts go only to active platform administrators; Qel Connect report alerts go to active moderators assigned in that tenant. Support administrator alerts contain no ticket subject or body. Bootstrap-owner authentication preserves additional explicit roles.
- Feedback/ticket changes and their user/admin notifications are written in the same database transaction, so a committed submission cannot lose its in-app receipt alert.
- The global admin-notification lookup temporarily switches to the existing `bypass` tenant context and restores the caller's context before returning. The bypass is not exposed to user input.
- Tenant context is transaction-local. Endpoints build response data before committing when they need RLS-protected messages; they do not refresh RLS rows after the context has been cleared.

## Operations added in migration `20261012_0011`

- **Support queue:** `GET /api/v1/support/admin/queue` supports status, priority, search, assignee, overdue, limit, and offset filters. It returns queue totals plus open and overdue counts. Admin updates can assign or unassign a ticket. Assignment is restricted to active platform administrators in the configured allowlist.
- **SLA tracking:** ticket rows store first-response and resolution deadlines, actual first public response, and resolution time. Normal tickets target 8 hours for first response and 72 hours for resolution; priority changes apply corresponding targets. A Celery task checks overdue tickets every five minutes and emits deduplicated alerts to platform administrators and the assignee. Existing open tickets start the SLA clock at migration rollout to avoid retroactive alert storms. These are elapsed UTC hours, not business-hours calendars; `waiting_user` currently does not pause the resolution clock.
- **Attachments:** users can add files up to 5 MiB to an owned ticket. The browser encrypts file bytes and filename/type metadata before upload. The API validates the envelope and size, counts encrypted bytes against workspace quota, stores ciphertext in private object storage below a tenant-prefixed key, and serves it only after ticket ownership or platform-admin authorization is checked. The server cannot inspect MIME bytes or run ClamAV on ciphertext; the raw object key is never returned to clients.
- **Preferences:** `/api/v1/notifications/preferences` stores email opt-in, immediate/daily/weekly cadence, an IANA time zone, and muted event domains. The API returns the supported category catalog and channel availability. The catalog covers support, feedback, query, provider, storage, plan, system, documents, DeepSpace, collection moderation, and collection activity. Muted application events are hidden in the global notification feed; muting collection activity also hides it from the global collection notification feed, while collection history and collaboration delivery remain unchanged. Muting or opting out suppresses pending and claimed-but-not-yet-dispatched email rows. The email worker checks the current preference again immediately before SMTP submission. A message already accepted by SMTP cannot be recalled.
- **Email outbox:** notifications and opted-in email deliveries are recorded in the same database transaction. Celery claims due rows with `SKIP LOCKED`, releases database locks before SMTP, and keeps account/tenant deliveries separate even when accounts share an email address. Immediate cadence sends one event per message; daily and weekly digests are scoped to the owning account. Digest boundaries use 08:00 in the saved IANA time zone (weekly on Monday). If SMTP is not configured, queued rows remain pending instead of being repeatedly failed. Delivery is at-least-once: an SMTP server may accept a message just before a worker crash, so retries can duplicate it. A stable Message-ID helps mail clients deduplicate but cannot guarantee exactly-once delivery. Configure `AKS_NOTIFICATION_SMTP_HOST`, `AKS_NOTIFICATION_SMTP_PORT`, `AKS_NOTIFICATION_SMTP_USERNAME`, `AKS_NOTIFICATION_SMTP_PASSWORD`, and `AKS_NOTIFICATION_SMTP_FROM`; deploy a worker and Celery beat. Email remains unavailable in the UI until host and sender are configured.
- **Query/provider/system alerts:** Query execution failures produce content-free user alerts; authenticated API 5xx failures produce a notification containing only the trace reference. An explicit provider health-test failure alerts the provider owner (or initiating user) and platform administrators. These producers never persist prompt text, provider secrets, or exception contents.
- **Storage/role-plan alerts:** quota checks generate deduplicated 80%, 90%, and 100% usage warnings for the initiating user; a detected role-derived allocation increase generates a plan notice. This product has no paid-subscription entity or billing integration, so payment, renewal, cancellation, and failed-payment events do not exist and are not fabricated.
- **Submission protection:** support creation and attachment upload share an authenticated per-user/per-tenant hourly budget; feedback submissions have a separate hourly budget. Configure with `AKS_RATE_LIMIT_SUPPORT_SUBMISSIONS_PER_HOUR` and `AKS_RATE_LIMIT_FEEDBACK_SUBMISSIONS_PER_HOUR`.
- **Public contact protection:** contact messages are limited per source IP using a keyed HMAC fingerprint with a one-hour TTL; the default is five submissions per hour. Verification requests are limited to ten per source IP and three per HMAC-fingerprinted email address per hour. Each code permits five attempts and expires after ten minutes. Configure `AKS_RATE_LIMIT_PUBLIC_CONTACT_SUBMISSIONS_PER_HOUR`, `AKS_RATE_LIMIT_PUBLIC_CONTACT_VERIFICATION_IP_PER_HOUR`, and `AKS_RATE_LIMIT_PUBLIC_CONTACT_VERIFICATION_EMAIL_PER_HOUR`. The endpoint also bounds field lengths and ignores automated submissions that fill its hidden honeypot field.
- **Retention:** a weekly worker purges only notifications users already dismissed after `AKS_NOTIFICATION_RETENTION_DAYS` (365 by default). Undismissed notifications remain durable. Delivered and suppressed outbox rows are removed after `AKS_NOTIFICATION_DELIVERY_RETENTION_DAYS` (90 by default); permanently failed rows remain for operational follow-up.
- **Feedback and support retention:** the daily `maintenance.retention_cleanup` worker removes feedback and support tickets of any status after 365 days since their last update by default (`AKS_FEEDBACK_RETENTION_DAYS` and `AKS_SUPPORT_TICKET_RETENTION_DAYS`). Related in-app notifications are deleted with each record. Ticket attachments are queued for the existing retryable object-storage cleanup worker before their database records are removed. Both settings accept 30–3650 days.
- **Notification Center:** `/dashboard/notifications` combines the durable application and existing collection feeds, supports read/dismiss, and refreshes every 30 seconds. The header drawer links to this page.

The shared realtime event stream remains an ephemeral invalidation/online event channel, not a durable notification source. This work does not create an always-on provider health probe: provider alerts currently follow explicit health tests. Team-based assignment and business-hours SLA calendars are not implemented. SMTP delivery depends on deployment configuration, a running worker, and Celery beat. Subscription lifecycle alerts require a billing system and are deliberately absent until such a source of truth exists.

## Security and reliability notes

- New preferences, delivery rows, and attachment metadata have tenant RLS policies. User reads remain tenant/user scoped; cross-tenant admin queries use the existing server-side bypass only after platform-admin permission checks.
- Attachments are not served from public URLs. The API resolves metadata by ticket, tenant, and attachment ID, then performs a tenant-prefix-guarded object read.
- Email is opt-in. No email is sent inline in an API transaction.
- Public website contact is separate from the notification outbox: it sends the verification code and, after successful verification, the contact message inline with a 12-second SMTP timeout. It requires authenticated SMTP using exactly one encrypted transport, STARTTLS or implicit TLS, `AKS_PUBLIC_CONTACT_FROM`, `AKS_PUBLIC_CONTACT_VERIFICATION_FROM`, and `AKS_PUBLIC_CONTACT_RECIPIENT`. Keep SMTP credentials and the private recipient in the deployment secret store; no recipient is exposed in frontend code, API responses, or application logs. The mail provider processes the verification email and contact message; email is not end-to-end encrypted. Contact text is not saved in AverQel's database. Redis holds only keyed verification fingerprints and rate-limit counters with short TTLs; the message body and OTP are not written there.
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
