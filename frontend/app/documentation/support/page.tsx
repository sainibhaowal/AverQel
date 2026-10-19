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
            body: "The current interface accepts attachments up to 5 MiB and encrypts them in your browser before upload. The server cannot scan encrypted files for malware, so open only files you trust.",
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
          New and migrated ticket text, replies, and attachments are encrypted in your browser for
          your account and the allowlisted platform administrator, who can decrypt them to provide
          support. Internal notes are encrypted only for the administrator and are not shown in your
          view. Legacy Support Manager assignments do not grant queue access. Your encryption
          passphrase is not sent to the server; losing it can make your messages unreadable. Older
          records stay plaintext until the administrator runs the migration in Support Management,
          and older backups may retain plaintext until expiry. Account IDs, email needed to route
          support, ticket status, category, timestamps, and attachment sizes remain visible to the
          service. A compromised live server could change the browser code or keys, and decrypted
          content is visible on your device. Resolved or closed tickets and their attachments are
          automatically deleted after 365 days by default; unresolved tickets remain available
          until resolved or closed. Privileged reads are audited. Do not submit information support
          does not need.
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
      <DocsSection title="Contact without signing in">
        <p>
          Visitors can use the Contact the developer form at the bottom of the public landing page.
          First, it sends a one-time code to the reply email address you enter. After you verify
          that address, the form sends your name, subject, and message through the mail service
          configured for that site; replies are addressed to the verified email. Direct mail to the
          published contact address is forwarded only when the site has configured Resend inbound
          processing. Messages are not saved in AverQel&apos;s application database. The mail
          provider and receiving mailbox handle them under their own retention and privacy rules. Do
          not include passwords, API keys, private documents, or other information the developer
          does not need. The form is unavailable until the site operator configures secure email
          delivery.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
