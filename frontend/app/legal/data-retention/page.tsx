import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function DataRetentionPage() {
  return (
    <PolicyLayout
      eyebrow="Retention"
      title="Data Retention & Deletion"
      intro="Effective 15 August 2026. AverQel retains information for the period needed to provide the requested feature, secure accounts, operate the service, resolve disputes, and meet legal obligations."
    >
      <PolicySection title="Data Retention (Cloud Server)">
        <p>
          Structured records are stored in PostgreSQL; runtime coordination uses Redis; documents
          and media may be stored in MinIO-compatible object storage. Active workspace content is
          retained until the user or an authorized administrator deletes it, subject to pending
          jobs, security records, legal obligations, and backup lifecycle.
        </p>
        <p>
          Current operational defaults include 90 days for audit records, 30 days for transient
          records, and a configurable session-memory retention window. These defaults can change by
          deployment and do not replace the retention rules shown in the product.
        </p>
      </PolicySection>
      <PolicySection title="Account Deletion Controls">
        <p>
          Users can use the available privacy settings or Support Centre to request deletion.
          Deletion is processed through account and data-deletion workflows. It may take time to
          remove related objects, queued work, audit records, and encrypted backups; data required
          for security or law may be retained for the applicable period.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
