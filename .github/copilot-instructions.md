@../AGENTS.md

Use `AGENTS.md` as the canonical project policy and read
`AGENT_ENGINEERING_STANDARD.md` before implementation. Invoke `production-change`
for every implementation and `documentation-impact` afterward. Present the
plan before coding, then proceed without waiting for routine approval. Add
behavior tests for changed logic and update relevant documentation in the same
change. Never test against active services; use
`./backend/scripts/test-isolated.sh` for database-backed backend tests. Before
a requested push, install and use the repository's isolated pre-push gate with
`bash .github/scripts/install-pre-push-hook.sh`. It runs the complete pre-commit
configuration and Actionlint for every workflow against each pushed commit
without allowing formatters to alter the active checkout. CI repeats workflow
lint for pull requests. Run applicable quality gates and inspect the diff.
Report exact results, including failures and skips. The manual desktop release
packages Linux `.deb` and Windows `.exe`; VPS deployment is a separate manual
workflow.
