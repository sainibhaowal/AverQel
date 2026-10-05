# 03. Current worktree change and release index

**Reviewed:** 2026-10-05. This index points reviewers to current implementation
contracts and separates source-code state from database and deployment state.
It is not a production certification.

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

Collections are experimental beta in this repository. Their current chat
encryption is not zero-knowledge or server-blind end-to-end encryption. The
collection moderation queue is tenant-admin report triage and its response
schema does not include chat message bodies. Support and feedback content is
readable by the submitter and authorized support staff.

### Identity, settings, and storage

- OAuth and authentication:
  [`../platform/02-auth-oauth-login.md`](../platform/02-auth-oauth-login.md).
- Tenant storage plans:
  [`../deepspace/06-deepspace-plan-storage.md`](../deepspace/06-deepspace-plan-storage.md).
- Retention and recovery:
  [`../storage/02-storage-retention-production-guide.md`](../storage/02-storage-retention-production-guide.md)
  and [`../storage/01-storage-backup-and-disaster-recovery.md`](../storage/01-storage-backup-and-disaster-recovery.md).

## Migration and environment status

The checked source migration graph has a single head, `20261012_0012`. This
was verified with `backend/.venv/bin/alembic heads` on 2026-10-05. The latest
recorded Docker database observation is head `20261012_0011`, dated
2026-10-03 in the rollout record in
[`../platform/05-feedback-support-notifications.md`](../platform/05-feedback-support-notifications.md).
That historical observation is not evidence that the target staging or
production database has applied `0012`.

The `0012` collection-moderation audit migration and the corresponding updated
application must be applied and deployed through the normal release procedure.
Then smoke-test report submission, tenant-scoped moderator listing, status and
note history, unauthorized-role denial, and existing account/collection
deletion in staging. Record the actual target, release commit, migration head,
and results. Do not infer deployment from the source migration graph.

## Verification evidence and limits

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
- The new `0012` migration, current source checkout, and target staging flow
  still need their own migration and smoke-test evidence before deployment
  readiness can be claimed.

Use [`01-end-to-end-handoff.md`](01-end-to-end-handoff.md) for release gates
and [`02-production-e2e-verification.md`](02-production-e2e-verification.md)
for dated test evidence. Each result must identify the exact commit,
environment, migration head, and test inputs.
