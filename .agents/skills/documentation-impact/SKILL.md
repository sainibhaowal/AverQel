---
name: documentation-impact
description: Review and update AverQel user, API, backend, frontend, testing, security, operator, and release documentation for every code or behavior change. Use after implementation and when a task changes how a feature works.
---

# Documentation-impact review

Run this review after every implementation, including bug fixes and small
patches. Read `AGENT_ENGINEERING_STANDARD.md` and identify who needs to
understand the change: end users, workspace administrators, API integrators,
operators, or developers.

Review the relevant sources:

| Changed area | Documentation to inspect |
| --- | --- |
| User-visible frontend or desktop workflow | `frontend/app/documentation/`, user-facing `README.md`, relevant empty/error states and workflow guidance |
| API, auth, or integration | API schemas/OpenAPI, permission and tenant-scope docs, request/response examples, error and compatibility notes |
| Backend data or persistence | Schema and data-flow docs, migration/upgrade, retention, deletion, backup, and recovery guidance |
| Configuration or local setup | Environment examples, install/build commands, defaults, prerequisites, and troubleshooting |
| Tests and automation | `backend/docs/platform/03-testing.md`, isolation guidance, CI/pre-commit commands, test fixtures and known limits |
| Electron packaging and releases | `applications/desktop/README.md`, release workflow documentation, supported artifact formats and source boundaries |
| Security-sensitive change | Threat boundary, auth/tenant isolation, encryption, secret handling, audit behavior, and operator response |

Update the relevant docs in the same change whenever user behavior, APIs,
configuration, security, data lifecycle, tests, release, or operations change.
Add a new document when no current guide has the right audience or scope. If no
documentation change is warranted, record the reason in the final report; do
not silently omit the review.

Use a clear title and audience-appropriate structure. Include purpose, required
permissions or prerequisites, steps, expected results, limitations, failure
handling, and related links where applicable. Use tables for roles, API fields,
settings, states, compatibility, and comparisons when they improve scanning.
Use diagrams only when they clarify a real flow. Keep examples and commands
accurate, validate repository-relative links, and do not copy historical test
results as current evidence.
