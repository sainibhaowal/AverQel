import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function FeedbackDocsPage() {
  return (
    <DocsShell
      title="Share feedback"
      intro="Send product suggestions, bug reports, usability feedback, and other comments to the AverQel team. Your submissions remain attached to your account so you can follow their review."
    >
      <DocsCards
        items={[
          {
            title: "Choose a category",
            body: "Select a topic such as product idea, bug, achievement, UX, documents, Query, DeepSpace, providers, performance, reliability, accessibility, security, or other.",
          },
          {
            title: "Describe the feedback",
            body: "Add a concise subject and enough detail for the team to understand the context and desired outcome.",
          },
          {
            title: "Track review",
            body: "Your feedback list shows the current status. The team can triage, plan, work on, complete, or decline a submission and can reply in its thread.",
          },
          {
            title: "Campaigns are optional",
            body: "An active campaign may ask a focused question. If no campaign is active, you can still submit general feedback.",
          },
        ]}
      />
      <DocsSection title="Feedback status">
        <p>
          Current feedback states are New, Triaged, Planned, In Progress, Completed, and Declined.
          Status is a review signal; Planned does not promise a delivery date, and Completed does
          not necessarily mean a release has already reached every deployment.
        </p>
      </DocsSection>
      <DocsSection title="Privacy and expectations">
        <p>
          Feedback is attached to your account so you can follow replies. New and migrated text is
          encrypted in your browser for your account and the allowlisted platform administrator,
          who can decrypt it to respond. Legacy Feedback Manager assignments do not grant queue
          access. The review queue does not show your email address or account ID. Your encryption
          passphrase is not sent to the server; losing it can make your messages unreadable. Older
          records stay plaintext until the administrator runs the migration in Feedback Management,
          and older backups may retain plaintext until expiry. Account IDs, category, status, and
          timestamps remain visible to the service. A compromised live server could change the
          browser code or keys, and decrypted content is visible on your device. Completed or
          declined submissions are automatically deleted after 365 days by default; active
          submissions are retained while under review. The product does not provide public roadmap
          voting, a community forum, or anonymous telemetry through this page. Do not include
          credentials, recovery codes, customer files, or other sensitive data in feedback.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
