# AverQel AI Agent Engineering Standard

This is the detailed engineering rulebook for AI coding agents and human
contributors. The root `AGENTS.md` is the always-loaded project summary; the
Codex, Claude Code, Gemini CLI, and GitHub Copilot entry points direct agents
here for implementation work. Skills provide focused procedures for recurring
tasks.

These instructions guide agents. CI, tests, hooks, permissions, and protected
branches provide technical enforcement. Do not claim that Markdown alone can
guarantee an agent or a local Git command will obey a rule.

## 1. Plan before implementation

Before changing code, tests, configuration, or release workflows, inspect the
current implementation and working tree, then present a plan before coding.
Scale the plan to the change: a small fix can use a short checklist; a cross-
system or high-risk change needs the full scope below.

The plan must state:

1. **What and why:** requested outcome, user impact, and acceptance conditions.
2. **Current state:** existing behavior, data flow, dependencies, and relevant
   safeguards found in the repository.
3. **Exact scope:** files and folders, plus affected routes, APIs, schemas,
   migrations, jobs, events, storage, integrations, test suites, and docs.
4. **Implementation:** ordered changes and compatibility strategy.
5. **Safety:** risks, security boundaries, failure modes, rollback or recovery
   considerations, and behavior that must not break.
6. **Evidence:** tests, static checks, workflow validation, documentation review,
   and any environment limits needed to verify the result.

After presenting the plan, start the authorized implementation without waiting
for routine approval. Ask only when missing information blocks a safe, correct
implementation or when the next action is destructive, external, or otherwise
requires explicit authorization. A plan is not permission to deploy, publish,
delete data, change a live service, or push code.

## 2. Critical engineering review

Do not code from assumptions. Trace the existing implementation and its callers
first. Review the relevant tests, schemas, API contracts, configuration,
workflows, and operating documentation. Use current checked-in docs and source
as the authority when framework behavior may differ from prior knowledge.

For each change, assess the relevant items below and record the ones that affect
design or validation:

- Functional requirements, edge cases, invalid input, empty state, and failure
  behavior.
- Identity, authentication, authorization, role boundaries, tenant isolation,
  encryption, key handling, and secret exposure.
- Data ownership, transactions, migration compatibility, retention, deletion,
  backup, and recovery.
- Public API and event compatibility, job idempotency, retries, timeouts,
  concurrency, ordering, and partial failure.
- Storage, cache, queue, memory, and external-provider behavior.
- Frontend accessibility, responsive behavior, loading/error states, and
  whether the interface truthfully reflects backend state.
- Electron process lifecycle, renderer isolation, local data boundaries, and
  packaging behavior for desktop changes.
- Performance, observability, auditability, operational impact, and rollback
  needs where they are relevant.

Prefer the smallest complete change that preserves existing architecture. Do
not introduce speculative abstractions, duplicate dependencies, parallel
Electron runtimes, weakened security, hidden fallbacks, or broad unrelated
refactors to make a local check easier. State and resolve tradeoffs explicitly.

## 3. Preserve product and security boundaries

- Preserve existing API behavior unless the task deliberately changes it and
  includes compatibility notes, tests, and documentation.
- Keep backend operations authenticated, authorized, and tenant-scoped. Never
  trust a user or tenant identifier supplied by an untrusted client without
  validating it against the authenticated principal.
- Keep credentials encrypted and out of logs, prompts, browser payloads, and
  release artifacts. Do not weaken crypto, authorization, validation, or audit
  controls to make a test pass.
- Treat destructive data operations, database migrations, service restarts,
  production configuration, release workflows, and deployment workflows as
  high impact. Inspect the full effect before acting.
- Keep NeoSIS as its own source repository and runtime. AverQel Desktop bundles
  the pinned NeoSIS runtime in the existing Electron shell; do not package a
  second Electron application. Desktop release and AverQel VPS deployment are
  separate workflows.
- Protect pre-existing tracked and untracked work. Do not reset, clean, stash,
  revert, overwrite, or stage user changes as a shortcut.

## 4. Tests are part of each behavior change

Every new or changed function, branch, state transition, API behavior, or
security rule needs behavior-focused test coverage at the appropriate level.
Bug fixes need a regression test that would fail before the fix. Cover normal
behavior, relevant boundary cases, and failure paths; for authorization changes,
include denied and cross-tenant cases where applicable.

| Change | Expected evidence |
| --- | --- |
| Backend logic or API | Focused unit tests; API/integration tests for persistence, permissions, or external boundaries |
| Database schema or migration | Migration/upgrade coverage against a disposable database and compatibility review |
| Frontend behavior | Component or integration tests for states and interactions; browser E2E for high-risk critical user flows |
| Desktop process or packaging | Tests for process lifecycle and routing plus a package/build check for each affected target |
| Release or CI workflow | YAML parse and workflow-specific lint, then inspect the affected workflow path and artifacts |
| Documentation-only change | Validate paths, commands, examples, and internal links; no runtime test is implied |

Do not add tests that only execute lines without checking behavior. Do not add
skip/xfail markers to silence failures. Investigate unexpected skips; report
intentional platform or environment skips with their reason. A subset passing
is not evidence that the complete suite passed.

Never point tests at active development, staging, or production systems.
Database-backed backend tests must use
`./backend/scripts/test-isolated.sh`; database-free tests may use the documented
`unit_no_db` selection. Frontend browser tests must follow
`backend/docs/security/isolated-test-runs.md`. Read the `safe-testing` skill
before running integration or E2E tests.

## 5. Documentation is part of completion

After every implementation, perform and report a documentation-impact review,
including for small fixes. Update the relevant docs in the same change whenever
behavior, setup, API contracts, roles, configuration, errors, security, data
handling, release, or operator procedures changed. If no documentation needs
to change, state why in the completion report instead of silently skipping the
review.

| Change area | Review and update when applicable |
| --- | --- |
| User-visible web or desktop behavior | In-app help under `frontend/app/documentation/`, user-facing README, screenshots or workflow steps |
| Backend API or integration | API schema/OpenAPI, API examples, permissions, errors, compatibility notes |
| Data model or migration | Schema/data-flow docs, upgrade and recovery steps, retention and deletion behavior |
| Configuration or local development | `.env` examples, setup docs, command references, prerequisites, defaults |
| Tests and quality gates | Test guide, isolation notes, CI/pre-commit commands, expected fixtures and limitations |
| Desktop, release, or deployment | `applications/desktop/README.md`, release/deploy guide, artifact and rollback details |
| Security-sensitive behavior | Threat boundary, auth/tenant rules, secret handling, audit and incident implications |

Write for the right audience: end users, workspace administrators, operators,
API integrators, or developers. Use a clear title, purpose, prerequisites,
steps, expected result, limitations/errors, and related links as relevant. Use
tables for settings, roles, routes, inputs/outputs, state transitions, and
comparisons when they make facts easier to scan. Use examples or Mermaid
diagrams when they clarify real workflows; do not add decoration or unsupported
claims. Keep commands copyable and links repository-relative and valid. Do not
present historical test results as current evidence.

## 6. Pre-push and CI gate

Install `pre-commit` and the repository hooks once after cloning:

```bash
python -m pip install pre-commit
pre-commit install
bash .github/scripts/install-pre-push-hook.sh
```

The pre-push hook requires `pre-commit` and either Docker or a local Actionlint
binary. Docker runs the pinned Actionlint image if a local binary is not
available.

The hook validates every commit being pushed in a temporary detached Git
worktree. It runs the entire `.pre-commit-config.yaml` suite with
`pre-commit run --all-files`, then Actionlint on every workflow. It uses a local
Actionlint binary when available or the pinned official `rhysd/actionlint`
Docker image otherwise. The temporary worktree is removed after the run; hook
formatting changes never rewrite the active checkout. If a formatter changes
files in that isolated worktree, the hook blocks the push and lists those files
so they can be corrected and committed.

The same workflow lint runs as the `GitHub Actions workflow lint` job on every
pull request and is included in the required `CI Passed` result. To run the
pre-commit checks manually, use a clean or disposable worktree because the
current config includes repository-wide formatters:

```bash
pre-commit run --all-files
docker run --rm --volume "$PWD:/repo:ro" --workdir /repo rhysd/actionlint:1.7.12 -color
git diff --check
```

Also run the tests and static checks for changed paths, and inspect the full
final diff and staged file list. Do not bypass the hook or push if a required
check fails. After pushing, inspect the actual GitHub Actions results for that
commit and keep fixing failures until the required checks are green; never
report a check from a different commit as evidence for the pushed commit.

**Pre-commit safety note:** the current `.pre-commit-config.yaml` contains
Ruff `--fix`, Black, whitespace, and EOF hooks that can rewrite files. The
installed pre-push hook protects the active checkout by running them against
the exact pushed commit in an isolated worktree. Never discard unrelated edits
to get a clean hook run.

The release workflow is manual and publishes Linux `.deb` and Windows `.exe`
desktop packages. It does not deploy the VPS. The VPS workflow is a separate
manual operation. Never trigger either workflow unless the user explicitly
requested it.

## 7. Keep agent guidance accurate

When work reveals a durable, reusable project rule, update this standard and
the relevant skill in the same task. Keep root agent files short and point them
here; do not copy a long rulebook into every vendor-specific file. Update only
skills relevant to the new rule, and remove outdated or contradictory guidance.
Review instruction files when architecture, test commands, CI, release, or
security boundaries change.

Markdown instructions and skills are not a hard enforcement mechanism. Where
a rule must hold regardless of an agent's choice, enforce it with code, tests,
permissions, CI, branch protection, or a Git hook and verify that mechanism.

## 8. Completion evidence

Before saying work is complete, report:

- What changed and why, with the key file paths.
- Which behavior, tests, and docs were added or updated.
- Exact commands run and pass/fail/skip counts; distinguish local from CI and
  production evidence.
- CI status for the current commit when a push was requested.
- Any limitation or remaining risk. Never use “perfect,” “fully verified,” or
  “production-ready” without evidence that supports that exact claim.
