import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function SecurityPage() {
  return (
    <PolicyLayout
      eyebrow="Trust And Security"
      title="The security posture users should expect from AverQel."
      intro="AverQel should make its security model understandable: strong authentication, limited privileged access, user isolation, encrypted transport, encrypted provider secrets, and documented owner controls."
    >
      <PolicySection title="Authentication and account security">
        <p>
          AverQel supports password-based authentication, secure session handling, logout
          revocation, logout-all-devices, and time-based 2FA using authenticator apps.
        </p>
      </PolicySection>

      <PolicySection title="Privileged access">
        <p>
          Platform-owner access should be limited to operational oversight, account control, abuse
          response, and security handling. Normal admin views should show metadata, status, usage,
          and audit records rather than private document or chat content.
        </p>
        <p>
          Administrative actions such as disabling users, forcing logout, or running deletion
          workflows should not require routine access to raw provider secrets or private content
          bodies.
        </p>
      </PolicySection>

      <PolicySection title="Isolation and service boundaries">
        <p>
          AverQel should maintain strict separation between user-owned documents, chats, queries,
          collections, and provider configurations. Personal provider secrets should stay encrypted,
          masked, and unavailable to other users.
        </p>
        <p>
          AverQel is a server-side SaaS, which means the platform hosts and processes product data.
          That does not mean user data is shared between accounts. Isolation is enforced by tenant,
          user ownership, scoped queries, and role checks.
        </p>
      </PolicySection>

      <PolicySection title="User trust expectations">
        <p>
          Users should never have to guess what is collected, who can access it, or how to ask for
          help. AverQel should make that visible in the product, not only in backend code.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
