import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function AdminDocsPage() {
  return (
    <DocsShell
      title="Admin"
      intro="Admin is for platform operation, security, support, and compliance handling. It is not a normal user role."
    >
      <DocsCards
        items={[
          {
            title: "Who Can Be Admin",
            body: "Admin access is controlled by configured allowlisted admin emails and roles. Normal users and editors cannot enter admin routes.",
          },
          {
            title: "What Admin Can See",
            body: "User metadata, role/status, 2FA state, usage counts, audit/security events, document processing counts, and deletion records.",
          },
          {
            title: "What Admin Should Not See By Default",
            body: "Document text, chat prompts, generated answers, provider API keys, OAuth tokens, or private endpoint secrets.",
          },
          {
            title: "Sensitive Actions",
            body: "Disable/reactivate users, force logout, terminate accounts, run deletion workflows, and any exceptional privileged actions must be audited.",
          },
        ]}
      />
      <DocsSection title="Admin Privacy Rule">
        <p>
          The admin dashboard is metadata-first. Admin exists to operate the SaaS safely, not to
          browse user content. User deletion and account control can happen without exposing raw
          provider secrets or normal private content in the admin UI.
        </p>
        <p>
          That boundary matters in production because the operational team needs visibility into
          system health, not user payloads. The audit trail is the source of truth for sensitive
          actions.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
