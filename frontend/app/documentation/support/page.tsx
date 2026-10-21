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
          your account and the platform-key owner, who can decrypt them to provide support. This is
          the administrator account that initialized the shared key; other allowlisted
          administrators cannot unlock the key or decrypt message bodies. Internal notes are
          encrypted only for that key owner and are not shown in your view. The first time you use
          Support or Feedback, create your own encryption key with a passphrase of at least 14
          characters; you do this once for your account, not for every ticket. The passphrase is not
          sent to the server, and losing it can make your encrypted copy unreadable. If an
          administrator is migrating older tickets, your key must exist first; records without it
          are skipped until you finish setup, and the administrator can then retry. The app decrypts
          messages in your browser after you unlock your key; there is no separate decrypt button.
          Legacy Support Manager assignments do not grant queue access. Older records stay plaintext
          until the administrator runs the migration in Support Management, and older backups may
          retain plaintext until expiry. Account IDs, email needed to route support, ticket status,
          category, timestamps, and attachment sizes remain visible to the service. After you unlock
          your key, it stays in browser memory across Support and Feedback navigation and locks
          after four hours without activity, sign-out, or login-session expiry. Reloading or closing
          the tab clears the in-memory unlock, so you may need to enter your passphrase again. A
          compromised live server could change the browser code or keys, and decrypted content is
          visible on your device. Replies show profile photos when participants have added one, with
          initials shown when no photo is available. Resolved or closed tickets and their
          attachments are automatically deleted after 365 days by default; unresolved tickets remain
          available until resolved or closed. Privileged reads are audited. Do not submit
          information support does not need.
        </p>
        <p>
          This encryption passphrase is not two-factor authentication. It unlocks your message key;
          it does not sign you in, and you do not enter it for every ticket or reply. The
          platform-key owner must initialize the shared support key before encrypted forms can work.
          If the form reports that support encryption is unavailable (HTTP 503), contact the
          platform administrator so they can finish that one-time setup. If your own key is not set
          up yet, the page asks you to create it. Save the passphrase: AverQel cannot recover it.
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
