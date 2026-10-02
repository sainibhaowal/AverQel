# 01. Sandboxed Python/SQL execution audit

## 1. What it does

1. Runs bounded Python and read-only SQL for calculations, table analysis,
   CSV/JSON workflows, and chart preparation.
2. Keeps arbitrary code outside the API and worker containers.
3. Returns structured stdout, stderr, status, duration, and generated-file
   metadata.
4. DeepSpace may stage explicitly selected Library files for one run. The
   file lookup is tenant/user/conversation scoped and the bytes are removed
   with the executor's temporary directory.

```mermaid
sequenceDiagram
    actor User
    participant UI as DeepSpace UI
    participant API as AverQel API
    participant Box as Isolated executor
    User->>UI: Ask for calculation or data analysis
    UI->>API: Authenticated execute request
    API->>API: Validate tenant, language, limits, and policy
    API->>Box: Send bounded code or read-only SQL
    Box-->>API: Result, status, and duration
    API-->>UI: Tool activity with result or safe error
```

| Public use case | What the user gets | Safety boundary |
| --- | --- | --- |
| Calculate a total or formula | A reproducible numeric result | CPU, memory, time, and output limits |
| Analyze CSV/JSON data | Rows, summaries, or chart-ready data | Ephemeral files; no host mounts |
| Analyze a Library file | Python can open the staged filename; OCR/extracted text is also available as `<filename>.extracted.txt` | At most five files, 10 MB each, 20 MB total |
| Run a SQL query | Read-only rows from supplied data | `SELECT`/`WITH` only; mutations rejected |

## 2. Existing foundation

1. CodeMirror already supports Python and SQL editing.
2. DeepSpace already has tenant authentication, Library storage, Celery, and
   structured tool dispatch.
3. The new isolated service is `backend/sandbox-executor/`.

## 3. Exact implementation

1. Client/policy: `backend/app/deepspace/services/sandbox_executor.py`.
2. API: `POST /api/v1/deepspace/sandbox/execute` in
   `backend/app/deepspace/api/sandbox.py`.
3. Assistant tool: `sandbox_execute` in
   `backend/app/deepspace/services/chat_service.py`.
4. Container policy: `backend/sandbox-executor/Dockerfile` and
   `backend/docker-compose.prod.yml`.
5. Configuration: `deepspace_sandbox_*` settings and the environment examples.

## 4. Execution flow

1. The authenticated user submits code or the model selects the tool.
2. AverQel validates language, size, timeout, and deployment state.
3. The request goes to the internal executor using a bearer token.
4. The executor rejects unsafe imports and mutating SQL, then runs in an
   ephemeral directory with bounded resources.
5. The result returns to the normal DeepSpace timeline; no provider receives
   host access.

## 5. What users see

1. A calculation result or SQL result appears as a normal tool activity.
2. Failures are clearly shown as unavailable, rejected, or timed out.
3. The model cannot truthfully claim execution when the sandbox is disabled.

## 6. Security audit

1. No host filesystem mounts or public ports.
2. Internal-only Docker network, read-only root, dropped capabilities,
   `no-new-privileges`, PID/CPU/memory limits, and strict request/output caps.
3. Network and host-oriented imports are rejected before execution.
4. API authorization remains `queries:run` and tenant identity comes from the
   authenticated context, never from a user-supplied tenant field.

## 7. Verification and production state

1. Direct tests returned Python `4` and read-only SQL rows.
2. Unauthorized requests returned `401`; unsafe imports were rejected.
3. Ruff, mypy, backend tests, Compose validation, and the sandbox image build
   passed.
4. Production operators must set a strong token and enable the
   `sandbox-execution` profile. It remains disabled by default by design.
