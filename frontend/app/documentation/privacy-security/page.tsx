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
            body: "New and migrated support and feedback text is encrypted in the browser for the submitter and allowlisted platform administrator. Routing metadata remains visible; legacy records need the admin migration.",
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
      <DocsSection title="Qel Connect and encryption">
        <p>
          Qel Connect chat includes client encryption helpers and an optional server-mediated sealed
          storage mode. The Qel Connect connection code is available through the API, and the sealed
          mode can be opened by the API for authorized members. Do not treat Qel Connect chat as
          zero-knowledge or server-blind end-to-end encryption. Qel Connect documents are processed
          server-side. See the{" "}
          <a className="text-primary underline" href="/documentation/collections-sharing">
            Qel Connect guide
          </a>{" "}
          for details.
        </p>
      </DocsSection>
      <DocsSection title="Admin and operational boundaries">
        <p>
          Administrative access is role- and route-specific, and platform-wide routes require an
          account in the configured platform-admin allowlist. The user and platform administrator
          are the intended decryption recipients for support and feedback. Internal notes are
          administrator-only. Legacy Support Manager and Feedback Manager assignments do not grant
          access to those queues. The feedback queue omits submitter email and account IDs.
          Designated Qel Connect moderators can read report details only inside their active tenant.
          Support and feedback metadata remain service-visible, and the administrator can decrypt
          the messages by design. The browser-based admin migration must be run to convert old
          plaintext records; backups can retain old copies until expiry. Privileged support,
          feedback, and moderation reads and changes are recorded in the audit log.
        </p>
        <p>
          Browser encryption does not protect content from a compromised device or from a
          compromised live server that changes the application code or recipient keys. The server
          cannot malware-scan encrypted attachments. This application encryption has not been
          independently audited; do not read it as a guarantee that all AverQel content is
          end-to-end encrypted.
        </p>
        <p>
          The default account view shows email, status, roles, and MFA status without per-user usage
          counts or recent activity. Global worker metrics require platform-admin access, and the
          public gateway blocks the raw Prometheus route.
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
