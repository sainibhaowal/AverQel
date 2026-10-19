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
          completed on the current session. Allowlisted platform administrators can use
          Support Management and Feedback Management directly. The Users view and backend API do
          not provide staff-role assignment controls; legacy support and feedback role rows do not
          grant queue access. Qel Connect moderation remains a separate, tenant-scoped moderator
          workflow. Disable, reactivate, force logout, and deletion use separate backend
          permissions and are recorded as audit events.
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
          selected operational records. A different authorized platform administrator may approve
          it immediately. A single administrator may approve their own request after a 24-hour hold
          by default (configured between 24 and 168 hours); recent MFA is required, and the requester
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
