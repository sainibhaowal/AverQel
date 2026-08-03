import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function PrivacySecurityPage() {
  return (
    <DocsShell
      title="Privacy & Security"
      intro="How AverQel separates tenants and users, protects provider credentials, limits MCP visibility, and controls agent actions."
    >
      <DocsCards
        items={[
          { title: "Tenant + User Isolation", body: "MCP servers, OAuth tokens, policies, account identities, and events are queried with both tenant and user ownership checks." },
          { title: "Encrypted Credentials", body: "OAuth access and refresh tokens are encrypted at rest. The browser receives safe account labels and scope names, never credential material." },
          { title: "Connected-account scope", body: "Connected MCP accounts are available across the owning user’s DeepSpace conversations; ownership, catalog freshness, tool policy, risk limits, and approvals remain enforced." },
          { title: "Metadata-Only Inspection", body: "The inspector exposes safe status and redacted event summaries, not raw MCP responses, private content, headers, tokens, or server configuration." },
        ]}
      />

      <DocsSection title="MCP account and tenant isolation">
        <p>
          Every native MCP connection belongs to one tenant and one user. OAuth token lookup uses
          the connection&apos;s tenant, user, and server identity together. DeepSpace cannot select a
          token belonging to another user or use a tenant-wide Google or GitHub token.
        </p>
        <p>
          Conversation and DeepSpace endpoints verify that the referenced object belongs to the
          current tenant and that the current user may operate it. These checks are repeated in the
          runtime immediately before remote execution; frontend context is never treated as proof
          of authorization.
        </p>
      </DocsSection>

      <DocsSection title="OAuth consent and secret lifecycle">
        <ul className="list-disc space-y-2 pl-6">
          <li>Users sign in and consent directly at Google, GitHub, or the approved provider.</li>
          <li>Passwords remain with the provider and are never submitted to AverQel.</li>
          <li>PKCE verifier data and signed OAuth state are held in encrypted, single-use transaction storage.</li>
          <li>Access tokens, refresh tokens, and client secrets are encrypted and never serialized into frontend DTOs.</li>
          <li>Verified granted scope names and safe account identity may be returned to the owning user.</li>
          <li>Disconnect removes the local credential record and attempts provider revocation where the provider supports it.</li>
          <li>OAuth secrets are excluded from logs, prompts, MCP events, inspector payloads, and marketplace metadata.</li>
        </ul>
      </DocsSection>

      <DocsSection title="Permission modes and precedence">
        <p>
          <strong>Always allow</strong> means the tool may run without a per-call approval only when
          every connection, scope, risk, tenant, catalog, and platform rule passes. It is not a
          global bypass.
        </p>
        <p>
          <strong>Needs approval</strong> pauses a risky action for an explicit user decision.
          <strong>Blocked</strong> prevents the tool from being offered or called. Blocked wins over
          every less restrictive setting.
        </p>
        <p>
          <strong>Read-only</strong> prevents writes and higher-risk actions even if a tool was
          otherwise selected. The risk ceiling limits the highest allowed risk class. Conversation
          and DeepSpace controls are additional gates: when an override is absent, stale, or false,
          the connection is denied for that scope.
        </p>
      </DocsSection>

      <DocsSection title="DeepSpace behavior">
        <p>
          When a user asks DeepSpace to search Gmail, inspect GitHub, read a Drive file, or perform
          another MCP task, AverQel checks the current tenant, user, connection, provider approval,
          authentication state, catalog revision, scope enablement, tool mode, risk policy, and
          confirmation requirement before planning and again immediately before the remote call.
        </p>
        <p>
          A blocked or disabled tool is not offered to the MCP action surface. A tool result may be summarized for
          the user, but raw remote payloads are not returned through the MCP inspector or persisted as
          unredacted MCP events.
        </p>
      </DocsSection>

      <DocsSection title="Admin and operational boundaries">
        <p>
          Administrators can manage approved catalog metadata through the protected catalog
          permission. Normal admin views receive operational metadata, not users&apos; OAuth tokens or
          private MCP content. Audit and deletion workflows remain tenant-aware and do not require
          exposing raw secrets.
        </p>
        <p>
          These controls describe AverQel&apos;s application contract. Operators must still configure
          production OAuth clients, callback URLs, encryption keys, database RLS, retention, network
          egress, provider scopes, and incident procedures for their deployment.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
