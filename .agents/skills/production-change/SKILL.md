---
name: production-change
description: Plan and implement AverQel code, feature, bug-fix, security, data, API, UI, or workflow changes with critical review, tests, documentation, and production safety. Use for every implementation task.
---

# Production change harness

This workflow applies to every implementation task. Read
`AGENT_ENGINEERING_STANDARD.md` and inspect the working tree before editing.

## Plan before coding

Present a plan before making changes. Include:

1. What outcome is requested, why, and how success will be judged.
2. Current behavior and safeguards discovered in the codebase.
3. Exact affected files, routes, APIs, schemas, migrations, jobs, events,
   storage, integrations, tests, and documentation.
4. Implementation order and compatibility approach.
5. Security, data, availability, and regression risks; what must not break.
6. Tests and other evidence needed to verify the change.

Keep a tiny fix plan short. For a cross-system or high-impact change, include a
scope table and explicit rollback or recovery considerations. After sharing the
plan, proceed without waiting for routine approval. Do not treat that as
authorization to deploy, publish, delete data, or push.

## Think critically and trace the system

- Inspect implementation, callers, schemas, tests, docs, and workflows before
  settling on a design. Verify framework APIs from the installed version's docs
  when versions matter.
- Trace input to persistence and response, including authorization, tenant
  context, events, caches, jobs, background workers, and external services as
  applicable.
- Identify success, invalid input, boundary, retry, timeout, concurrent, and
  partial-failure behavior. Check backward compatibility and safe rollout.
- Preserve auth, tenant isolation, credential encryption, privacy, API
  contracts, data retention, observability, and existing integrations.
- Prefer the smallest complete implementation. Avoid speculative layers,
  duplicate dependencies, unsafe fallback behavior, broad unrelated refactors,
  or tests that merely execute code without asserting behavior.
- Preserve every pre-existing tracked and untracked change. Never use reset,
  clean, stash, or broad revert commands to simplify your work.

## Tests and regressions

Every changed behavior or logic path needs appropriate behavior-focused test
coverage. Add a regression test for every bug fix. Test relevant positive,
negative, boundary, and failure cases; include authorization and cross-tenant
denials for security-sensitive behavior. Select the correct layer: unit,
component, API/integration, migration, browser E2E, or package/build.

Use the `safe-testing` skill before database-backed, integration, or E2E test
runs. Never use active development, staging, or production data or services.
Investigate unexpected skips; do not hide a failure or add a skip to force a
green result. Report exact pass/fail/skip counts and any test scope that was not
run.

## Documentation after every change

After implementation, use the `documentation-impact` skill. Review user help,
admin/operator guidance, API/schema docs, configuration, test instructions,
release notes, and security documentation as applicable. Update the relevant
docs in the same change whenever behavior or operating steps changed. If no
docs need an edit, say why in the final evidence. Use structured headings and
tables for facts that benefit from comparison; verify examples, commands, and
links against the current repository.

## Verify and report

Use `quality-gates` before calling work ready or performing an explicitly
requested push. For desktop and release work, also use `desktop-release`.
Review the full diff, check for unrelated edits and secret exposure, and verify
the working tree before reporting.

Report what changed, why, exact affected paths, tests and documentation added,
commands and outcomes, actual CI status when available, skips, limitations, and
remaining risks. Never claim “perfect,” “fully tested,” or “production-ready”
without evidence for that exact claim.
