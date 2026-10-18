import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function DataRetentionPage() {
  return (
    <PolicyLayout
      eyebrow="Retention"
      title="Data Retention & Deletion"
      intro="Last reviewed 17 October 2026. Retention depends on record type, workspace settings, and the operator's deployment. The periods below are application defaults, not a guarantee that every deployment has configured or run its cleanup workers."
    >
      <PolicySection title="Application defaults">
        <ul className="list-disc space-y-2 pl-5">
          <li>Audit records: 90 days by default.</li>
          <li>Transient records: 30 days by default.</li>
          <li>Revoked authentication sessions and related token records: 90 days by default.</li>
          <li>Dismissed in-app notifications: 365 days by default.</li>
          <li>Delivered or suppressed notification-delivery records: 90 days by default.</li>
        </ul>
        <p>
          The operator can configure these values. Account sessions, provider records, support
          tickets, feedback, workspace content, and backups have separate lifecycle behavior. Their
          final retention period depends on the applicable feature and deployment configuration. The
          source repository does not define a production backup retention schedule.
        </p>
      </PolicySection>

      <PolicySection title="Public contact messages">
        <p>
          The landing-page contact form first emails a one-time code to the address entered, then
          forwards the verified address, name, subject, and message to the configured SMTP mail
          service. Direct email to the configured contact address may be forwarded by a signed
          Resend webhook to the private inbox. AverQel does not persist verification codes or
          message contents in its application database or application logs. Verification challenge
          fingerprints expire from Redis after 10 minutes and single-use token fingerprints after 30
          minutes. Contact rate-limit fingerprints expire after one hour. Resend and the receiving
          mailbox may retain verification and contact messages under their own retention rules; the
          mailbox owner is responsible for deleting them. Email is not end-to-end encrypted.
        </p>
      </PolicySection>

      <PolicySection title="Workspace content retention">
        <p>
          Workspace storage settings provide Off, 30, 60, and 90-day options for eligible inactive
          content. The lifecycle is archive-first; selecting a period does not mean that all content
          is immediately and permanently deleted at that age. The current server default keeps
          automatic archive disabled unless an operator enables it. Check the retention status shown
          in your workspace settings.
        </p>
      </PolicySection>

      <PolicySection title="Account deletion">
        <p>
          Account deletion removes the account and its account-owned database records, including
          submitted support tickets and feedback. Uploaded object files are deleted directly where
          possible. If object storage is unavailable, a restricted background worker retries the
          cleanup; after the configured retry limit, an operator may need to investigate. There is
          no fixed cleanup completion time.
        </p>
        <p>
          Security and audit records may remain for their configured retention period. Deletion from
          backups follows the deployment&apos;s backup lifecycle, which is not defined in this
          repository, so deletion from the live database does not establish immediate removal from
          every backup.
        </p>
      </PolicySection>

      <PolicySection title="Workspace offboarding is different">
        <p>
          A workspace purge removes its documents and source files, extracted text and embeddings,
          ingestion and index records, queries and citations, conversations and messages, Qel
          Connect workspace data, comments, and pinned findings. It retains user accounts, provider
          settings, support and feedback records, and audit records. A platform administrator must
          confirm the exact workspace ID and choose a reason to request this destructive operation.
          A different authorized platform administrator must approve it before processing begins.
          This does not replace account deletion or individual data-rights requests.
        </p>
      </PolicySection>

      <PolicySection title="Requesting a change or deletion">
        <p>
          Use the in-app Trust &amp; Privacy settings or Support Centre to request an export or
          deletion. The Support Centre requires an account; visitors can use the public contact form
          at the bottom of the landing page. The hosted service is operated by Ravinder Singh —
          Independent Developer, AverQel Independent Project. This source does not publish a direct
          email address; the form is available only when the deployment has configured its SMTP mail
          service.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
