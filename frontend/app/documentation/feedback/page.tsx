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
          The submitter and authorized platform support staff can read and discuss a feedback
          submission. Feedback is not end-to-end encrypted. The product does not provide public
          roadmap voting, a community forum, or anonymous telemetry through this page. Do not
          include credentials, recovery codes, customer files, or other sensitive data in feedback.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
