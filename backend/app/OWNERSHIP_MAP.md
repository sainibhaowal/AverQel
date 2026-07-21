# Backend ownership map

This document is the migration boundary for the feature-centered backend
layout. It is intentionally non-destructive: it describes ownership and
future destinations without moving, deleting, or duplicating source files.

## Safety rules

1. No source file is deleted during migration.
2. A file is moved only after its imports and tests have been inventoried.
3. Shared code is extracted only when at least two features use the same
   responsibility and the extracted module has a narrow, stable contract.
4. A shared module must not contain a large feature implementation merely
   because one helper is reused.
5. Every move is followed by import validation, focused tests, and a full
   diff review.
6. Large mixed modules remain intact until their internal ownership split is
   designed and tested.

## Target application shape

```text
app/
├── auth/
│   ├── api/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   └── services/
├── providers/
│   ├── api/
│   ├── adapters/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   └── services/
├── deepspace/
│   ├── api/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   ├── autonomy/
│   ├── execution/
│   ├── integrations/
│   ├── memory/
│   ├── missions/
│   ├── orchestration/
│   ├── planning/
│   ├── policy/
│   ├── proactive/
│   ├── runtime/
│   ├── subagents/
│   ├── workspace/
│   └── workers/
├── query/
│   ├── api/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   └── services/
├── documents/
│   ├── api/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   └── services/
├── ingestion/
│   ├── api/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   ├── services/
│   └── workers/
├── integrations/
│   ├── api/
│   ├── connectors/
│   ├── mcp/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   └── services/
├── analytics/
│   ├── api/
│   ├── schemas/
│   └── services/
├── system/
│   ├── api/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   ├── services/
│   └── workers/
├── shared/
│   ├── contracts/
│   ├── events/
│   ├── schemas/
│   ├── types/
│   └── utilities/
├── platform/
│   ├── config/
│   ├── database/
│   ├── errors/
│   ├── logging/
│   ├── middleware/
│   ├── observability/
│   ├── security/
│   └── tenancy/
├── inference/
├── main.py
└── __init__.py
```

The exact target names are intentionally not implemented by this document.
The current package paths remain the source of truth until each migration
step is approved and tested.

## Current ownership map

### Auth

Already feature-centered and should remain the reference pattern:

```text
app/auth/api.py
app/auth/dependencies.py
app/auth/models/
app/auth/repositories/
app/auth/schemas/
app/auth/services/
app/auth/rbac.py
app/auth/roles.py
app/auth/security.py
app/auth/tenancy.py
```

Ownership: authentication, users, profiles, tenants, roles, permissions,
admin user management, token lifecycle, account security, and tenant scope.

### Providers

Current files are split by technical layer:

```text
app/api/v1/providers.py
app/models/providers/
app/repositories/providers/
app/schemas/providers/
app/services/providers/
app/services/security/provider_*
```

Future owner: `app/providers/`.

Provider adapters, registry, model discovery, selection, OAuth, health,
context-window handling, local providers, provider configuration, secrets,
assignments, usage, and provider management belong to this feature.

Provider secret encryption is shared with the security boundary and must be
reviewed before deciding whether it stays in `platform/security` or is exposed
through a provider-owned service interface.

### DeepSpace

Current DeepSpace-owned code:

```text
app/api/v1/deepspace_chats.py
app/api/v1/deepspace_export.py
app/models/deepspace/
app/repositories/deepspace/
app/schemas/deepspace/
app/services/deepspace/
app/deepspace/workers/tasks.py
```

Future owner: `app/deepspace/`.

The current DeepSpace service subpackages already express the correct domain
boundaries:

```text
autonomy       goal contracts, evidence, repair/replan, completion gates
execution      agent loop, tools, permissions, tool contracts, reliability
integrations   DeepSpace export, voice, client proxies
memory         long-term memory and memory operations
missions       mission registry, mission state, events, cancellation
orchestration  public DeepSpace service and master orchestration
planning       task classification, mission planning, validation
policy         autonomy and execution authorization
proactive      triggers and proactive task execution
runtime        context, events, policies, hooks, observability, state machine
subagents      profiles, registry, contexts, result normalization
workspace      file access, shell, coding harness, workspace modes
```

`deepspace_runtime` is the current safe package name. Once it is inside
`app/deepspace/`, its future name can simply be `runtime`; that rename should
not happen until imports and tests are migrated together.

### Query and shared conversation

Current query code:

```text
app/api/v1/chats.py
app/api/v1/queries.py
app/api/v1/intelligence.py
app/models/query/
app/repositories/query/
app/schemas/query/
app/services/query/
```

Future owner: primarily `app/query/`.

However, the following are shared by normal Query and DeepSpace and must not
be duplicated:

```text
conversation persistence
message persistence
message versions
chat repository operations
stream event contracts
structured answer contracts
retrieval primitives
answer rendering primitives
```

The shared portion should eventually be extracted into narrow modules under
`app/shared/` only where it is genuinely feature-neutral. Query-specific
classification, prompt policy, follow-up behavior, and query orchestration
remain Query-owned.

### Documents and collections

Current code:

```text
app/api/v1/documents.py
app/api/v1/collections.py
app/models/documents/
app/repositories/documents/
app/schemas/documents/
app/services/documents/
```

Future owner: `app/documents/`.

Documents, collections, permissions, collection notifications, document
chunks, document metadata, deletion, sharing, and document exports belong to
this feature. Collection real-time chat is currently mixed into the large
collections API and must be assessed during the later split.

### Ingestion

Current code:

```text
app/models/ingestion/
app/repositories/ingestion/
app/services/ingestion/
app/services/ingestion/extractors/
app/ingestion/workers/tasks.py
```

Future owner: `app/ingestion/`.

Upload processing, parsing, OCR, conversion, extraction, chunking, embedding,
table extraction, ingestion jobs, and ingestion workers belong here. Some
document schemas are currently reused by ingestion and need contract review
before they are moved.

### Integrations and MCP

Current code:

```text
app/api/v1/integrations.py
app/api/v1/mcp.py
app/api/v1/voice_routes.py
app/models/integrations/
app/repositories/integrations.py
app/repositories/mcp_events.py
app/schemas/integrations/
app/services/integrations/
app/integrations/workers/tasks_connectors.py
app/integrations/workers/tasks_mcp.py
```

Future owner: `app/integrations/`.

Connector lifecycle, OAuth, sync orchestration, web connectors, MCP
marketplace/runtime/security, voice integration, connector events, and their
workers belong here. DeepSpace-specific voice/export helpers remain under
DeepSpace integrations if they are not general platform integrations.

### Analytics

Current code:

```text
app/api/v1/analytics.py
app/api/v1/dashboard.py
app/schemas/analytics/
app/services/analytics/
```

Future owner: `app/analytics/`.

Dashboard aggregation and analytics response contracts belong here. The
dashboard UI is a composition surface, not necessarily a separate backend
domain.

### System and administration

Current code:

```text
app/api/v1/admin.py
app/api/v1/app_feedback.py
app/api/v1/feedback.py
app/api/v1/health.py
app/api/v1/metrics.py
app/api/v1/support.py
app/schemas/system/
app/models/system/
app/repositories/system/
app/services/system/
app/system/workers/tasks_maintenance.py
```

Future owner: `app/system/`.

Health, metrics, support, feedback, audit logs, idempotency, quality,
storage, rate limits, operational telemetry, and maintenance belong here.

Data deletion is currently spread across document models, document services,
and admin APIs. Its final owner must be decided between Documents and System
based on whether it is a document-specific operation or a platform-wide
privacy operation.

### Platform

Current platform candidates:

```text
app/core/config.py
app/core/context.py
app/core/errors.py
app/core/ids.py
app/core/logging.py
app/core/middleware.py
app/platform/database/
app/services/security/
app/services/system/cache_service.py
app/services/system/otel.py
app/services/system/rate_limit_service.py
app/main.py
```

These should not be copied into every feature. Their final placement between
`platform/` and `shared/` requires an import review. Auth-specific security,
RBAC, roles, and tenancy remain under `app/auth/` unless proven generic.

### Inference

```text
app/inference/main.py
app/inference/runtime.py
app/inference/schemas/inference.py
```

Inference is an infrastructure boundary used by provider/local-runtime
behavior. It may remain a top-level `app/inference/` package or become part of
`platform/inference`; it should not be mixed into ordinary query code.

## Large mixed modules: later split only

These files remain intact during ownership migration:

```text
app/api/v1/deepspace_chats.py
app/api/v1/collections.py
app/services/query/query_service.py
app/services/query/answer_service.py
app/services/deepspace/execution/agent_tools.py
app/services/deepspace/orchestration/master_orchestrator.py
app/services/providers/provider_management_service.py
```

Their future split boundaries are:

```text
deepspace_chats.py
  conversations, runtime, missions/runs, memory, tasks, subagents,
  orchestration, websocket/streaming

collections.py
  collections, permissions, notifications, presence, collection chat,
  collection expiry

query_service.py / answer_service.py
  shared conversation/stream contracts, retrieval, synthesis, query policy,
  provider execution, follow-ups, tracing

agent_tools.py
  tool contracts, tool registry, permission checks, MCP bridge, tool executor

master_orchestrator.py
  mission coordination, lane scheduling, runtime state, approvals,
  continuation/recovery, observability

provider_management_service.py
  provider config management, assignments, health, models, OAuth, secrets
```

## Migration order after approval

1. Freeze this ownership map.
2. Create package markers and target directories only.
3. Migrate one complete feature at a time, starting with Providers or
   Documents—not the shared Query/DeepSpace boundary.
4. Keep compatibility imports while callers are migrated.
5. Extract shared contracts only after usage is verified.
6. Split the large mixed modules one boundary at a time.
7. Run import checks, focused tests, API route checks, and the full test suite.
8. Review the final diff for missing files, accidental deletions, and changed
   route behavior before committing.
