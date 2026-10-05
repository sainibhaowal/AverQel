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
          The dashboard hides administrative navigation from users without an admin role, and
          protected APIs also enforce backend permissions. Frontend visibility alone is not the
          security boundary. Access is determined by the authenticated account, tenant, role, and
          permission required by each route.
        </p>
      </DocsSection>
      <DocsSection title="Different queues have different scopes">
        <p>
          Support staff may read support tickets and feedback submissions so they can respond.
          Tenant administrators may review collection reports scoped to their tenant. These are
          purpose-specific permissions; they do not create a universal interface for browsing every
          user&apos;s content. Internal support notes are not returned to the ticket submitter.
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
