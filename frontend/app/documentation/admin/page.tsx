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
          The dashboard shows each staff page only to its assigned role, and protected APIs also
          enforce backend permissions. Frontend visibility alone is not the security boundary.
          Platform-wide administration still requires an account in the configured platform-admin
          allowlist. Support Manager, Feedback Manager, and Qel Connect Moderator are separate
          roles; assigning one does not grant platform administration. Support Managers must also be
          in the platform-admin allowlist. A platform administrator can grant or revoke only these
          staff roles from the Users view; the change preserves each account&apos;s base role and is
          audited. A new grant takes effect after the user signs in again; removal applies to
          subsequent API requests. Disable, reactivate, force logout, and deletion use separate
          backend permissions and are recorded as audit events.
        </p>
      </DocsSection>
      <DocsSection title="Account and workspace information">
        <p>
          The default user view contains account email, enabled or disabled state, assigned roles,
          and multi-factor status. It does not show individual document, query, chat, or recent
          activity counts. The workspace list shows its status and seats in use; its record update
          time is not presented as user activity.
        </p>
        <p>
          Product analytics use a rolling 30-day window and are hidden unless at least five
          different workspace members contributed. Daily chart points are also hidden unless at
          least five members contributed that day.
        </p>
      </DocsSection>
      <DocsSection title="Different queues have different scopes">
        <p>
          Support access is a separate Support Manager role. Support Managers can read ticket
          content and attachments across workspaces, and must also be in the platform-admin
          allowlist. Feedback review is a separate Feedback Manager role: managers can read
          submitted text across workspaces and reply in-app, while the staff view omits submitter
          email and account IDs. Qel Connect moderation is a separate tenant-scoped moderator role;
          report details load only when opened. These privileged reads and changes are audited.
          Internal support and moderator notes are not returned to the person who submitted the
          request.
        </p>
      </DocsSection>
      <DocsSection title="Deletion and operations">
        <p>
          The workspace purge deletes workspace documents and source files, extracted text and
          embeddings, ingestion and index records, queries and citations, conversations and
          messages, Qel Connect workspace data, comments, and pinned findings. It keeps user
          accounts, provider settings, support and feedback records, and audit records. Operators
          must select a reason and type the exact workspace ID to request it. A different authorized
          platform administrator must approve the request before it starts; both actions are
          audited. Account-level privacy requests use the separate user privacy controls; this
          workspace purge does not process them. If object storage is unavailable, failed file
          removals remain in the storage cleanup retry queue.
        </p>
        <p>
          Document recovery and storage cleanup views expose operational status and error codes
          only; they omit document identifiers, object paths, and raw provider error messages.
          Account deletion removes account-owned database records. If object storage is unavailable,
          file cleanup is queued for background retries; no fixed completion time is promised.
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
