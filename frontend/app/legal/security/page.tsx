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
          document, query, conversation, and recent-activity counts. Workspace views show status and
          seats; aggregate analytics use a minimum group threshold.
        </p>
        <p>
          Content access is separately assigned for support, feedback, and moderation. Support
          Managers can read support ticket content and attachments across workspaces and must also
          be in the platform-admin allowlist. Feedback Managers can read feedback text across
          workspaces, with submitter email and account IDs omitted from their staff response. Qel
          Connect moderators can read report details only in their assigned workspace. Staff reads
          and administrative changes are audited. Users should not assume that all content is
          invisible to authorized staff.
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
          AverQel does not provide end-to-end encryption for the entire product. Qel Connect has
          limited client-side encryption features, but document processing and other service
          operations may require server access to content. Security also depends on deployment
          configuration, patching, monitoring, network boundaries, key protection, backups, and
          incident response.
        </p>
      </PolicySection>

      <PolicySection title="Report a security issue">
        <p>
          Use Support Centre in the application to report a suspected issue. Do not include
          passwords, API keys, recovery codes, or unrelated user content. Support content is
          readable by assigned Support Managers and is not end-to-end encrypted. The hosted service
          is operated by Ravinder Singh — Independent Developer, AverQel Independent Project. The
          current source does not specify a public security contact for people who cannot sign in.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
