import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ConnectorsMcpDocsPage() {
  return (
    <DocsShell
      title="Connectors & MCP"
      intro="AverQel provides a curated marketplace for approved remote MCP providers. Users authorize their own accounts, while AverQel keeps tenant isolation, encrypted credentials, tool permissions, approvals, and DeepSpace routing under its control."
    >
      <DocsCards
        items={[
          {
            title: "Marketplace",
            body: "Browse approved providers with publisher, logo, transport, authentication, reviewed tools, scopes, risk labels, documentation, and health metadata.",
          },
          {
            title: "User OAuth",
            body: "Google or GitHub handles the login and consent screen. AverQel receives the authorization result, never the user's password, and stores token material encrypted.",
          },
          {
            title: "Policy Control",
            body: "Each connection has read-only, risk, per-tool, conversation, and DeepSpace controls. Write, delete, and external-message actions can require approval.",
          },
          {
            title: "Remote Runtime",
            body: "This release connects to remote Streamable HTTP or SSE MCP servers. Local stdio, SSH, and arbitrary local servers are not supported by the marketplace release.",
          },
        ]}
      />

      <DocsSection title="The user flow">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Open Dashboard → MCP Marketplace and choose an approved provider.</li>
          <li>
            Review the publisher, trust status, endpoint, transport, tools, risks, and requested
            OAuth scopes.
          </li>
          <li>
            Select Connect. The browser goes to the provider&apos;s official authorization page.
          </li>
          <li>Sign in and approve the requested scopes at Google, GitHub, or another provider.</li>
          <li>
            AverQel returns to the connection inspector, captures only safe account identity,
            refreshes the catalog, and shows the available tools.
          </li>
          <li>
            Configure the connection policy. A connection or scope remains unavailable when it has
            not been explicitly enabled.
          </li>
          <li>
            Use the protected MCP surface for actions such as searching Gmail or reading a GitHub
            repository. The runtime checks identity, connection, catalog freshness, tool policy, and
            approval requirements before calling the remote server.
          </li>
        </ol>
      </DocsSection>

      <DocsSection title="Official and community providers">
        <p>
          An <strong>Official</strong> provider is operated by the vendor represented in the catalog
          and has been reviewed by AverQel. A <strong>Community</strong> provider is a reviewed
          third-party server that is not operated by that official vendor or by AverQel. Community
          providers never receive the Official badge automatically and always show a trust warning
          before connection.
        </p>
        <p>
          Only entries with AverQel&apos;s approved trust status can be connected. The catalog is
          metadata, not a guarantee that a vendor will remain available or that its tools will never
          change; the runtime still performs ownership, approval, freshness, and catalog checks.
        </p>
      </DocsSection>

      <DocsSection title="Badges and provider metadata">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Official:</strong> reviewed vendor-operated provider.
          </li>
          <li>
            <strong>Community:</strong> reviewed third-party provider with a visible warning.
          </li>
          <li>
            <strong>New:</strong> recently published catalog entry within its review window.
          </li>
          <li>
            <strong>Trending:</strong> catalog popularity signal within its review window.
          </li>
          <li>
            <strong>Interactive:</strong> provider reviewed as supporting interactive workflows.
          </li>
          <li>
            New, Trending, and Interactive are catalog attributes with review and expiry metadata;
            they are not hard-coded frontend labels.
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="OAuth, token storage, and revocation">
        <p>
          AverQel uses provider-specific OAuth profiles, PKCE, signed state, a stable callback, and
          scope verification. The user authenticates with the provider. AverQel does not receive or
          store the provider password.
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>OAuth transactions, including PKCE state, are encrypted and single-use.</li>
          <li>Access and refresh tokens are encrypted with tenant-bound associated data.</li>
          <li>
            Safe account identity and verified scope names are stored separately from encrypted
            credentials.
          </li>
          <li>
            Disconnect removes the local token record and requests provider revocation where
            supported.
          </li>
          <li>
            Refresh updates encrypted credentials and verified scope metadata without exposing
            secrets to the frontend.
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="Tool permissions and precedence">
        <p>DeepSpace applies the most restrictive applicable rule. The effective order is:</p>
        <ol className="list-decimal space-y-2 pl-6">
          <li>
            Connection ownership, provider approval, enabled status, authentication, and catalog
            freshness.
          </li>
          <li>Connected-account availability across DeepSpace conversations.</li>
          <li>
            Explicit <strong>Blocked</strong> tool mode.
          </li>
          <li>Allowlist and denylist checks.</li>
          <li>Read-only mode and the connection risk ceiling.</li>
          <li>
            A master tool permission applies to every tool by default. Individual tool settings
            can override it after the master setting is saved.
          </li>
          <li>
            Per-tool mode: <strong>Always allow</strong>, <strong>Needs approval</strong>, or{" "}
            <strong>Blocked</strong>.
          </li>
          <li>Platform and tenant safety rules, which Always allow can never bypass.</li>
        </ol>
        <p>
          Always allow permits a tool only after all higher-level checks pass. Needs approval pauses
          before the remote side effect. Blocked tools are not offered to DeepSpace and cannot be
          executed through the MCP runtime.
        </p>
        <p>
          The MCP inspector provides one master permission selector for fast account-wide changes
          and one master risk ceiling for the maximum allowed risk. Risk safeguards are separate
          safety limits, not a duplicate per-tool permission system.
        </p>
        <p>
          A connected server is automatically available to the owning user&apos;s DeepSpace
          conversations. Ownership, connection status, catalog freshness, tool permissions, risk
          limits, and approval rules are still checked before every remote call.
        </p>
      </DocsSection>

      <DocsSection title="Remote transport and current limits">
        <p>
          <strong>Remote HTTP</strong> means AverQel connects over a vendor-hosted HTTPS Streamable
          HTTP MCP endpoint. <strong>Remote SSE</strong> means the server uses the Server-Sent
          Events transport. The endpoint is validated by AverQel before use and the runtime
          maintains catalog freshness and safe reconnect behavior.
        </p>
        <p>
          Local stdio processes, SSH-launched servers, arbitrary local servers, and user-supplied
          executable MCP packages are not supported in this marketplace release. This keeps the VPS
          from executing unreviewed vendor code and keeps the product focused on remote providers.
        </p>
      </DocsSection>

      <DocsSection title="Catalog and health limitations">
        <p>
          Marketplace tool lists are AverQel-reviewed catalog metadata. After authentication, the
          connection can refresh its live tool catalog, but a remote provider can change tools or
          availability. AverQel rejects stale catalogs and tools removed from the current catalog.
        </p>
        <p>
          Health and last-verified indicators are safe status metadata, not a promise of uptime or
          provider correctness. The browser never performs endpoint health probes or arbitrary
          metadata discovery. Community logo URLs are validated and fall back to a local identity
          when unsafe.
        </p>
      </DocsSection>

      <DocsSection title="Why AverQel does not clone vendor MCP servers">
        <p>
          AverQel is the secure MCP host/client and policy layer, not a copy of every vendor server.
          Cloning a vendor repository would create credential, update, licensing, maintenance, and
          supply-chain responsibilities that belong to the vendor. AverQel instead stores curated
          public metadata, connects to the official remote endpoint, and enforces its own tenant,
          user, token, tool, approval, and audit boundaries.
        </p>
      </DocsSection>

      <DocsSection title="Marketplace and connection APIs">
        <p>
          The frontend uses the typed MCP API boundary for marketplace entries, provider details,
          connections, policies, tools, scoped conversation/DeepSpace controls, refresh, OAuth, and
          inspection. Responses are explicit DTOs and never include raw server configuration,
          tokens, client secrets, OAuth transaction data, or raw MCP event payloads.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
