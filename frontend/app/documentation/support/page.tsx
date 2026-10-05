import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function SupportDocsPage() {
  return (
    <DocsShell
      title="Support centre"
      intro="Use Support Centre to open a private ticket with the AverQel support team, provide relevant details, and continue the conversation as the ticket is updated."
    >
      <DocsCards
        items={[
          {
            title: "Create a ticket",
            body: "Choose the closest category, give the issue a concise subject, and describe what happened and what you expected.",
          },
          {
            title: "Follow the thread",
            body: "Public support replies and status changes appear in your ticket. Reply with requested details to continue the conversation.",
          },
          {
            title: "Attach a file",
            body: "The current interface accepts PDF, PNG, JPEG, and UTF-8 text attachments up to 5 MiB, subject to validation, malware scanning, and available storage.",
          },
          {
            title: "Understand status",
            body: "Tickets can move through open, in progress, waiting for user, resolved, and closed states. A user reply can reopen a resolved or closed ticket.",
          },
        ]}
      />
      <DocsSection title="How to get a useful response">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Describe the page or workflow and the steps that reproduce the issue.</li>
          <li>Include the time and timezone and any visible request or ticket reference.</li>
          <li>
            Attach only a file needed to understand the issue, after removing unrelated personal
            data.
          </li>
          <li>
            Do not include passwords, API keys, recovery codes, private documents, or production
            secrets.
          </li>
          <li>Watch the ticket thread for a reply or request for more information.</li>
        </ol>
      </DocsSection>
      <DocsSection title="Who can read support content">
        <p>
          Your ticket and public replies are visible to you and authorized support staff. Authorized
          staff may also record internal notes that are not shown in your user view. Support content
          is not end-to-end encrypted. Access is controlled by the application and backend
          authorization; do not submit information that support does not need.
        </p>
      </DocsSection>
      <DocsSection title="Response targets and email">
        <p>
          The current backend records elapsed-UTC first-response and resolution targets (8 and 72
          hours for normal priority; priority changes can select different targets) and can alert
          support staff when tickets become overdue. These are operational targets, not a guarantee
          of response by a particular wall-clock time; they do not use a business-hours calendar,
          and waiting for the user does not pause the resolution clock. Email notifications require
          the deployment to configure SMTP and run the notification worker and scheduler. In-app
          ticket updates remain the primary thread.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
