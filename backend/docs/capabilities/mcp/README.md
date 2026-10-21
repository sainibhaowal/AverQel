# MCP documentation

The MCP implementation contract is maintained in
[`../06-mcp-connections.md`](../06-mcp-connections.md). The companion status
record summarizes repository behavior and external deployment gates; check
the [current release index](../../release/03-current-worktree-change-index.md)
for the latest recorded migration and environment evidence.

- [Current MCP release status](01-current-release-status.md)
- [MCP architecture and implementation map](02-mcp-architecture-and-implementation-map.md)
- [Composio hosted app catalog and operations](03-composio-hosted-mcp.md)

The current Marketplace uses Composio's live app catalog with a project key
owned by each AverQel account and tenant/user-scoped hosted app sessions. The
dated architecture map describes the former bundled catalog and OAuth-token
flow; use the current contract and Composio guide for present behavior. The
runtime does not enable arbitrary endpoints, local process servers, or global
credentials, and side-effecting calls remain subject to approval and policy
controls.
