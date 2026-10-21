# 03. Current worktree change and release index

**Reviewed:** 2026-10-20. This index points reviewers to current implementation
contracts and separates source-code state from database and deployment state.
The inspected checkout contains uncommitted changes. This index is not a
production certification.

## Product areas and implementation guides

### Documents Hub

- User journey and access tiers:
  [`../library/09-documents-hub-user-guide.md`](../library/09-documents-hub-user-guide.md).
- Ingestion, extraction, OCR, recovery, and security:
  [`../library/05-documents-production.md`](../library/05-documents-production.md),
  [`../library/06-ingestion-ocr.md`](../library/06-ingestion-ocr.md), and
  [`../library/08-ingestion-recovery-security-observability.md`](../library/08-ingestion-recovery-security-observability.md).
- Organization, collaboration, webhooks, and API contracts:
  [`../library/07-documents-hub-workflows.md`](../library/07-documents-hub-workflows.md).

### Query

- Retrieval and source-document behavior:
  [`../capabilities/02-document-intelligence.md`](../capabilities/02-document-intelligence.md)
  and [`../capabilities/07-ocr-rag-library-sandbox-artifacts.md`](../capabilities/07-ocr-rag-library-sandbox-artifacts.md).

### DeepSpace

- Runtime, queueing, retries, tools, and durable events:
  [`../deepspace/04-deepspace-agent-runtime.md`](../deepspace/04-deepspace-agent-runtime.md)
  and [`../deepspace/05-deepspace-operations-runbook.md`](../deepspace/05-deepspace-operations-runbook.md).
- DeepSpace working Library attachments:
  [`../deepspace/09-composer-library-attachments.md`](../deepspace/09-composer-library-attachments.md).
- Memory lifecycle and context retrieval:
  [`../deepspace/10-deepspace-memory-moderation.md`](../deepspace/10-deepspace-memory-moderation.md)
  and [`../deepspace/08-selective-context-retrieval.md`](../deepspace/08-selective-context-retrieval.md).
- Research, sandbox, artifacts, schedules, MCP, and voice are indexed in
  [`../README.md`](../README.md) under Capabilities and DeepSpace.

### Electron desktop

- Packaging targets, app-icon sizing, local setup, and window behavior:
  [`../../../applications/desktop/README.md`](../../../applications/desktop/README.md).
- The current shell has no notification-area tray icon. Closing the window
  exits AverQel; minimizing leaves it in the taskbar. A second launch focuses
  the existing window instead of creating another process.

### MCP and Composio

- Current hosted app catalog, user-owned project keys, callback, data handling,
  and troubleshooting:
  [`../capabilities/mcp/03-composio-hosted-mcp.md`](../capabilities/mcp/03-composio-hosted-mcp.md).
- Shared MCP runtime, broker, ownership, policy, and approval contract:
  [`../capabilities/06-mcp-connections.md`](../capabilities/06-mcp-connections.md).
- The current Marketplace uses Composio's live catalog. Each user supplies an
  encrypted project key scoped to their tenant/account; the running backend
  decrypts it for Composio requests. OAuth apps require the configured public
  callback origin. Source implementation does not establish live deployment
  readiness.

Documents Hub owns source files; Query retrieves evidence from eligible
sources; DeepSpace has a separate working Library for conversation files and
outputs. Do not use “Library” without naming which product area it belongs to.

### Collections, support, and notifications

- Collection chat and encryption custody:
  [`../library/10-collection-chat-encryption.md`](../library/10-collection-chat-encryption.md),
  [`../library/11-collection-chat.md`](../library/11-collection-chat.md), and
  [`../library/12-collection-rooms.md`](../library/12-collection-rooms.md).
- Collection hardening, report moderation, migration, and deployment limits:
  [`collection-bridge-hardening.md`](collection-bridge-hardening.md).
- Feedback, ticket conversations, attachments, notification preferences,
  email outbox, and rollout evidence:
  [`../platform/05-feedback-support-notifications.md`](../platform/05-feedback-support-notifications.md).
- Six platform-admin modules, access requirements, UTC timestamps, audit
  outcomes, short identifiers, and encryption boundaries:
  [`../platform/06-platform-administration.md`](../platform/06-platform-administration.md).

Collections are experimental beta in this repository. Their current chat
encryption is not zero-knowledge or server-blind end-to-end encryption. The
collection moderation queue is tenant-scoped report triage for users assigned
the `collection_moderator` role; its response schema does not include chat
message bodies. New and migrated support and feedback content is encrypted in
the browser for the submitter and the single platform-key owner. Other allowlisted
administrators cannot unlock that key, so the current queue UI cannot open for
them. A browser migration handles existing plaintext rows and support
attachments; users must
initialize their key first, and old backup snapshots retain plaintext until
expiry. Metadata remains service-visible, encrypted attachments cannot be
server-scanned, and a compromised live server can replace browser code or
recipient keys. Legacy support and feedback manager roles do not grant access
to either platform queue, and the platform staff-role assignment endpoint has
been removed.

The platform key is tied to its creator's account. The current product has no
transfer or recovery flow; keep the key-owner account active and protect its
passphrase. Erasing that account removes its stored key backup and can make
existing platform-key copies unreadable in AverQel.

Users create their support/feedback key once. Its private key is unlocked in
browser memory across those two pages and locks after four hours of inactivity,
on sign-out, login-session expiry, reload, or tab close. This is distinct from
TOTP MFA. The four-hour period is an idle timeout, not a fixed 12-hour session.

### Identity, settings, and storage

- OAuth and authentication:
  [`../platform/02-auth-oauth-login.md`](../platform/02-auth-oauth-login.md).
- Platform-admin route access, six admin modules, audit display, and encryption
  distinctions:
  [`../platform/06-platform-administration.md`](../platform/06-platform-administration.md).
- Tenant storage plans:
  [`../deepspace/06-deepspace-plan-storage.md`](../deepspace/06-deepspace-plan-storage.md).
- Retention and recovery:
  [`../storage/02-storage-retention-production-guide.md`](../storage/02-storage-retention-production-guide.md)
  and [`../storage/01-storage-backup-and-disaster-recovery.md`](../storage/01-storage-backup-and-disaster-recovery.md).

## Migration and environment status

The checked source migration graph has a single head, `20261019_0004`. This
was verified with `cd backend && .venv/bin/alembic heads` on 2026-10-20.
That command reads the source migration graph; it does not inspect a database.
The latest recorded Docker database observation in this repository is the
historical head `20261012_0011` from 2026-10-03, which predates the current
Composio migrations and is not evidence of any current development, staging,
or production database state. No current target database migration state is
recorded here.

Apply the source migrations to a disposable isolated database before release,
then follow the documented staging migration and feature-smoke procedure for
the actual target. Record the target, release commit, migration head, and
results. Do not infer database or deployment state from the source migration
graph.

## Verification evidence and limits

- On 2026-10-20, desktop lifecycle tests passed (2/2), title-bar/preload tests
  passed (3/3), and a Linux `.deb` was built and inspected locally. The package
  was not installed. The full desktop suite reported 28 passes and one existing
  brand-asset staging mismatch. The frontend production build stopped at
  unrelated type errors in generated admin route references and
  `app/dashboard/layout.tsx`; the package therefore used the existing
  `frontend/out`. These checks do not establish installed-app or deployment
  state.
- On 2026-10-20, a documentation audit covered all 100 tracked and untracked
  source Markdown files. All 273 local links and Markdown heading fragments
  resolved, and `git diff --check -- '*.md' '*.MD'` passed. External URL
  reachability was not checked.

- On 2026-10-05, the documentation-focused frontend checks passed: Vitest
  reported 4 files and 10 tests passed; TypeScript, ESLint for the updated
  memory guide, and the production build passed; the build generated 88 pages.
  A repository Markdown local-link scan and `git diff --check` also passed.
  These checks validate the documentation routes and local source only.
- The full-suite and browser results in the 2026-09-27 release reports are
  historical local evidence. They do not validate changes added afterward.
- The 2026-10-03 support/notification rollout record reports a targeted 47-test
  regression selection and local frontend lint, TypeScript, and production
  image build; its database observation stopped at `0011`.
- SMTP was not live-tested in that record. Email needs valid deployment SMTP,
  worker, and scheduler configuration. No paid-subscription lifecycle source
  exists; provider notifications are from explicit tests, not continuous
  monitoring.
- The source graph currently includes Composio credential migrations through
  `20261019_0004`; no target database or live Composio OAuth/tool flow was
  inspected during this documentation pass.

Use [`01-end-to-end-handoff.md`](01-end-to-end-handoff.md) for release gates
and [`02-production-e2e-verification.md`](02-production-e2e-verification.md)
for dated test evidence. Each result must identify the exact commit,
environment, migration head, and test inputs.
