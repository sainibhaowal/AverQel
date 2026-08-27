# AverQel documentation

This directory contains the technical, product, and operational documentation
for AverQel. The root [README](../README.md) is the public orientation; this
index points to the deeper guides.

## Public operations and contribution guides

- [Release security controls](../.github/RELEASE_SECURITY.md)
- [Contributor guide](../CONTRIBUTING.md)
- [Desktop development guide](../applications/desktop/README.md)
- [Frontend development guide](../frontend/README.md)
- [New feature plans](New%20Features/README.md)

Host-specific VPS runbooks, Docker commands, credentials, and deployment
addresses are intentionally excluded from the public repository. Keep those
operator materials in the deployment workspace and never commit environment
files or secrets.

## Product and architecture

The public product and architecture overview is maintained in the root
[README](../README.md) and the implementation documentation in the frontend
and backend packages. Local design plans are not product promises until the
implementation, tests, migrations, and release notes are complete.

## Feature planning

The documents in [`New Features/`](New%20Features/) are delivery plans and
acceptance criteria. A plan is not a product promise until the implementation,
tests, migration, and release notes are complete.

## Documentation standard

Every production change should update the nearest relevant guide when it
changes setup, security, API behavior, operational recovery, or user-visible
workflow. Documentation must distinguish clearly between implemented behavior,
planned work, and operator-only configuration.
