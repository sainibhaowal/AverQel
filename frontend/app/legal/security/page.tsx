import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function SecurityPage() {
  return (
    <PolicyLayout
      eyebrow="Trust And Security"
      title="Security controls and their limits"
      intro="Last reviewed 17 October 2026. This page describes controls present in the application source. It is not a guarantee that risk can be eliminated or proof that a live deployment is configured securely."
    >
      <PolicySection title="Account protection">
        <p>
          The application supports password authentication, configured OAuth login, session
          revocation, logout from all devices, and authenticator-app multi-factor authentication.
          Protect your account credentials and use available security settings.
        </p>
      </PolicySection>

      <PolicySection title="Administrator and staff access">
        <p>
          Platform-wide administration requires both an administrator role and an email in the
          deployment&apos;s platform-admin allowlist. The standard administrator user view is
          limited to email, account status, roles, and multi-factor status. It omits per-user
          document, query, conversation, and recent-activity counts.
        </p>
        <p>
          An allowlisted platform administrator can decrypt support and feedback through Support
          Management and Feedback Management. Legacy Support Manager and Feedback Manager roles do
          not grant access. Public support replies are encrypted for the user and administrator;
          internal notes are encrypted only for the administrator. The feedback queue omits
          submitter email and account IDs. Qel Connect moderators can read report details only in
          their assigned workspace. Privileged reads and administrative changes are audited.
        </p>
      </PolicySection>

      <PolicySection title="Isolation and connected services">
        <p>
          Protected requests are checked against tenant, account ownership, role, and resource
          permissions. Provider credentials are handled by backend services and are not meant to be
          returned in normal product responses. Their protection depends on the configured
          encryption keys and deployment practices.
        </p>
        <p>
          This is a server-side application. When you request an AI, search, embedding, reranking,
          voice, email, or connected MCP action, required information may be processed by the
          configured service. Use only connections appropriate for the information you send.
        </p>
      </PolicySection>

      <PolicySection title="Encryption and service limits">
        <p>
          New and migrated support and feedback content is encrypted in the browser before upload;
          private keys are protected by a passphrase that is not sent to the server. The server
          retains routing metadata, and the platform administrator is an intended recipient who can
          decrypt the content. Older records remain plaintext until the administrator runs the
          migration in each management page. Older backups can retain plaintext until they expire.
          Encrypted attachments cannot be malware-scanned by the server.
        </p>
        <p>
          This protection does not cover the whole product. A compromised live server could serve
          altered browser code or keys, and a compromised device can expose content after it is
          decrypted. The support and feedback encryption design has not been independently audited.
          Security also depends on deployment configuration, patching, monitoring, network
          boundaries, key protection, backups, and incident response.
        </p>
      </PolicySection>

      <PolicySection title="Report a security issue">
        <p>
          Use Support Centre in the application to report a suspected issue. Do not include
          passwords, API keys, recovery codes, or unrelated user content. Support is encrypted for
          you and the allowlisted platform administrator after key setup and legacy migration. The
          hosted service is operated by Ravinder Singh — Independent Developer, AverQel Independent
          Project. The current source does not specify a public security contact for people who
          cannot sign in.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
