# AverQel documentation

This directory contains the technical, product, and operational documentation
for AverQel. The root [README](../README.md) is the public orientation; this
index points to the deeper guides.

## Operate and deploy

- [VPS production runbook](VPS-Production-Runbook.md)
- [VPS commands](VPS-Command.md)
- [Docker commands](DockerCMD.md)
- [Release security controls](../.github/RELEASE_SECURITY.md)
- [Git workflow](Git_Guide.md)

## Product and architecture

- [MCP plan and release status](mcp-plan.md)
- [DeepSpace architecture](brand/README.md)
- [Agent timeline production plan](Agent-Timeline-Production-Plan.md)
- [Current implementation notes](current.md)
- [Tier plans](TierPlans-3.md)

## Feature planning

The documents in [`New Features/`](New%20Features/) are delivery plans and
acceptance criteria. A plan is not a product promise until the implementation,
tests, migration, and release notes are complete.

## Documentation standard

Every production change should update the nearest relevant guide when it
changes setup, security, API behavior, operational recovery, or user-visible
workflow. Documentation must distinguish clearly between implemented behavior,
planned work, and operator-only configuration.
