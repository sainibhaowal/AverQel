import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ConnectorsMcpDocsPage() {
  return (
    <DocsShell
      title="Connectors & MCP"
      intro="AverQel connects official vendor MCP servers through a tenant-scoped Python MCP runtime with generic OAuth, encrypted credentials, dynamic catalogs, approvals, and durable lifecycle events."
    >
      <DocsCards
        items={[
          {
            title: "Connector Sources",
            body: "The MCP marketplace syncs registry metadata and lets each workspace connect approved remote MCP applications.",
          },
          {
            title: "OAuth + Secret Safety",
            body: "MCP OAuth metadata is discovered from the vendor, callbacks use signed expiring state, and access/refresh tokens are encrypted per tenant and server.",
          },
          {
            title: "Connector Documents",
            body: "Connector outputs become durable connector documents or sync artifacts that the rest of the product can query and reference later.",
          },
          {
            title: "Native MCP Runtime",
            body: "Installed servers support Streamable HTTP and SSE fallback, with reconnect workers, list-change notifications, prompts/resources/templates, and an Inspector view.",
          },
        ]}
      />

      <DocsSection title="What exists now">
        <p>
          Today&apos;s connector system is already real and useful. Users can connect sources,
          configure sync rules, and let the agent use connector context during missions. Connector
          status, sync state, and recent activity are visible in the dashboard and orchestration
          surfaces.
        </p>
        <p>
          Several integrations use first-class OAuth flows so users do not have to paste raw tokens
          for every service. Connector setup also supports configuration forms, optional filters,
          and connector-scoped document ingestion.
        </p>
      </DocsSection>

      <DocsSection title="How MCP fits in">
        <p>The native MCP server path is the primary integration model:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>discover tools, prompts, resources, and templates dynamically from each server</li>
          <li>map MCP tool risk into AverQel&apos;s permission tiers</li>
          <li>persist connection, catalog, notification, and tool-call events for replay and inspection</li>
          <li>keep OAuth, tenant ownership, approvals, and audit safety under AverQel&apos;s control plane</li>
        </ul>
      </DocsSection>

      <DocsSection title="What users and operators should understand">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Connectors are not just API keys; they are durable runtime records with status and sync
            state.
          </li>
          <li>
            Connector actions still pass through approval and safety policy when the requested tool
            is risky.
          </li>
          <li>
            Connector outputs can become searchable source material, mission input, or follow-up
            tasks.
          </li>
          <li>
            MCP is a standardization path that improves maintainability; it does not remove
            AverQel&apos;s ownership of auth, scoping, or safety.
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="Why this matters for future development">
        <p>
          This is one of the most important maintainability areas in the system. A strong MCP-aware
          connector layer makes it easier to add new tools and services without rewriting the whole
          agent surface every time.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
