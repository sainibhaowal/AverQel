import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function TermsPage() {
  return (
    <PolicyLayout
      eyebrow="Terms Of Service"
      title="The operating rules for the AverQel independent project."
      intro="Effective 15 August 2026. AverQel is an independently operated software project. By using it, you agree to use the service lawfully, protect your account, and understand the limits of AI-assisted output and connected services."
    >
      <PolicySection title="Account responsibility">
        <p>
          You are responsible for the credentials, devices, provider accounts, files, prompts, and
          instructions used with your account. Enable available account security controls and do not
          share credentials or authorization links.
        </p>
      </PolicySection>

      <PolicySection title="Acceptable use">
        <p>
          You must not use AverQel for unlawful activity, malware, credential theft, unauthorized
          access, privacy invasion, unlawful surveillance, harassment, abusive automation, malicious
          uploads, attempts to bypass access controls, or activity that harms the service or another
          user.
        </p>
      </PolicySection>

      <PolicySection title="User content and AI output">
        <p>
          You retain rights in content you submit, subject to rights belonging to other people. You
          grant AverQel the limited permission needed to store, transform, retrieve, transmit, and
          display that content to operate the features you request. You are responsible for having
          the right to upload, share, and process it.
        </p>
        <p>
          AI output, search results, extracted text, citations, and connected-service results may be
          incomplete or incorrect. Review outputs before relying on them, especially for legal,
          medical, financial, security, or other high-impact decisions.
        </p>
      </PolicySection>

      <PolicySection title="Connected services and availability">
        <p>
          AI providers, web services, and MCP-connected apps are separate services. Their
          availability, limits, policies, and processing are outside AverQel&apos;s control. You
          authorize an external action only when you enable the connection and satisfy the
          applicable policy or approval requirement.
        </p>
      </PolicySection>

      <PolicySection title="Suspension, deletion, and changes">
        <p>
          AverQel may restrict or suspend access when needed to respond to abuse, security risk,
          legal requirements, or a serious service-impacting issue. You may stop using the service
          and use available account deletion controls. Deletion may require asynchronous cleanup and
          may not immediately remove encrypted backups, security records, or legally required data.
        </p>
        <p>
          Features, infrastructure, and these terms may change. Material changes will be announced
          through the product or website when reasonably practicable. The Support Centre is the
          current contact route for questions about these terms.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
