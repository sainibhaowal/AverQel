import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function PrivacyPage() {
  return (
    <PolicyLayout
      eyebrow="Privacy Policy"
      title="How AverQel processes your information"
      intro="Last reviewed 17 October 2026. This notice describes the hosted AverQel application and the access controls present in this source version. The service operator, live hosting region, and enabled external providers depend on the deployment."
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
          default administrator user view.
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
          Workspace content is not routinely displayed in the platform administrator user view. That
          view is limited to account email, status, roles, and multi-factor status. Workspace
          administration shows workspace status and seats; analytics are aggregated and use a
          minimum group threshold.
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            Explicitly assigned Support Managers can read support tickets, replies, internal notes,
            and attachments across workspaces. This content is not end-to-end encrypted.
          </li>
          <li>
            Explicitly assigned Feedback Managers can read submitted feedback text across workspaces
            and reply to it. Their staff response omits submitter email and account ID.
          </li>
          <li>
            Qel Connect moderators can open reported content only within their assigned workspace;
            report details load when a report is opened.
          </li>
        </ul>
        <p>
          These staff roles are assigned separately from ordinary platform administration. Support
          access also requires the configured platform-admin allowlist. Privileged reads and
          administrative changes produce audit events. Audit events record administrative
          identifiers and actions, not the full support, feedback, or report text.
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
          AverQel is not end-to-end encrypted as a whole. Qel Connect has limited client-side
          encryption features, but the server processes documents and other product data to provide
          the requested functions. Do not treat the service as a place where administrators or
          configured providers can never access submitted content.
        </p>
      </PolicySection>

      <PolicySection title="Retention and your controls">
        <p>
          Retention depends on the record type, your workspace settings, and the deployment. Current
          defaults include 90 days after revocation for authentication sessions and related token
          records, 90 days for audit records, 30 days for selected transient records, 365 days for
          dismissed in-app notifications, and 90 days for delivered or suppressed
          notification-delivery records. Active content is retained until it is deleted or an
          applicable workspace retention rule processes it. File deletion can continue in a
          background cleanup queue after an account is deleted.
        </p>
        <p>
          You can use the in-app privacy controls to export or delete your account and manage
          available content and connection settings. Account deletion removes the account and
          account-owned records; pending storage cleanup, security records, and deployment backup
          lifecycle can delay complete removal. A workspace purge is a separate administrator
          operation that requires approval from a second, different authorized administrator. It
          retains user accounts, provider settings, support and feedback records, and audit records.
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
          Operator: Ravinder Singh — Independent Developer, AverQel Independent Project. The Support
          Centre requires an account. A postal address, production hosting region, and the exact
          providers enabled for a live deployment are not specified in this repository and must be
          confirmed for the hosted service. This page was reviewed 17 October 2026; a review date
          does not mean a deployment has published or adopted this revision.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
