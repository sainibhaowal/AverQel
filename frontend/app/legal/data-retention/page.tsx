import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function DataRetentionPage() {
  return (
    <PolicyLayout
      eyebrow="Retention"
      title="Data Retention & Deletion"
      intro="AverQel keeps only the data required to operate the service, secure accounts, and meet billing obligations."
    >
      <PolicySection title="Data Retention (Cloud Server)">
        <p>
          Account identities, subscription receipts, license checks, documents, and chat records are
          retained securely on the VPS database for active workspaces, account management, and
          support.
        </p>
      </PolicySection>
      <PolicySection title="Account Deletion Controls">
        <p>
          Users can request full account deletion from the Trust & Privacy settings. Deleting an
          account permanently erases all associated data and metadata from our PostgreSQL cloud
          database.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
