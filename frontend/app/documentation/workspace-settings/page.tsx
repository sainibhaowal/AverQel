import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function WorkspaceSettingsDocsPage() {
  return (
    <DocsShell
      title="Plans, storage & workspace settings"
      intro="Settings show the account’s available controls, storage use, notification preferences, providers, and privacy actions. What appears depends on role and deployment configuration."
    >
      <DocsSection title="Plan and storage">
        <p>
          The plan page reports the role-derived plan and its current storage allocation, plus
          measured workspace usage. This describes the allocation configured for the account; it is
          not a purchase, invoice, renewal, or payment-management flow. AverQel does not currently
          expose a paid-subscription lifecycle through this area.
        </p>
        <p>
          Storage details can break usage down across supported data classes. Retention controls
          should be read carefully: a retention preference or archive operation is not the same as
          immediate permanent deletion. The exact behavior and currently enabled purge operations
          are deployment- and policy-dependent.
        </p>
      </DocsSection>
      <DocsSection title="Account security">
        <p>
          Profile and security settings provide the controls shown for your account, including
          password management, two-factor authentication where enabled, and review or revocation of
          linked sessions. Keep recovery information private and revoke sessions you do not
          recognize.
        </p>
      </DocsSection>
      <DocsSection title="Privacy actions">
        <p>
          Trust &amp; Privacy includes the available account export and account deletion workflows.
          Export and deletion are consequential operations; follow the confirmation steps and any
          displayed account verification requirements. Account deletion is distinct from changing
          local browser data or a workspace retention preference.
        </p>
      </DocsSection>
      <DocsSection title="Provider settings">
        <p>
          The provider area can configure supported model, embedding, reranking, and local runtime
          providers. The list and features depend on provider support and deployment configuration.
          A provider entry does not by itself confirm credentials, network access, model
          availability, or successful requests; use the available test or status controls.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
