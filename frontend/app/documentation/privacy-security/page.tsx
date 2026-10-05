import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function PrivacySecurityPage() {
  return (
    <DocsShell
      title="Privacy & security"
      intro="AverQel applies authentication, tenant and user authorization, and integration policies in its backend. These controls reduce unauthorized access; they do not mean that all content is client-only or invisible to the service."
    >
      <DocsCards
        items={[
          {
            title: "Tenant and user isolation",
            body: "Protected API routes scope reads and writes to the authenticated account, tenant, resource ownership, and role permissions.",
          },
          {
            title: "Credential handling",
            body: "Provider and OAuth credential material is handled by backend services and is not intended to be returned in normal frontend responses. Exact protection depends on configured encryption keys and deployment practices.",
          },
          {
            title: "Tool authorization",
            body: "Connected tools are governed by ownership, enabled status, provider policy, tool modes, risk limits, and required approvals.",
          },
          {
            title: "Content boundaries",
            body: "Documents and AI requests are processed by configured server-side services. Authorized support staff can read submitted support and feedback threads.",
          },
        ]}
      />
      <DocsSection title="MCP account and tenant isolation">
        <p>
          MCP connection lookups are scoped by tenant, user, and provider connection. DeepSpace tool
          execution checks the owning account and relevant connection and conversation permissions;
          frontend state is not authorization evidence. Review a provider&apos;s requested scopes
          and policy before connecting it.
        </p>
      </DocsSection>
      <DocsSection title="OAuth consent and secret lifecycle">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Users consent on the provider&apos;s authorization page; AverQel does not need the
            provider password.
          </li>
          <li>
            Access tokens, refresh tokens, and client secrets are handled server-side and encrypted
            at rest where the configured credential storage applies.
          </li>
          <li>
            Only safe account details and granted scope information needed by the interface should
            be exposed to the owning user.
          </li>
          <li>
            Disconnect removes local connection credentials and requests provider revocation where
            supported; remote revocation behavior is provider-dependent.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Permission modes and precedence">
        <p>
          MCP controls can include Read-only, Always allow, Needs approval, or Blocked modes, along
          with connection, conversation, and risk limits. A more restrictive applicable rule should
          prevent a tool call. Always allow does not bypass backend authorization, provider state,
          or platform safety rules. Review the connector guide for current precedence details.
        </p>
      </DocsSection>
      <DocsSection title="AI providers and content processing">
        <p>
          When a user sends a prompt or document question to an external model provider, the backend
          sends the content needed for that request to the configured provider. Provider retention,
          processing location, and contractual terms are separate from AverQel&apos;s tenant access
          controls. Use a provider approved for the data you intend to process.
        </p>
      </DocsSection>
      <DocsSection title="Collections and encryption">
        <p>
          Collection chat includes client encryption helpers and an optional server-mediated sealed
          storage mode. The collection connection code is available through the API, and the sealed
          mode can be opened by the API for authorized members. Do not treat collection chat as
          zero-knowledge or server-blind end-to-end encryption. Collection documents are processed
          server-side. See the{" "}
          <a className="text-primary underline" href="/documentation/collections-sharing">
            Collections guide
          </a>{" "}
          for details.
        </p>
      </DocsSection>
      <DocsSection title="Admin and operational boundaries">
        <p>
          Administrative access is role- and route-specific. Some privileged workflows intentionally
          allow authorized staff to review support tickets, feedback, collection reports, or
          operational metadata. This is not a promise that administrators can never access user
          content, nor does it provide a general-purpose browser for every user&apos;s private data.
          Sensitive access and actions should follow the deployment&apos;s audit and privacy policy.
        </p>
        <p>
          Operators must protect signing and encryption keys, database and object-storage access,
          OAuth credentials, backups, logs, network egress, and administrative accounts. Production
          security depends on deployment configuration, patching, monitoring, incident response, and
          verified restore procedures as well as application code.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
