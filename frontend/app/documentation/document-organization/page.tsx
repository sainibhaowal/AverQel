import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function DocumentOrganizationDocsPage() {
  return (
    <DocsShell
      title="Documents Hub organization & collaboration"
      intro="Keep source files understandable and share access deliberately. The exact controls depend on the role granted by the workspace and the features enabled on that deployment."
    >
      <DocsSection title="Organization controls">
        <p>
          The current Documents Hub includes tags and nested folders for basic organization. Higher
          role levels can expose saved views, classification rules, and organization schedules.
          Administrators have additional controls for smart collections, webhooks, and
          administrative document operations. These are permission tiers, not separate copies of the
          document library.
        </p>
        <p>
          Saved views apply filters to documents the current user is allowed to access. Smart
          collections evaluate configured conditions against eligible documents; they do not copy
          files or expand access. Classification rules and schedules run through authorized
          background work and remain subject to the same tenant and document checks.
        </p>
      </DocsSection>
      <DocsSection title="Sharing, comments & versions">
        <p>
          Where enabled, document sharing grants specific access or creates a revocable, expiring
          share link. Comments, mentions, version comparison, and restore actions are permission
          checked. Restoring a prior version creates a controlled document state; review the result
          before relying on it.
        </p>
        <p>
          Shared collection documents remain ordinary source files processed by the Documents Hub.
          Collection membership controls access to the shared item; it does not make the document
          zero-knowledge or remove server-side processing needed for preview, OCR, and indexing.
        </p>
      </DocsSection>
      <DocsSection title="Bulk actions & quarantine">
        <p>
          Eligible users can select multiple documents for supported actions such as organization or
          processing recovery. The API checks each item independently and can return a mix of
          accepted and rejected results. Quarantine is a security state: inspect the displayed
          reason and use the offered release or removal action only when authorized. Destructive
          actions require confirmation where the interface provides it.
        </p>
      </DocsSection>
      <DocsSection title="Role and deployment notes">
        <p>
          The backend is authoritative for role permissions and tenant access. The public guide
          intentionally describes capability classes rather than promising that every account can
          see every control. Webhook delivery, schedules, scanning, and document processing also
          require their corresponding backend workers and configuration.
        </p>
        <p>
          For the implementation-level route map and current feature matrix, see the
          repository&apos;s
          <a
            className="text-primary underline"
            href="https://github.com/sainibhaowal/AverQel/blob/main/backend/docs/library/09-documents-hub-user-guide.md"
          >
            {" "}
            Documents Hub user guide
          </a>
          . Verify its commit-specific deployment notes before treating them as rollout evidence.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
