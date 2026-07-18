import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ProfileDocsPage() {
  return (
    <DocsShell
      title="Profile Settings"
      intro="Manage your account profile, connection credentials, active sessions, and personal identity configurations within the AverQel workspace."
    >
      <DocsCards
        items={[
          {
            title: "Identity Management",
            body: "Update your profile email, connection nickname, avatar, and workspace labels to customize your peer-to-peer presence.",
          },
          {
            title: "Permanent Connection ID",
            body: "Your connection code is a permanent, 8-character hash used by peers to invite you into E2EE direct chat channels.",
          },
          {
            title: "Active Sessions Monitor",
            body: "Inspect active device logins, IP access parameters, and session leases to prevent unauthorized account access.",
          },
          {
            title: "Account Cleanup",
            body: "Initiate full account purging, delete local storage indexes, and reset keys from your profile settings console.",
          },
        ]}
      />

      <DocsSection title="Managing Connection Credentials">
        <p>
          Your Profile configuration serves as the base for establishing E2EE Collections. Here, you can find your permanent Connection ID. If you change your connection name/nickname, it immediately updates across all active collection topologies for your connected peers.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
