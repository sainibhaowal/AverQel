# Platform administration: access, audit, and operational modules

This guide is for AverQel platform operators. It describes the six platform-admin
modules and the security boundaries enforced by the API. Seeing an admin page
in the browser is not proof that its API calls are authorized; every route checks
the signed-in account, platform-admin allowlist, and required permission.

## Access requirements

Platform-wide administration requires an account with an administrator role,
an email included in the deployment's platform-admin allowlist, and TOTP
authenticator MFA enabled and verified on the current login session. MFA is
required by default. The authenticated `GET /api/v1/admin/access` readiness
route can explain a missing role, allowlist entry, authenticator setup, or
MFA-verified sign-in, but it grants no administrative permission. The protected
route checks remain authoritative.

Configure TOTP from account security using `POST /api/v1/auth/2fa/setup` and
`POST /api/v1/auth/2fa/confirm`. After enrolling, sign out and sign back in with
the authenticator challenge so the current session carries verified MFA. The
platform-admin account itself cannot turn off TOTP while it remains allowlisted.
Account erasure and tenant-content purge requests, approvals, and cancellations
also require an MFA-verified sign-in from the previous 10 minutes by default.
The exact recent-MFA window is deployment-configurable from 1 to 60 minutes.

## The six modules

| Module | Main work | Access and safeguards |
| --- | --- | --- |
| **Users** | Review accounts, tenant, active state, roles, MFA status, creation time, and last successful sign-in. Disable, reactivate, force logout, or erase an account. | Separate server permissions gate reads and each action. Disable blocks sign-in and revokes sessions; force logout revokes sessions without deleting data. Account erasure requires recent MFA and the exact `DELETE <account email>` confirmation. The currently signed-in account and configured bootstrap admins are protected. The UI does not assign staff roles. |
| **Audit Logs** | Review platform-wide events; filter by action, account ID, or security events; page through results. | Requires `admin:audit_logs:read`. Audit rows expose action, recorded outcome/status, actor and target references, resource, trace reference, and safe authentication metadata. They exclude prompts, documents, chats, passwords, MFA codes, IP addresses, and device details. Audit timestamps are displayed in UTC. The table abbreviates actor and tenant IDs to the first UUID segment and trace IDs to eight characters; expanding a row shows the full available references. |
| **Support Management** | Triage cross-tenant tickets, assign active platform admins, update status and priority, reply, add admin-only notes, and migrate eligible legacy content. | Requires the support read/write permissions and a platform-admin session. Message text and attachments are encrypted in the browser for the submitter and the single platform-key owner. Only the account that created the platform key can unlock message content or run migration; another allowlisted admin receives `403` at the key endpoint, so the current UI cannot open the queue for that account. See [support and feedback security](05-feedback-support-notifications.md). |
| **Feedback Management** | Review submissions, update review status, reply in the encrypted thread, and create feedback campaigns. | Requires feedback read/write permissions and a platform-admin session. Submitter email and account ID are omitted from the review queue. Only the platform-key owner can unlock message content; another allowlisted admin receives `403` at the key endpoint, so the current UI cannot open the queue for that account. |
| **Data Deletion** | Erase one account, review/retry failed storage-cleanup jobs, or request a tenant-content purge. | Account erasure removes the selected account and its owned live records; it is not the tenant-purge workflow. Purging tenant content retains user accounts and selected operational records. A second authorized admin can approve a purge immediately; a sole admin can self-approve after the configured hold (24 hours by default, bounded to 24–168 hours). Requests, approvals, and cancellations require recent MFA and are audited. Backups and external-provider copies follow their own retention controls. |
| **System Metrics** | View service-wide request/error counters, instrumented database operations, worker retries, and selected DeepSpace counters through a live snapshot stream. | Requires `admin:metrics:read` and platform-admin access. The dashboard reports live, partial, reconnecting, or unavailable state; counters are operational signals, not per-user usage records or an uptime guarantee. Shared Redis metric storage must be available. The raw Prometheus scrape route is not a public admin UI and is blocked by the production gateway. |

Support and Feedback Management are different from Qel Connect moderation.
Legacy `support_manager` and `feedback_manager` role rows do not grant access to
the cross-tenant queues. Qel Connect moderators remain scoped to their active
tenant. Read and write activity on protected admin surfaces is audited.

### Route permissions

Platform-admin allowlisting and MFA are required in addition to the permissions
below. A platform-admin-ready session does not automatically have every module
permission.

| Area/action | Required permission |
| --- | --- |
| Users: list/detail | admin:users:read |
| Users: disable, reactivate, force logout, erase | admin:users:disable, admin:users:reactivate, admin:users:logout, and admin:users:delete, respectively |
| Audit Logs | admin:audit_logs:read |
| Support Management: read or update | admin:support:read or admin:support:write |
| Feedback Management: read or update | admin:feedback:read or admin:feedback:write |
| Data Deletion: list, request/cancel, approve | admin:data_deletions:read, admin:data_deletions:write, or admin:data_deletions:approve |
| Account erasure and failed storage-cleanup retry | admin:users:delete |
| Storage-cleanup queue | admin:users:read |
| System Metrics | admin:metrics:read |

If the platform-admin access readiness endpoint reports that access is not
allowed, follow its reason code: an administrator role, allowlist entry,
authenticator enrollment, or a new MFA-verified sign-in may be missing. If
readiness succeeds but a module still returns HTTP 403, the session passed
the platform-admin gate but may lack that route's specific permission. One
module's permission does not imply another's. Do not treat a failed queue
request as an empty queue.

## Timestamps, outcomes, and identifiers

The API persists event instants in UTC and serializes date-time fields with an
offset. The Audit Logs and Data Deletion screens explicitly render timestamps as
UTC. Users, Support Management, Feedback Management, and System Metrics format
their displayed dates in the browser's local time zone; check the displayed zone
before comparing those labels with an audit row or server log. Audit `status` is
the recorded outcome for that event (for example, success, failure, or another
action-specific state); `action` describes what was attempted. A visible short
ID is a display aid, not a different database identifier. Use the expanded row
for the full audit reference when correlating an event with API logs.

Support ticket cards show the first eight characters of a ticket UUID as a
compact reference; API routes continue to use the full UUID. In Audit Logs,
actor and tenant UUIDs are shortened to their first UUID segment and trace IDs
to eight characters in the table, with full available references on expansion.

The audit retention period is 90 days by default and is deployment-configurable.
After account erasure, security history retains minimal anonymous metadata; a
separate administrator erasure event keeps the target's opaque account UUID
(not email) so an authorized operator can find the event later.

## Support and feedback encryption is not MFA

These encryption mechanisms address different risks:

| Mechanism | Why it exists and who can decrypt | Who sets it up |
| --- | --- | --- |
| Sign-in MFA (TOTP) | Confirms an authenticator challenge for the login session. It protects platform-admin access and recent-MFA deletion actions; it does not encrypt application content. | Each account required to use MFA enrolls an authenticator in account security. |
| Support/feedback content encryption | Avoids storing new message text as readable database content while still letting the submitter and the single platform-key owner read and reply. Message bodies and attachments are encrypted in the browser; the service still sees routing metadata. | One platform admin account creates and owns the platform key. Each user creates a personal key with a passphrase of at least 14 characters the first time they open Support or Feedback. |
| Composio key/session encryption | Protects the user's Composio project key and hosted-session reference at rest and binds them to their tenant/account. The running server decrypts them when calling Composio, so this is not server-blind or end-to-end encryption. | Each user supplies their own Composio project key; the server's connector-secret encryption backend must be configured. |
| Model-provider secret encryption | Protects provider credentials at rest. The running backend needs the secret to send requests to the selected model provider. | The account owner adds the provider credential; the operator configures the backend secret-encryption key. |

The user passphrase is never sent to the API. The browser keeps the unlocked
private key in memory across Support and Feedback navigation, then locks it after
four hours without activity, on sign-out, when the login session expires, or
when the page is reloaded/closed. This is a rolling idle timeout, not a fixed
four-hour session from sign-in. The passphrase cannot be recovered by AverQel.
The current source uses a four-hour idle timeout; it does not use a fixed
12-hour unlock window.

The platform encryption key is owned by the administrator account that created
it. Only that account can retrieve and unlock its encrypted private-key backup;
other allowlisted administrators receive `403` and cannot decrypt message
bodies or perform legacy migration; the current queue UI cannot open under
those accounts even when they otherwise have route permissions. The application
has no key transfer or recovery workflow. Keep the owner account active and protect its passphrase;
losing the passphrase or erasing that account can make existing platform-key
copies unreadable in AverQel. The UI may assign tickets to another admin, but
assignment does not transfer decryption access.

The per-user Composio key replaces reliance on one shared platform credential:
each user connects and controls their own app accounts, and another AverQel
user cannot use that key or claim its hosted sessions. The encryption protects
stored credentials and session references; it does not hide tool requests or
results from the running server, Composio, or the connected app provider.

If the platform key has not been created, the authenticated public-key request
returns `503` and users cannot submit encrypted content. A user who has not
created a personal key receives `404` from the personal-key lookup and is shown
the one-time setup form. During legacy migration, users without personal keys
are skipped until they complete setup; an admin can then retry migration.
Existing keys cannot be replaced through ordinary setup (`409`); creating a
new key without recovering the old one can make prior encrypted messages
unreadable. Browser encryption
does not protect content from a compromised live server that serves altered
code or recipient keys, a compromised client, or already-created plaintext
backups. It applies to support and feedback only, not all AverQel data.

For the exact cryptographic envelope, migration rules, metadata visibility,
retention, and attachment limits, see
[Feedback, support, and durable notifications](05-feedback-support-notifications.md).
For user workflows, see the in-app [Support](../../../frontend/app/documentation/support/page.tsx)
and [Feedback](../../../frontend/app/documentation/feedback/page.tsx) guides.

## Related operator guides

- [Administrator MFA and authentication history](02-auth-oauth-login.md#administrator-mfa-and-account-security-history)
- [Account erasure and tenant-content purge](../security/account-erasure.md)
- [Backend testing and isolated verification](03-testing.md)
