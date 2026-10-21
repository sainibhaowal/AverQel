import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function PrivacyPage() {
  return (
    <PolicyLayout
      eyebrow="Privacy Policy"
      title="How AverQel processes your information"
      intro="Last reviewed 19 October 2026. This notice describes the hosted AverQel application and the access controls present in this source version. The service operator, live hosting region, and enabled external providers depend on the deployment."
    >
      <PolicySection title="Information the service processes">
        <p>
          Account and security information includes your email, account and workspace identifiers,
          roles, multi-factor status, sign-in sessions, and security events. Product information can
          include provider settings, prompts and responses, conversations, memories, queries,
          uploaded files and extracted text, Qel Connect activity, support tickets and attachments,
          feedback you submit, and messages you choose to send through the public contact form.
        </p>
        <p>
          Operational records include request and job status, limited service-health counts,
          administrative audit events, and notification delivery state. The application does not
          show individual document, query, or conversation counts or recent user activity in its
          default administrator user view. Unknown-account password failures and OAuth callback
          failures are logged as anonymous security events without the submitted email or IP
          address.
        </p>
      </PolicySection>

      <PolicySection title="How information is used and shared">
        <p>
          Information is processed to authenticate accounts, provide requested product features,
          store and retrieve user content, route authorized provider requests, operate Qel Connect,
          prevent abuse, secure and maintain the service, and answer support or legal requests.
        </p>
        <p>
          When you configure an AI, embedding, reranking, web-search, voice, email, or MCP-connected
          service, information needed for the selected request may be sent to that service. The
          receiving provider processes it under its own terms and privacy notice. Review the
          provider and connection before sending sensitive information. The actual suppliers and
          regions enabled for a hosted deployment are listed only when confirmed by its operator;
          see the{" "}
          <a className="underline" href="/legal/subprocessors">
            external services page
          </a>
          .
        </p>
        <p>
          Before the public contact form accepts a message, it sends a one-time verification code to
          the reply email address you enter. The code and contact message are handled by the email
          service configured for the site using SMTP with TLS. The recipient address is kept in
          backend configuration and is not returned to the browser or displayed on the site. After
          verification, your name, reply email, subject, and message are sent to that recipient;
          your reply address is set as Reply-To so the site operator can answer you. Direct email
          sent to the published contact address may also be processed by Resend and forwarded to the
          operator&apos;s private inbox through a signed webhook. AverQel does not save verification
          codes or contact message contents in its application database or application logs. Short-
          lived verification fingerprints and rate-limit counters are held in Redis. Email is not
          end-to-end encrypted: the email provider and receiving mailbox handle these messages and
          may retain them under their own terms and settings. The operator controls retention in the
          receiving mailbox.
        </p>
      </PolicySection>

      <PolicySection title="Legal basis">
        <p>
          AverQel is developed by a solo developer and is not a separate registered company. If the
          developer operates a hosted instance, the operator is that individual. This source does
          not establish the legal basis relied on for each processing purpose and jurisdiction. The
          hosted operator must identify themselves and publish the applicable basis where required;
          this code page cannot decide it on their behalf.
        </p>
      </PolicySection>

      <PolicySection title="Who can access content">
        <p>
          Workspace content is not routinely displayed in the platform administrator user view.
          That view contains account email, tenant, status, roles, multi-factor status, account
          creation time, and last completed sign-in time. Support and feedback are separate
          user-submitted conversations for which the operator provides a support response.
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            Support text and attachments are encrypted in the browser for the submitting account and
            the platform support administrator. The user can read their own conversation; the
            allowlisted platform administrator can decrypt it in Support Management to respond.
            Internal notes are encrypted only for the administrator. This does not expose the
            user&apos;s chats, documents, or other private workspace content.
          </li>
          <li>
            Feedback text is encrypted in the browser for the submitting account and the platform
            administrator. Both can read the conversation and the administrator can respond. The
            feedback queue omits submitter email and account ID. Legacy staff roles do not grant
            cross-workspace access.
          </li>
          <li>
            Qel Connect moderators can open reported content only within their assigned workspace;
            report details load when a report is opened.
          </li>
        </ul>
        <p>
          Platform-wide access requires the configured platform-admin allowlist. Qel Connect
          moderation remains separately role-gated and tenant-scoped. Privileged reads and
          administrative changes produce audit events. Audit events record administrative
          identifiers and actions, not the full support, feedback, or report text.
        </p>
        <p>
          The platform administrator can view a global account-security history containing account
          creation and provider email verification, completed sign-ins and MFA results, failed
          sign-ins and lockouts, password changes, session revocation, and administrator account
          actions. It contains event times, account or actor identifiers, authentication method,
          outcome, and bounded reason codes. It excludes IP addresses, device details, prompts,
          documents, chats, and query contents. Security events are retained for 90 days by default.
          Platform-administrator routes require an allowlisted account with authenticator-based MFA
          enabled and completed for the current session.
        </p>
        <p>
          Your account security settings list your own active sign-in sessions, including a device
          label and the browser&apos;s user-agent string, so you can recognize and revoke sessions.
          These details are not included in the platform-wide security history. AverQel keeps an
          active session record while that session remains valid; after revocation, it is retained
          for up to 90 days by default and then removed. The sign-in session flow does not store an
          IP address.
        </p>
      </PolicySection>

      <PolicySection title="Storage, security, and encryption">
        <p>
          The server stores structured records and uploaded objects and applies tenant, ownership,
          and role checks to protected requests. Provider credentials are handled by backend
          services and protected at rest where deployment encryption keys are configured. Protecting
          the deployment, keys, backups, logs, and network access also depends on its operator.
        </p>
        <p>
          New support and feedback text, replies, and support attachments are encrypted in the
          browser with AES-GCM; their content keys are wrapped for the submitting account and the
          platform administrator. Private keys are stored only as passphrase-encrypted backups, and
          the passphrase is not sent to the server. A database or object-storage copy alone should
          therefore contain ciphertext for migrated records. The service still sees account IDs,
          email needed for support, categories, status, timestamps, attachment sizes, and routing
          metadata. The platform administrator can decrypt support and feedback by design. Losing
          an encryption passphrase can make that account&apos;s messages unreadable.
        </p>
        <p>
          Older records remain plaintext until the platform administrator runs the browser-based
          migration in Support Management and Feedback Management. Previous backups may retain
          plaintext until those backups expire. Encrypted attachments cannot be scanned by the
          server&apos;s malware scanner. This encryption does not protect against a compromised user
          device, a compromised live server that changes the browser code or keys, or content after
          it is decrypted on screen. AverQel is not end-to-end encrypted as a whole, and this
          application-level design has not been independently cryptographically audited.
        </p>
      </PolicySection>

      <PolicySection title="Retention and your controls">
        <p>
          Retention depends on the record type, your workspace settings, and the deployment. Current
          defaults include 90 days after revocation for authentication sessions and related token
          records, 90 days for audit records, 30 days for selected transient records, 365 days for
          feedback and support records of any status after their last update, 365 days for dismissed
          in-app notifications, and 90 days for delivered or suppressed notification-delivery
          records. Expired support attachment deletion can continue in a background cleanup queue.
        </p>
        <p>
          You can use the in-app privacy controls to export or delete your account and manage
          available content and connection settings. Account deletion removes the account and its
          account-owned live records; records owned by other people in a shared tenant remain.
          Stored-file cleanup can continue in the background. Minimal anonymized security records,
          deployment backups, and copies held by external providers may follow separate retention
          periods. Managed local backup archives are pruned after successful backup-script runs,
          with a 30-day default; this is not an automatic schedule, and remote copies and VPS
          snapshots follow their own settings. A tenant-data purge is a different administrator
          operation and does not delete individual accounts. It retains user accounts, provider
          settings, support and feedback records, and audit records. A second authorized
          administrator can approve it immediately; a single administrator can approve after a
          24-hour hold by default. The requester can cancel before approval.
          See{" "}
          <a className="underline" href="/legal/data-retention">
            Retention &amp; Deletion
          </a>
          .
        </p>
        <p>
          Depending on applicable law, you may have rights to access, correct, export, restrict,
          object to, or delete personal information. Signed-in users can use Support Centre; anyone
          can use the public contact form at the bottom of the landing page to make a request. The
          application applies temporary contact and global request rate limits using the
          visitor&apos;s network address; the dedicated contact limit is stored as a keyed
          fingerprint for up to one hour.
        </p>
      </PolicySection>

      <PolicySection title="Contact and deployment details">
        <p>
          Operator: AverQel Independent Project. The Support Centre requires an account. A postal
          address, production hosting region, and the exact
          providers enabled for a live deployment are not specified in this repository and must be
          confirmed for the hosted service. This page was reviewed 17 October 2026; a review date
          does not mean a deployment has published or adopted this revision.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
