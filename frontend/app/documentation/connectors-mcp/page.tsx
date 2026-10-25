import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ConnectorsMcpDocsPage() {
  return (
    <DocsShell
      title="Connectors & MCP"
      intro="Browse Composio's live app catalog, connect your own app accounts, and use their actions through DeepSpace. Each AverQel account supplies and owns its Composio project key and connected sessions."
    >
      <DocsCards
        items={[
          {
            title: "Your Composio key",
            body: "Under Dashboard → Providers → MCP, choose + to browse provider families, then select Composio to open its setup panel. Add your own Composio project API key there; AverQel encrypts and scopes it to your account and never returns it to the browser.",
          },
          {
            title: "Live app catalog",
            body: "MCP Marketplace loads Composio's current apps and tools on request. Search and pagination let you explore the catalog without a fixed app-count promise.",
          },
          {
            title: "Your app accounts",
            body: "Authorize each app for your own account. Other AverQel users cannot use your Composio key or connection sessions.",
          },
          {
            title: "DeepSpace approvals",
            body: "Connected tools use the existing MCP broker and policy checks. Writes, deletions, and external messages require approval before execution.",
          },
        ]}
      />

      <DocsSection title="Connect an app">
        <ol className="list-decimal space-y-2 pl-6">
          <li>
            Open <strong>Dashboard → Providers → MCP</strong>, choose <strong>+</strong> to browse
            provider families, then select <strong>Composio</strong>. Enter your project API key in
            its setup panel and choose <strong>Validate and save</strong>.
          </li>
          <li>
            Open <strong>Dashboard → MCP Marketplace</strong>. Search or browse Composio&apos;s live
            app catalog and choose <strong>View details</strong> to inspect the description, catalog
            metadata, available app links, authentication requirements, and tools.
          </li>
          <li>
            Choose <strong>Connect</strong> for an app that requires sign-in. Review the requested
            access and complete the app&apos;s authorization flow. Apps that Composio marks as
            requiring no account authorization can be added directly.
          </li>
          <li>
            After authorization, the app appears under <strong>Installed</strong>. DeepSpace can
            discover and call its available tools under your connection policy.
          </li>
        </ol>
        <p>
          The catalog is supplied by Composio and changes over time. App availability, tool lists,
          and counts depend on Composio and your project. App cards use Composio&apos;s maintained
          toolkit logo CDN for their icons. AverQel no longer lists its eight bundled Google,
          GitHub, Notion, and Slack cards as Marketplace choices. Existing installed connections are
          retained.
        </p>
        <p>
          App cards resolve toolkit icons from Composio&apos;s maintained logo CDN. The details view
          shows only fields and HTTPS links supplied by that catalog; publisher/author information
          or a separate per-app MCP endpoint may not be published. Tool details are loaded from
          Composio and paged when an app has more actions than fit in the first response.
        </p>
      </DocsSection>

      <DocsSection title="OAuth setup">
        <p>
          OAuth-based apps need the AverQel deployment&apos;s public HTTPS origin. After sign-in,
          Composio returns the browser to AverQel. The server checks the connected-account ID
          against the pending request for your account and confirms the app and connection with your
          own Composio key. You do not need to register a callback verifier in your Composio
          project.
        </p>
        <p>
          If the server&apos;s public origin is missing, OAuth connections remain unavailable until
          the AverQel operator configures it. Local development can use an HTTP localhost origin.
          No-auth apps can still be added. Composio and the connected app may show additional
          consent or project-permission steps; availability varies by app.
        </p>
      </DocsSection>

      <DocsSection title="Account isolation and data handling">
        <p>
          AverQel encrypts your Composio project key and binds it to your tenant and account. The
          backend uses that key to make Composio requests, so the key is not end-to-end encrypted
          from the running AverQel server. The key is not shared with other AverQel users. Each
          connected app session is also scoped to the account that started it.
        </p>
        <p>
          Composio handles app authorization and hosted tool execution. The connected app provider
          processes the actions and data you send to it. AverQel does not receive your app password
          or store your app&apos;s OAuth token in the Composio key record. Review Composio&apos;s
          and the app provider&apos;s terms before connecting sensitive accounts.
        </p>
        <p>
          Removing your Composio key disables your Composio sessions in AverQel. It does not
          necessarily revoke authorization held by Composio or the connected app; revoke access
          there as well when you want to remove the external grant.
        </p>
      </DocsSection>

      <DocsSection title="Tool permissions and approvals">
        <p>
          DeepSpace checks the connection owner, enabled status, catalog, and saved policy before
          calling a Composio tool. Read actions may run under your policy. Writes, deletions, and
          external messages pause for an approval card before the remote action. Setting a tool to
          Always allow cannot bypass that side-effect approval requirement.
        </p>
        <p>
          Review each approval card&apos;s tool name and inputs before accepting it. Reject an
          action you did not request, and disconnect the app if its access is no longer needed.
        </p>
        <p>
          Tool searches use the latest catalog AverQel has received, and schema lookup refreshes the
          selected connection&apos;s saved catalog. AverQel requests aged catalog updates in the
          background, so a provider&apos;s newest changes may take time to appear if that provider
          is slow or unavailable. Before an action runs, AverQel checks the current saved tool
          definition and policy. A removed tool is not run and must be searched again. If the
          definition changes while an approval is pending, that approval expires and the action does
          not run; ask DeepSpace to prepare it again so you can review the updated request.
        </p>
      </DocsSection>

      <DocsSection title="Limits and troubleshooting">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>No key:</strong> add your own key under Providers → MCP. No platform-admin key
            setup is required.
          </li>
          <li>
            <strong>Key validation fails:</strong> confirm it belongs to your Composio project and
            that AverQel can reach Composio over HTTPS.
          </li>
          <li>
            <strong>OAuth is unavailable:</strong> check the public HTTPS callback URL, the
            deployment&apos;s <code>AVERQEL_PUBLIC_ORIGIN</code> setting. No project-level callback
            registration is required.
          </li>
          <li>
            <strong>No tools after connecting:</strong> check the Installed connection status and
            refresh its catalog. The app or your Composio project may not expose every action.
          </li>
          <li>
            <strong>Catalog or tool details do not load:</strong> AverQel stops waiting after 20
            seconds and offers a retry. Search results load in pages of 24 apps; choose{" "}
            <strong>Load more apps</strong> to continue browsing. A slow catalog request does not
            block the rest of the page.
          </li>
          <li>
            The live catalog and external authorization cannot be verified without a valid Composio
            project key and an app account with the required permissions.
          </li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
