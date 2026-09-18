# 07. Production end-to-end verification report

This report records the reproducible checks for the six advanced capabilities.
No provider secret or temporary API key is stored in the repository.

The dated results below are historical evidence from the environments and
commits named in each section. They do not automatically certify the current
uncommitted worktree. The current release gate is tracked in
`00-end-to-end-handoff.md` and must be rerun after the pending migrations,
runtime changes, provider changes, and frontend changes are committed.

## 1. Verification scope

1. Backend APIs, DeepSpace tool schemas, provider adapters, research tools,
   document operations, artifact jobs, schedules, and MCP policy paths.
2. Frontend DeepSpace panels, generated-file rendering, provider settings,
   Markdown/diagram rendering, reconnect behavior, and MCP controls.
3. Compose configuration, live API health, and the isolated service profiles.
4. OpenZen model discovery and a bounded live generation probe using a
   temporary user-supplied credential.
5. OCR-to-sandbox staging, generated artifact collection, and generic artifact
   preview/download behavior.

## 2. Automated evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Complete backend regression suite | Passed | `backend/.venv/bin/pytest -q backend/tests` reached `[100%]` with no failures after the schedule error-code fix |
| Targeted capability/provider suite | Passed | Advanced capability, OpenZen, provider-tool, artifact, and research tests reached `[100%]` |
| Complete frontend suite | Passed | 81 test files and 301 tests passed |
| Compose production configuration | Passed | `docker compose --env-file backend/.env.localprod.example -f backend/docker-compose.prod.yml config --quiet` |
| Live API liveness | Passed | `GET /api/v1/health/live` returned HTTP 200 and `{"status":"ok"}` |
| Live API readiness | Passed | `GET /api/v1/health/ready` returned HTTP 200 and `{"status":"ok"}` |
| OpenZen model discovery | Passed | Authenticated `/zen/v1/models` returned HTTP 200, 70 models, including `nemotron-3.5-lightning-free` |

## 3. Live OpenZen generation result

1. The request used the OpenCode Zen base URL and the requested
   `nemotron-3.5-lightning-free` model.
2. The upstream endpoint returned HTTP 400 with `MissingSessionID` and the
   message that the free tier can only be used in the OpenCode client.
3. This is an upstream provider policy response, not an AverQel crash or a
   credential leak. AverQel must report the provider error and cannot bypass
   that restriction.
4. The temporary key was passed only to the process environment for the
   probe, was never printed, committed, or written to an AverQel file.

### Current provider-policy evidence (2026-09-17)

The running worker reproduced the upstream response for the requested free
model: HTTP 403 with `OpenCode's free tier can only be used from within
OpenCode`. DeepSpace classifies this as `OPENCODE_FREE_TIER_CLIENT_ONLY`,
preserves the user's selected model, and reports the provider policy clearly.
AverQel cannot bypass a provider's client-entitlement restriction; a Zen
model/account that permits API access is required for generation inside
AverQel.

## 4. Runtime activation conditions

1. The feature branch must be merged and the API, worker, scheduler, and
   frontend images rebuilt before the running deployment contains the latest
   migrations and routes.
2. Sandbox execution is disabled by default. Operators must set a strong
   `AKS_DEEPSPACE_SANDBOX_TOKEN`, set
   `AKS_DEEPSPACE_SANDBOX_ENABLED=true`, and start the
   `sandbox-execution` profile.
3. JavaScript browser rendering is a separate `research-browser` profile and
   must be smoke-tested with the target egress policy before enabling it.
4. OpenZen Nemotron free-tier generation requires a provider-supported client
   path; model discovery alone does not prove generation entitlement.

## 4.1 Localhost activation evidence (2026-09-14)

1. The local environment contains one authoritative sandbox switch:
   `AKS_DEEPSPACE_SANDBOX_ENABLED=true`. The obsolete
   `AKS_DISABLE_SANDBOX` override is absent, so the enabled setting is not
   silently negated.
2. `averqel-sandbox-executor` is healthy and returns `{"status":"ok"}` from
   its internal `/health` endpoint. An authenticated smoke execution returned
   `20.0` for `print(sum([10, 20, 30]) / 3)`.
3. `averqel-research-egress-proxy` is running and
   `averqel-research-renderer` is healthy. An authenticated render of a public
   page returned HTML with HTTP 200. The renderer remains isolated on its
   internal network and accepts only the configured bearer token.
4. The rebuilt API is attached to both internal capability networks while
   retaining its normal application network. The API liveness endpoint still
   returns HTTP 200 after activation.
5. These checks validate service wiring and isolation; authenticated browser
   user-flow tests still require a test account and are intentionally not
   represented by fabricated credentials.

## 5. Production conclusion

1. AverQel's six capability implementations are present, covered by tests,
   and protected by existing authentication, tenant isolation, and resource
   policies.
2. The local application health endpoints and frontend are responding.
3. Production activation is still a deployment operation, not a code gap.
4. The only unsuccessful live probe was the requested OpenZen free model,
   rejected by OpenZen before model output was generated.
5. The optional sandbox profile is intentionally not started by the default
   localhost Compose stack; enabling it requires the per-environment token in
   `.env.localprod` or `.env.vps` and a profile rebuild.

## 6. Reasoning privacy and rendering regression

1. Provider reasoning events are now treated as private backend state; raw
   chain-of-thought is not streamed through SSE or persisted in assistant
   metadata.
2. The DeepSpace activity panel renders only safe tool, plan, approval,
   verification, and error activity. Legacy `thinking` history is ignored.
3. The query thinking panel shows a private-reasoning notice instead of raw
   provider text, preventing giant prompt-like paragraphs from reaching the
   browser.
4. Backend and frontend regression tests cover this behavior, including the
   original repeated-garbage failure shape.

## 7. Library upload and preview coverage

1. Library upload sessions accept Unicode-safe file names and infer a known
   type when browsers declare `application/octet-stream`.
2. Common Office, OpenDocument, data, archive, image, audio, and video MIME
   types are normalized before storage while existing size, malware, tenant,
   and path-safety checks remain enforced.
3. PPTX and Office text extracted by the existing ingestion router are shown
   in the Library preview; spreadsheet extraction falls back to readable text
   when a browser cannot parse a legacy workbook.
4. Multi-file uploads continue to use independent resumable sessions with
   bounded concurrency, so one rejected file cannot corrupt another upload.

## 8. Current worktree release status (2026-09-18)

The current worktree contains additional uncommitted queue, runtime, metrics,
context, provider, frontend, and migration changes. Only a focused DeepSpace
blank-response regression test and Python compilation have been rerun during
the current audit. The full backend/frontend/e2e evidence in this document
must therefore be rerun before this worktree is called production-ready.
