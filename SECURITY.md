# Security policy

AverQel treats authentication, tenant isolation, document access, connector
credentials, and release integrity as security boundaries.

## Supported releases

| Version line | Security support |
| --- | --- |
| Protected `main` | Active fixes and coordinated security updates |
| Latest published AverQel release | Active fixes and security updates |
| Older releases | Upgrade first; no backports are promised |

Security support depends on the deployment using the documented production
configuration. Custom images, modified source, and unsupported infrastructure
may change the impact or remediation path.

## Report a vulnerability privately

Please use the repository's [private security advisory form](https://github.com/sainibhaowal/AverQel/security/advisories/new).
Do not create a public issue, commit, pull request, or chat message containing
exploitable details. If the advisory form is unavailable, contact the project
maintainers privately through GitHub before sharing technical details.

Include:

- affected version or commit;
- a concise impact description;
- reproducible steps or a minimal proof of concept;
- affected endpoints, roles, tenants, or deployment conditions;
- a suggested mitigation, if known.

Please redact credentials, personal data, customer documents, OAuth tokens,
SSH keys, and production host details. We will acknowledge a useful report,
verify the impact, coordinate a fix, and publish release notes when disclosure
is safe. Please allow reasonable time for triage and remediation before public
disclosure; coordinated disclosure dates are agreed with the reporter.

## Scope

Please report issues involving authentication, authorization, tenant
isolation, document access, file or prompt processing, SSRF, OAuth and MCP
connectors, secret handling, release integrity, or a vulnerability that is
reachable through a documented AverQel deployment.

Reports about an upstream dependency are still useful when AverQel exposes the
affected path. We may coordinate the fix with that upstream project.

When testing in good faith, avoid accessing data that is not yours, deleting
or modifying data, degrading availability, persistence, or social engineering.
Stop testing and report immediately if you encounter real user data.

## Operational security controls

- Secrets belong in GitHub Actions secrets or VPS-owned environment files, not
  source control.
- Production releases are built from an exact protected `main` commit.
- Docker images are smoke-tested, vulnerability-scanned, SBOM-attested, and
  keylessly signed before VPS deployment.
- Desktop assets are checksummed and verified before public publication.
- OAuth tokens are encrypted, user-scoped, and excluded from browser and log
  payloads.

See [`.github/RELEASE_SECURITY.md`](.github/RELEASE_SECURITY.md) for release
credential and signing controls.
