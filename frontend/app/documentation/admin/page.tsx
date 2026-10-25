import { DocsSection, DocsShell } from "../_components/DocsShell";

/** Direct compatibility route; admin workflows are intentionally omitted from public navigation. */
export default function AdminDocsPage() {
  return (
    <DocsShell
      title="Administrative controls"
      intro="AverQel administrative screens are restricted workflows for specifically authorized operators. They are not part of the normal user workspace."
    >
      <DocsSection title="Role and route protection">
        <p>
          Protected APIs enforce backend permissions; frontend visibility alone is not the security
          boundary. Platform-wide administration requires both an administrator role and an account
          in the configured platform-admin allowlist, with authenticator-based MFA enabled and
          completed on the current session. Allowlisted platform administrators can use Support
          Management and Feedback Management directly. The Users view and backend API do not provide
          staff-role assignment controls; legacy support and feedback role rows do not grant queue
          access. Qel Connect moderation remains a separate, tenant-scoped moderator workflow.
          Disable, reactivate, force logout, and deletion use separate backend permissions and are
          recorded as audit events.
        </p>
        <p>
          Data Deletion checks the current session before loading platform-wide account and storage
          cleanup data. If the session is not eligible, it explains whether the account needs to be
          added to the platform-admin allowlist, needs authenticator setup, or needs a new MFA
          sign-in. The status check does not grant access; every administrative API continues to
          enforce the platform-admin and permission checks on the server.
        </p>
      </DocsSection>
      <DocsSection title="The six administrator modules">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Users:</strong> review account status, roles, MFA, creation time, and last
            successful sign-in; disable, reactivate, force logout, or erase an account. The UI does
            not assign staff roles.
          </li>
          <li>
            <strong>Audit Logs:</strong> filter platform events by action, security event, or exact
            account ID. The table shows recorded outcomes and UTC timestamps; expand a row to see
            full available IDs. Actor and tenant UUIDs are shortened in the table, and trace IDs
            show their first eight characters.
          </li>
          <li>
            <strong>Support Management:</strong> triage and reply to support tickets, manage
            priority/status/assignment, add administrator-only notes, and migrate legacy tickets.
          </li>
          <li>
            <strong>Feedback Management:</strong> review and reply to feedback, update its status,
            and launch campaigns. The queue does not show submitter email or account ID.
          </li>
          <li>
            <strong>Data Deletion:</strong> erase one account, review failed file-cleanup jobs, or
            request a separate tenant-content purge. Account erasure and tenant purge have different
            scopes and approval steps.
          </li>
          <li>
            <strong>System Metrics:</strong> inspect service-wide request, error, database, worker,
            and selected DeepSpace counters. The live stream can show partial or unavailable data
            when shared metrics storage is unavailable.
          </li>
        </ul>
        <p>
          Backend event timestamps are UTC instants. Audit Logs and Data Deletion explicitly display
          UTC; Users, Support Management, Feedback Management, and System Metrics use the
          browser&apos;s local time zone. Check the displayed zone before comparing dates from
          different modules.
        </p>
      </DocsSection>
      <DocsSection title="Account information">
        <p>
          The user view contains account email, tenant, enabled or disabled state, assigned roles,
          multi-factor status, account creation time, and the last completed sign-in. A sign-in that
          is still waiting for a required second factor does not update the last sign-in time.
        </p>
      </DocsSection>
      <DocsSection title="Platform security timeline">
        <p>
          Audit Logs displays events across tenants and can filter the security timeline by account
          ID. It includes registration and verified OAuth account creation, completed password and
          OAuth sign-ins with MFA outcome, failed sign-ins and lockouts, password changes, session
          revocation, and administrator disable, reactivate, force-logout, and erasure actions.
          Failed password attempts for unknown accounts, OAuth callback failures, and cancellations
          appear as anonymous platform events without the submitted email or IP address. Details
          exclude passwords, second-factor codes, prompts, documents, chats, and query contents.
          Account-erasure audit events retain the opaque target account ID (not its email) for the
          configured audit period, 90 days by default.
        </p>
      </DocsSection>
      <DocsSection title="Different queues have different scopes">
        <p>
          Allowlisted platform administrators can read and respond to support tickets and feedback
          across tenants. Legacy Support Manager and Feedback Manager assignments do not grant
          access to these queues. The feedback queue omits submitter email and account IDs. Qel
          Connect moderation remains a separate tenant-scoped moderator workflow, and report details
          load only when opened. These privileged reads and changes are audited. Internal support
          and moderator notes are not returned to the person who submitted the request.
        </p>
      </DocsSection>
      <DocsSection title="Support encryption is different from sign-in MFA">
        <p>
          TOTP MFA verifies an administrator&apos;s sign-in session and is required for platform
          administration. The Support and Feedback encryption passphrase unlocks a browser-held
          private key so its owner can read encrypted message content; it does not sign the user in
          and is not requested for each ticket or reply. One platform administrator initializes and
          owns the shared public key; only that same account can unlock its private key. Another
          allowlisted administrator receives HTTP 403 at the key endpoint, so the current Support
          and Feedback UI cannot open for that account. Each user initializes their own key once.
          The key stays unlocked across Support and Feedback navigation for up to four hours without
          activity; sign-out, login-session expiry, a reload, or closing the page clears the
          in-memory key.
        </p>
        <p>
          The application does not currently support platform-key transfer or recovery. Keep the
          owner account active and protect its passphrase. Erasing the owner account removes its
          stored key backup and may make existing administrator copies unreadable. Assignment to
          another administrator does not transfer decryption access.
        </p>
        <p>
          If the platform key is missing, Support or Feedback cannot encrypt new messages and the
          public-key request returns HTTP 503 until an administrator initializes it. A user without
          a personal key receives HTTP 404 from the personal-key lookup and should complete the
          one-time setup. See the{" "}
          <a className="text-primary underline" href="/documentation/support">
            Support guide
          </a>{" "}
          for the user setup steps.
        </p>
      </DocsSection>
      <DocsSection title="Deletion and operations">
        <p>
          The Data Deletion screen erases one selected user account and that account&apos;s owned
          database records, including provider connections and settings, queries, documents,
          conversations, support tickets, and submitted feedback. Records and content owned by other
          users in the same tenant remain. The screen requires typing <code>DELETE</code> followed
          by the account email and requires recent authenticator MFA. A protected bootstrap
          administrator and the currently signed-in administrator cannot be deleted through this
          action.
        </p>
        <p>
          Account-owned object-storage files are queued in the same transaction as database erasure
          and retried by the maintenance worker. The API reports how many cleanup jobs were queued;
          failed jobs remain available to the restricted operator cleanup view. Audit security
          events retain only minimal anonymous metadata. Backups and copies held by external
          providers follow their own retention and deletion controls, so live-app deletion does not
          promise immediate removal from every backup or third-party system.
        </p>
        <p>
          A separate tenant-data purge removes tenant content while retaining account records and
          selected operational records. A different authorized platform administrator may approve it
          immediately. A single administrator may approve their own request after a 24-hour hold by
          default (configured between 24 and 168 hours); recent MFA is required, and the requester
          can cancel while it awaits approval. The worker checks the delay again before processing.
          This is not the account-erasure workflow shown on the Data Deletion screen.
        </p>
        <p>
          Global worker and request metrics are limited to platform operators. The unauthenticated
          Prometheus route is blocked by the public gateway; the API port is not exposed publicly in
          the production compose configuration.
        </p>
      </DocsSection>
      <DocsSection title="Operational responsibility">
        <p>
          Operators must follow the deployment&apos;s least-privilege, audit, privacy, incident
          response, and account recovery policies. The availability of an admin page or route does
          not prove that the current deployment has enabled, migrated, or verified its workflow.
          Detailed operational procedures belong in the restricted operator runbooks, not the public
          product guide.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
