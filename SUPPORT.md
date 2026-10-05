# Support

For account or product questions, use **Support Centre** in the signed-in
AverQel workspace when it is available. Tickets support a private reply thread,
status tracking, and validated attachments. Response targets are operational
targets, not a guaranteed response time. Self-hosted operators can also use
the project issue tracker for reproducible bugs and deployment problems.

## Start here

1. Check the [in-app product documentation](https://averqel.com/documentation) and relevant
   release notes. Repository users can also browse the
   [backend documentation index](backend/docs/README.md).
2. Check the [changelog](CHANGELOG.md) for known behavior changes.
3. For a deployment issue, check the [VPS deployment workflow](.github/workflows/deploy-vps.yml),
   [API reliability guide](backend/docs/platform/01-api-reliability.md), and
   [backup and recovery guide](backend/docs/storage/01-storage-backup-and-disaster-recovery.md).
   Capture the failing service, release version, and redacted logs.
4. For a reproducible open-source bug, search the
   [issue tracker](https://github.com/sainibhaowal/AverQel/issues), then
   [open an issue](https://github.com/sainibhaowal/AverQel/issues/new) with
   steps, expected behavior, actual behavior, environment, and redacted
   diagnostics. Do not post private account or customer details there.

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

Use the in-app Support Centre for account-specific conversations. Use the
[issue tracker](https://github.com/sainibhaowal/AverQel/issues) for public,
reproducible open-source issues. For other private details, contact
`support@averqel.com`. Suspected vulnerabilities must use the private process
in [`SECURITY.md`](SECURITY.md), not ordinary support.

## Do not post publicly

Never include passwords, API keys, OAuth codes, access tokens, SSH private
keys, `.env` contents, customer documents, or unredacted production logs.
Security vulnerabilities belong in a private GitHub Security Advisory; see
[`SECURITY.md`](SECURITY.md).

## Useful diagnostics

```bash
git status --short
cd backend
docker compose --env-file .env.vps -f docker-compose.prod.yml ps
docker compose --env-file .env.vps -f docker-compose.prod.yml logs --tail=200 api frontend
```

Always redact hostnames, credentials, tokens, personal data, and document
content before sharing output.

For a suspected vulnerability, stop public discussion and follow
[`SECURITY.md`](SECURITY.md). For conduct concerns, follow
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
