import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function TermsPage() {
  return (
    <PolicyLayout
      eyebrow="Terms Of Service"
      title="AverQel Terms of Service"
      intro="Last reviewed 17 October 2026. AverQel is developed by a solo developer and is not a separate registered company. The individual or entity operating a hosted instance must identify themselves and its deployment-specific providers before public launch."
    >
      <PolicySection title="Your account and security">
        <p>
          Provide accurate account information, protect your sign-in credentials and devices, and
          use available security controls. You are responsible for activity performed through your
          account, subject to rights and protections that apply under local law.
        </p>
      </PolicySection>

      <PolicySection title="Acceptable use">
        <p>
          Use AverQel lawfully and only with content and connections you are authorized to use. Do
          not use it for malware, credential theft, unauthorized access, privacy invasion, unlawful
          surveillance, harassment, deceptive impersonation, abusive automation, malicious uploads,
          or attempts to bypass access controls or harm another person or the service. See the
          <a className="underline" href="/legal/acceptable-use">
            Acceptable Use Policy
          </a>
          .
        </p>
      </PolicySection>

      <PolicySection title="Your content and service processing">
        <p>
          You retain rights in content you submit, subject to rights belonging to others. You permit
          AverQel to store, transform, retrieve, transmit, and display that content as needed to
          provide the features you request, protect the service, and respond to authorized support
          or security work. You are responsible for having the rights and permissions needed to
          submit or share it.
        </p>
        <p>
          Allowlisted platform administrators can read support tickets, attachments, and submitted
          feedback across tenants so they can respond to those requests. Legacy Support Manager and
          Feedback Manager assignments do not grant access to those queues. Qel Connect moderators
          can review reports within their assigned workspace. These
          workflows are described in the{" "}
          <a className="underline" href="/legal/privacy">
            Privacy Policy
          </a>
          .
        </p>
      </PolicySection>

      <PolicySection title="External providers and connected services">
        <p>
          When you configure an AI, search, voice, embedding, reranking, email, or MCP-connected
          service, the information necessary for your selected request may be sent to it. Those
          services have their own terms, privacy practices, availability, and limits. Review their
          terms and the data you choose to send. You authorize external actions only through enabled
          connections and applicable approval controls.
        </p>
      </PolicySection>

      <PolicySection title="AI output and availability">
        <p>
          AI output, search results, extracted text, citations, and connected-service results may be
          incomplete or incorrect. Review them before relying on them, especially for legal,
          medical, financial, safety, or other high-impact decisions. Service availability depends
          on the hosted deployment and external providers.
        </p>
      </PolicySection>

      <PolicySection title="Account controls, suspension, and deletion">
        <p>
          You can stop using the service and use available privacy settings to export or delete your
          account. Account deletion removes account-owned records; object-storage cleanup may
          continue in the background, and security records or deployment backups can follow separate
          retention periods. An administrator workspace purge is a different operation. It requires
          approval from a second, different authorized administrator and does not delete user
          accounts, provider settings, support records, feedback records, or audit records. Read the{" "}
          <a className="underline" href="/legal/data-retention">
            Retention &amp; Deletion notice
          </a>{" "}
          before requesting deletion.
        </p>
        <p>
          Access may be restricted to respond to abuse, security risks, legal requirements, or a
          serious service incident. Where appropriate and permitted, the operator will provide
          notice and a support route.
        </p>
      </PolicySection>

      <PolicySection title="Changes and contact">
        <p>
          Features and these terms may change. Material changes should be announced before they
          apply where required by law. The hosted service is operated by AverQel Independent
          Project. Questions about these terms can be sent through the public Contact the developer
          form on the landing page or the Support Centre for signed-in users. The form requires the
          deployment to configure SMTP delivery.
          Direct mail sent to the contact address is forwarded only when the deployment has
          configured Resend inbound processing. A postal address and deployment-specific providers
          are not specified here and must be confirmed for the hosted service. This page was
          reviewed 17 October 2026; a review date does not mean the hosted service has published,
          adopted, or notified users about this revision.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
