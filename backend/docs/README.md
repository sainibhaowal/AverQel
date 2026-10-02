# AverQel backend documentation

This directory contains the implementation contracts, operational runbooks,
verification evidence, and release policies for AverQel. Read this file first;
the documents are grouped by the order in which the system is understood and
operated.

## Documentation map

### 00. Release status

- [End-to-end handoff](release/01-end-to-end-handoff.md) — overall system,
  current capability status, migrations, and release gates.
- [Production E2E verification](release/02-production-e2e-verification.md)
  — reproducible local evidence and remaining staging/VPS gates.
- [Current worktree change index](release/03-current-worktree-change-index.md)
  — feature families, source areas, migrations, and current verification.

### 01. Capabilities

- [Sandbox execution](capabilities/01-sandbox-execution.md)
- [Document intelligence](capabilities/02-document-intelligence.md)
- [Browser research](capabilities/03-browser-research.md)
- [Artifact generation](capabilities/04-artifact-generation.md)
- [Scheduled jobs](capabilities/05-scheduled-jobs.md)
- [MCP connections](capabilities/06-mcp-connections.md)
- [MCP current release status](capabilities/mcp/01-current-release-status.md)
- [OCR, RAG, Library, sandbox, and artifacts](capabilities/07-ocr-rag-library-sandbox-artifacts.md)
- [Public landing and capability directory](capabilities/08-public-landing-and-capabilities.md)
- [Advanced capability index](capabilities/09-advanced-capabilities-index.md)
- [Advanced workspace capabilities](capabilities/10-advanced-workspace-capabilities.md)
- [Voice and realtime audio](capabilities/11-voice-and-realtime-audio.md)

### 02. DeepSpace

- [Low-latency execution](deepspace/01-deepspace-low-latency.md)
- [Agent harness implementation plan](deepspace/02-deepspace-agent-harness-implementation-plan.md)
- [Agent task loop](deepspace/03-deepspace-agent-loop.md)
- [Runtime agent loop](deepspace/04-deepspace-agent-runtime.md)
- [Operations runbook](deepspace/05-deepspace-operations-runbook.md)
- [Plans and tenant storage](deepspace/06-deepspace-plan-storage.md)
- [Retention policy](deepspace/07-deepspace-retention-policy.md)
- [Selective context retrieval](deepspace/08-selective-context-retrieval.md)
- [Composer Library attachments](deepspace/09-composer-library-attachments.md)
- [Memory moderation lifecycle](deepspace/10-deepspace-memory-moderation.md)

### 03. Library and document processing

- [Heavy-file processing architecture](library/01-heavy-file-processing-architecture.md)
- [Library Office preview](library/02-library-office-preview.md)
- [Library editing and exports](library/03-library-editing-and-exports.md)
- [Large Library imports](library/04-large-library-imports.md)
- [Documents production contract](library/05-documents-production.md)
- [OCR ingestion](library/06-ingestion-ocr.md)
- [Documents Hub workflows](library/07-documents-hub-workflows.md)
- [Ingestion recovery, security, and observability](library/08-ingestion-recovery-security-observability.md)
- [Documents Hub user guide](library/09-documents-hub-user-guide.md)
- [Sealed collection chat](library/10-collection-chat-encryption.md)

### 04. Platform foundations

- [API reliability](platform/01-api-reliability.md)
- [OAuth login](platform/02-auth-oauth-login.md)
- [Backend testing](platform/03-testing.md)
- [Current end-to-end verification](platform/04-end-to-end-verification.md)
- [Realtime websocket events](platform/04-realtime-events.md)

### 05. Storage and recovery

- [Backup and disaster recovery](storage/01-storage-backup-and-disaster-recovery.md)
- [Storage retention production guide](storage/02-storage-retention-production-guide.md)
- [Storage retention planning records](storage/retention/README.md)

### Roadmap

- [DeepSpace document attachments and conversion](roadmap/01-deepspace-document-attachments-and-conversion.md)

## Release-status convention

“Available locally” means the implementation and local verification are
complete. “Deployment gate remains” means the feature still needs isolated
VPS/staging proof, real external credentials, or a physical-device test. These
labels are intentional and must not be replaced with a production claim until
the documented gate is completed.

Automatic archive is opt-in per tenant and archive-first. Permanent purge is
disabled. Existing authentication, tenant isolation, DeepSpace chat/queue
behavior, provider behavior, and storage contracts remain separate from this
documentation organization.
