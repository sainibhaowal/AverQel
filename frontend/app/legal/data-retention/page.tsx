import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function DataRetentionPage() {
  return (
    <PolicyLayout
      eyebrow="Retention"
      title="Data Retention & Deletion"
      intro="Last reviewed 19 October 2026. Retention depends on record type, workspace settings, and the operator's deployment. The periods below are application defaults, not a guarantee that every deployment has configured or run its cleanup workers."
    >
      <PolicySection title="Application defaults">
        <ul className="list-disc space-y-2 pl-5">
          <li>Audit records: 90 days by default.</li>
          <li>Transient records: 30 days by default.</li>
          <li>Revoked authentication sessions and related token records: 90 days by default.</li>
          <li>Feedback records of any status: 365 days after their last update by default.</li>
          <li>Support tickets of any status: 365 days after their last update by default.</li>
          <li>Dismissed in-app notifications: 365 days by default.</li>
          <li>Delivered or suppressed notification-delivery records: 90 days by default.</li>
        </ul>
        <p>
          The operator can configure feedback and support retention from 30 to 3650 days with
          <code> AKS_FEEDBACK_RETENTION_DAYS</code> and
          <code> AKS_SUPPORT_TICKET_RETENTION_DAYS</code>. The daily cleanup worker removes old
          records regardless of status, deletes related in-app notifications, and queues support
          attachment objects for retryable deletion. Cleanup may take longer if object storage is
          unavailable. The PostgreSQL, MinIO, and production-config backup scripts prune their
          managed local archives after successful runs, keeping 30 days by default. The operator can
          change this with the script&apos;s <code>--retention-days</code> option or by exporting
          <code> AKS_BACKUP_RETENTION_DAYS</code> before running it. This is not an automatic
          schedule, and remote copies or VPS snapshots use their own retention settings. The scripts
          create checksums but do not encrypt archives.
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
          Account deletion removes the account and its account-owned live database records,
          including provider connections and settings, documents, queries, conversations, support
          tickets, submitted feedback, and personal connection data. In a shared tenant, records
          owned by other users are retained. Account-owned object-storage files are queued for
          background deletion, including document files, media, library versions, and temporary
          upload chunks; the maintenance worker retries failed jobs, and an operator may need to
          investigate jobs that reach the retry limit. There is no fixed cleanup completion time.
        </p>
        <p>
          A minimal security audit trail may remain for its configured retention period (90 days by
          default). Events attributed to the erased account are anonymized. A separate administrator
          erasure event retains the opaque account ID, action, time, outcome, and cleanup count for
          the audit period; it does not retain the deleted account&apos;s email. Administrative
          account erasure requires recent administrator MFA and exact email confirmation. Backup scripts
          prune managed local archives after successful runs (30 days by default), but deletion
          does not immediately remove records from backups or copies held by external providers.
        </p>
      </PolicySection>

      <PolicySection title="Tenant-data purge is different">
        <p>
          A separate tenant-data purge removes its documents and source files, extracted text and
          embeddings, ingestion and index records, queries and citations, conversations and
          messages, Qel Connect workspace data, comments, and pinned findings. It retains user
          accounts, provider settings, support and feedback records, and audit records. A platform
          administrator must confirm the exact tenant ID and choose a reason to request this
          destructive operation. A second authorized platform administrator may approve it
          immediately. For a single-owner installation, the requester may approve after a 24-hour
          hold by default (configurable from 24 to 168 hours). Recent MFA is required for the
          request, approval, and cancellation; the requester can cancel while it awaits approval.
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
