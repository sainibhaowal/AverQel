import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ProvidersPage() {
  return (
    <DocsShell
      title="Providers"
      intro="AverQel has two related provider concepts: model providers for AI runtime routing and MCP providers for user-authorized remote tools such as Gmail, Notion, Slack, and GitHub."
    >
      <DocsCards
        items={[
          {
            title: "Model Providers",
            body: "OpenRouter, OpenAI-compatible endpoints, Anthropic, Google, Ollama, LM Studio, embeddings, rerankers, and search runtimes power AI generation and retrieval.",
          },
          {
            title: "Self-hosted SearXNG",
            body: "DeepSpace can use a configured SearXNG JSON endpoint for server-side web search without a third-party search API key.",
          },
          {
            title: "MCP Providers",
            body: "Google Gmail, Drive, Calendar, Chat, People, GitHub, Notion, Slack, and future approved vendors remain available through the separate MCP surface.",
          },
          {
            title: "Provider-Owned Login",
            body: "MCP users authenticate on the provider authorization page. AverQel stores encrypted tokens and safe account identity, not provider passwords.",
          },
          {
            title: "Explicit Ownership",
            body: "Provider credentials and MCP connections are scoped to the current tenant and user. They are never treated as a shared global account.",
          },
        ]}
      />

      <DocsSection title="Model providers versus MCP providers">
        <p>
          Model providers answer questions or create embeddings. MCP providers remain a separate
          protected integration surface for external product actions. A Google model provider and a
          Google Gmail MCP connection are separate integrations with separate credentials, policies,
          and ownership.
        </p>
        <p>
          Do not put MCP OAuth credentials into the normal model-provider configuration. MCP uses
          dedicated provider profiles and dedicated per-user connection records so existing Google,
          GitHub, Drive, and other integrations remain compatible.
        </p>
      </DocsSection>

      <DocsSection title="Self-hosted SearXNG web search">
        <p>
          Add <strong>SearXNG (Self-hosted)</strong> from the Web provider tab and enter the URL
          reachable by the AverQel API, for example <code>http://searxng:8080</code> when both
          services share a private Docker network. SearXNG must have its JSON search format enabled.
          No API key is required.
        </p>
        <p>
          DeepSpace invokes the bounded <code>web_search</code> tool only when the selected model
          requests it. Results are fetched server-side, filtered by the configured domain policy,
          and returned with titles, URLs, snippets, source engines, and available publication dates.
          The final Markdown response receives a Sources section with links.
        </p>
        <p>
          Requests use bounded timeouts, Redis-backed per-user rate limits, redirect blocking, URL
          validation, and endpoint SSRF checks. The model never receives shell or cURL access; it
          receives only the typed web-search tool and sanitized result data. MCP remains a separate
          integration surface.
        </p>
      </DocsSection>

      <DocsSection title="Google and GitHub MCP connections">
        <ol className="list-decimal space-y-2 pl-6">
          <li>
            AverQel publishes a curated marketplace entry with the official remote endpoint,
            reviewed tools, requested scopes, and risk policy.
          </li>
          <li>
            An administrator configures AverQel&apos;s Google or GitHub OAuth client ID, client
            secret, and exact callback URI on the VPS.
          </li>
          <li>The user selects Connect and is redirected to Google or GitHub.</li>
          <li>The provider returns an authorization result to AverQel&apos;s signed callback.</li>
          <li>
            AverQel verifies scopes and account identity, encrypts the token material, refreshes the
            safe catalog, and opens the connection inspector.
          </li>
          <li>
            MCP actions remain available only through the current user&apos;s approved connection
            after policy and scope checks pass.
          </li>
        </ol>
        <p>
          If an OAuth client is not configured, the marketplace entry remains visible but shows
          Setup pending. This is an operator configuration state, not a request for users to give
          AverQel their Google or GitHub password.
        </p>
      </DocsSection>

      <DocsSection title="Notion and Slack MCP connections">
        <p>
          Notion uses its official remote Streamable HTTP MCP endpoint with OAuth discovery and
          dynamic client registration. AverQel uses PKCE and stores the resulting credentials only
          in the encrypted per-user MCP token record.
        </p>
        <p>
          Slack uses its official remote MCP endpoint with confidential OAuth. An administrator must
          configure an approved Slack app&apos;s <code>AKS_MCP_SLACK_OAUTH_CLIENT_ID</code> and{" "}
          <code>AKS_MCP_SLACK_OAUTH_CLIENT_SECRET</code> values on the VPS, together with the same
          HTTPS callback used by the MCP OAuth service. The catalog requests the reviewed Slack read
          and write user scopes. Read actions are read-only; message sending, channel changes,
          reactions, and canvas changes require explicit AverQel approval.
        </p>
        <p>
          After the required provider setup is available, both entries use the same flow: Connect,
          provider consent, signed callback, scope verification, encrypted token storage, live tool
          discovery, policy checks, and DeepSpace routing.
        </p>
      </DocsSection>

      <DocsSection title="MCP marketplace trust metadata">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Official:</strong> reviewed provider operated by the represented vendor.
          </li>
          <li>
            <strong>Community:</strong> reviewed third-party provider; it is never automatically
            official.
          </li>
          <li>
            <strong>New:</strong> recently added provider within its catalog review period.
          </li>
          <li>
            <strong>Trending:</strong> reviewed popularity signal with explicit review metadata.
          </li>
          <li>
            <strong>Interactive:</strong> reviewed support for interactive workflows.
          </li>
        </ul>
        <p>
          These are catalog attributes, not security permissions. Approval status controls whether a
          provider can be connected; badges help users understand provenance and product status.
        </p>
      </DocsSection>

      <DocsSection title="Remote MCP transport labels">
        <p>
          Remote HTTP means a vendor-hosted HTTPS Streamable HTTP MCP endpoint. Remote SSE means a
          vendor-hosted HTTPS Server-Sent Events MCP endpoint. AverQel validates remote endpoints
          and does not let the browser probe them directly.
        </p>
        <p>
          Stdio, SSH, and local process transports are not supported in this release. AverQel does
          not clone or execute arbitrary vendor MCP repositories on the VPS. This reduces
          supply-chain and host-execution risk while the product focuses on approved remote
          services.
        </p>
      </DocsSection>

      <DocsSection title="Provider health and catalog preview">
        <p>
          Marketplace previews are reviewed metadata. Once connected, AverQel can refresh the live
          tool catalog and records a safe catalog revision and health status. Health is an
          operational signal, not an uptime guarantee, and remote providers can change tools or
          permissions.
        </p>
        <p>
          The runtime rejects stale catalogs, disabled providers, revoked connections, removed
          tools, and policy violations. The frontend receives only typed safe DTOs; provider tokens,
          client secrets, raw OAuth metadata, and raw MCP event payloads remain server-side.
        </p>
      </DocsSection>

      <DocsSection title="Why AverQel does not clone MCP repositories">
        <p>
          The vendor owns its MCP implementation, endpoint availability, OAuth application, and tool
          behavior. AverQel owns the marketplace review, tenant/user connection, encryption, policy,
          approval, runtime routing, and safe inspection. Keeping those responsibilities separate
          makes provider updates safer and prevents unreviewed code from running inside AverQel.
        </p>
      </DocsSection>

      <DocsSection title="Existing AI provider support">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Chat runtimes include OpenRouter, OpenAI-compatible providers, Anthropic, Google,
            Ollama, LM Studio, and OpenCode Zen.
          </li>
          <li>
            Embedding runtimes include local deterministic paths, sentence-transformers, OpenRouter,
            Ollama, LM Studio, and OpenAI-compatible providers.
          </li>
          <li>Reranking and web search use their own provider routing and secret boundaries.</li>
        </ul>
        <p>
          These model-provider flows remain separate from the remote MCP marketplace and are not
          replaced by it.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
