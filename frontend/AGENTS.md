<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## AverQel frontend work

Follow the repository-root [`AGENTS.md`](../AGENTS.md) and
[`AGENT_ENGINEERING_STANDARD.md`](../AGENT_ENGINEERING_STANDARD.md) for the
plan-first workflow, security boundaries, tests, documentation review, and
pre-push checks. For every frontend behavior change, add focused Vitest or
Playwright coverage at the appropriate level and review the relevant in-app
help under `app/documentation/`. Use the `production-change` skill before
implementation and `documentation-impact` after it. Keep the existing
Next.js-specific rule above:
read the installed framework guide under `node_modules/next/dist/docs/` before
using version-sensitive APIs.
