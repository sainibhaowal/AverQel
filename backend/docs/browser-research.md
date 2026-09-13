# 03. Controlled browser research audit

## 1. What it does

1. Renders public JavaScript pages that the secure text reader cannot parse.
2. Supports research retrieval only; it is not an unrestricted browser.
3. Prevents cookies, credentials, downloads, private-network access, and
   side-effecting interactions.

## 2. Exact implementation

1. Adapter: `backend/app/deepspace/services/browser_reader.py`.
2. Renderer: `backend/research-renderer/server.mjs`.
3. Egress policy: `backend/research-renderer/squid.conf`.
4. Deployment profile: `research-browser` in
   `backend/docker-compose.prod.yml`.
5. Research orchestration and snippet-only fallback:
   `backend/app/deepspace/services/research_pipeline.py`.

## 3. Execution flow

1. Research intent selects deterministic query planning.
2. The secure URL validator checks the target before rendering.
3. Chromium runs behind Squid on an internal network.
4. Every browser request is checked again; blocked requests are aborted.
5. Extracted HTML is bounded and returned to evidence ranking.
6. If rendering fails, the source is labeled snippet-only/unavailable.

## 4. What users see

1. Current pages requiring JavaScript can contribute fetched evidence.
2. Sources that cannot be opened are visibly distinguished from verified
   fetched pages.
3. Research progress and citations continue through the normal DeepSpace SSE.

## 5. Security audit

1. SSRF checks reject private, link-local, loopback, and service hostnames.
2. Squid is the only browser egress path and has internal-destination ACLs.
3. Renderer requests require a strong bearer token and strict timeouts.
4. No user-approved side-effecting automation is exposed by this profile.

## 6. Verification and production state

1. The renderer and egress proxy are health-checked in Compose.
2. The current local deployment reports the renderer healthy.
3. Operators must smoke-test the profile in their target environment before
   enabling it; the profile is deliberately separate from normal API traffic.
