import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function PrivacyPage() {
  return (
    <PolicyLayout
      eyebrow="Privacy Policy"
      title="How the independently operated AverQel project handles your data."
      intro="Effective 15 August 2026. AverQel is an independently operated software project, not a separate incorporated company. This policy describes the data processed to provide the service and the controls currently implemented in the product."
    >
      <PolicySection title="Information processed">
        <p>
          AverQel processes account and authentication data, workspace and tenant identifiers,
          provider settings, conversations, messages, memories, uploaded documents, Library files,
          collection membership, approvals, usage and operational records, and security events.
        </p>
        <p>
          If you configure an AI provider, web-search provider, or MCP connection, the information
          required for that request may be sent to that provider. The provider&apos;s own terms and
          privacy policy apply to its processing. AverQel does not receive a provider password from
          OAuth login; it receives the authorization result and stores protected token material.
        </p>
      </PolicySection>

      <PolicySection title="Why information is processed">
        <p>
          We process information to authenticate users, provide chat and document features, route
          authorized provider requests, run collections and Library workflows, maintain durable
          conversation state, prevent abuse, operate the service, and respond to support or legal
          requests.
        </p>
      </PolicySection>

      <PolicySection title="Storage and access boundaries">
        <p>
          The current deployment uses PostgreSQL for structured records, Redis for runtime
          coordination, and MinIO-compatible object storage for documents and media. Records carry
          tenant, user, workspace, conversation, collection, and ownership boundaries where
          applicable. Authorization is checked before protected reads and writes.
        </p>
        <p>
          Provider and OAuth secrets are encrypted before storage and are not displayed as raw
          values in ordinary product views. Collection messages and media may use the
          collection&apos;s client-side encryption flow. This does not mean every AverQel record or
          every provider request is end-to-end encrypted.
        </p>
      </PolicySection>

      <PolicySection title="Your choices and rights">
        <p>
          You can manage connected providers, memories, conversations, Library files, collections,
          and account settings through the product where those controls are available. Depending on
          your location, you may also have rights to access, correct, export, restrict, object to,
          or delete personal information. Contact the AverQel operator through the Support Centre
          linked in the application to make a request.
        </p>
      </PolicySection>

      <PolicySection title="Changes and contact">
        <p>
          This policy may change when the service, providers, or legal requirements change. The
          effective date above will be updated when a revised version is published. AverQel is an
          independent project; the Support Centre is the current contact route for privacy and
          security questions.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
