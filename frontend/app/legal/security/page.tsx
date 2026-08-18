import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function SecurityPage() {
  return (
    <PolicyLayout
      eyebrow="Trust And Security"
      title="How the current AverQel deployment protects accounts and workspaces."
      intro="This is a technical overview, not a guarantee that security risk can be eliminated. Controls can change as the independent project and its infrastructure evolve."
    >
      <PolicySection title="Authentication and account security">
        <p>
          The application supports password authentication, OAuth login where configured, session
          revocation, logout-all-devices, and authenticator-app 2FA.
        </p>
      </PolicySection>

      <PolicySection title="Privileged access">
        <p>
          Privileged access is intended for operational oversight, account control, abuse response,
          and security handling. Administrative surfaces are designed around metadata, status,
          usage, and audit records rather than routine browsing of private content.
        </p>
        <p>
          Administrative actions such as disabling users, forcing logout, and running deletion
          workflows do not require routine access to raw provider secrets.
        </p>
      </PolicySection>

      <PolicySection title="Isolation and service boundaries">
        <p>
          Documents, chats, queries, collections, memories, and provider configurations are scoped
          by tenant, user, workspace, ownership, and role checks. Provider secrets are encrypted and
          masked in ordinary views.
        </p>
        <p>
          AverQel is a server-side SaaS, which means the platform hosts and processes product data.
          That does not mean user data is shared between accounts. Isolation is enforced by tenant,
          user ownership, scoped queries, and role checks.
        </p>
      </PolicySection>

      <PolicySection title="User trust expectations">
        <p>
          Users should be able to review connection, approval, retention, and deletion controls in
          the product. Questions or suspected incidents should be reported through the Support
          Centre.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
