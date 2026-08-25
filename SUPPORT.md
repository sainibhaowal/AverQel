# Support

Support is community-oriented and best-effort. Include the AverQel version,
deployment type, operating system, and a minimal reproduction so the issue can
be investigated efficiently.

## Start here

1. Check the [README](README.md) and the relevant guide in [`Docs/`](Docs/).
2. Check the [changelog](CHANGELOG.md) for known behavior changes.
3. For a deployment issue, follow the [VPS production runbook](Docs/VPS-Production-Runbook.md)
   and capture the failing service, release version, and safe logs.
4. For a reproducible product bug, search the [issue tracker](https://github.com/sainibhaowal/AverQel/issues),
   then [open an issue](https://github.com/sainibhaowal/AverQel/issues/new) with
   steps, expected behavior, actual behavior, environment, and redacted
   diagnostics.

## What to include

- AverQel release or commit and whether the issue is local, desktop, or VPS;
- operating system, browser or Electron version, and relevant provider;
- the smallest reproducible steps and the first failing log message;
- whether the issue affects one tenant/user or all tenants/users;
- what changed immediately before the failure.

Feature requests should explain the user problem, proposed behavior, and any
security or tenant-isolation implications. Do not use public issues for
production incidents containing sensitive data; contact the maintainers
privately instead.

## Contact

Use the [issue tracker](https://github.com/sainibhaowal/AverQel/issues) for
public, reproducible support. For account, deployment, or other details that
must remain private, contact `support@averqel.com`. Suspected vulnerabilities
must use the private process in [`SECURITY.md`](SECURITY.md), not ordinary
support.

## Do not post publicly

Never include passwords, API keys, OAuth codes, access tokens, SSH private
keys, `.env` contents, customer documents, or unredacted production logs.
Security vulnerabilities belong in a private GitHub Security Advisory; see
[`SECURITY.md`](SECURITY.md).

## Useful diagnostics

```bash
git status --short
docker compose --env-file .env.vps -f docker-compose.prod.yml ps
docker compose --env-file .env.vps -f docker-compose.prod.yml logs --tail=200 api frontend
```

Always redact hostnames, credentials, tokens, personal data, and document
content before sharing output.

For a suspected vulnerability, stop public discussion and follow
[`SECURITY.md`](SECURITY.md). For conduct concerns, follow
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
