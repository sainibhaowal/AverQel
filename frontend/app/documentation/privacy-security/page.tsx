import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function PrivacySecurityPage() {
  return (
    <DocsShell
      title="Privacy & Security"
      intro="How AverQel separates users, protects provider secrets, limits admin visibility, records sensitive actions, and gates agent execution."
    >
      <DocsCards
        items={[
          {
            title: "Private By Default",
            body: "Documents, chats, queries, DeepSpace conversations, notes, connectors, and personal providers are scoped to the owning user and protected from other users.",
          },
          {
            title: "Encrypted Provider Secrets",
            body: "Provider API keys and tokens are encrypted at rest, masked in responses, and never returned as raw values.",
          },
          {
            title: "Admin Metadata Model",
            body: "Platform admins manage account status, usage counts, security events, audit logs, and deletion workflows without normal access to private content bodies.",
          },
          {
            title: "Audit And Deletion Controls",
            body: "Sensitive admin operations are audited. Break-glass is disabled by default, and deletion workflows are tracked without requiring raw secret or content disclosure in normal flows.",
          },
        ]}
      />
      <DocsSection title="Server-Side Processing, Isolated Accounts">
        <p>
          AverQel processes documents, chats, retrieval, and AI workflows on the server. That does
          not mean user data is mixed together. It means the platform hosts and processes the data
          while enforcing account and tenant isolation in the application layer.
        </p>
        <p>
          The same rule applies to DeepSpace: read-only actions can auto-run, but writes, syncs, and
          shell execution are approval-gated so the UI and backend stay aligned on what is allowed.
        </p>
      </DocsSection>
      <DocsSection title="Durable DeepSpace runs">
        <p>
          Durable runs keep their authoritative state in PostgreSQL: tenant/user ownership,
          checkpoints, approvals, redacted ordered event records, tool idempotency records, trace
          identifiers, final assistant-message links, and dead-letter records. Redis may provide a
          short-lived reconnect snapshot, but it is never the durable mission source of truth.
        </p>
        <p>
          New chat runs are durable by default and there is no user-facing legacy/durable selector.
          Existing route names remain as compatibility adapters so clients do not break. Durable
          event payloads and checkpoints use redaction, every query remains tenant/user scoped, and
          durable tool invocations use idempotency keys to prevent duplicate side effects.
        </p>
        <p>
          Durable controls describe the runtime contract, not a blanket certification for every
          deployment. Production operators must validate provider limits, infrastructure capacity,
          retention settings, connector scopes, and incident procedures for their own environment.
        </p>
      </DocsSection>
      <DocsSection title="Compliance Position">
        <p>
          AverQel is designed for EU/US privacy alignment through minimization, access limitation,
          auditability, deletion workflows, and clear policy pages. Final production compliance also
          requires legal review, infrastructure review, subprocessors, retention settings, and
          incident response procedures.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
