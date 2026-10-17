import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function SubprocessorsPage() {
  return (
    <PolicyLayout
      eyebrow="External services"
      title="Infrastructure and connected providers"
      intro="AverQel deployments can use external services to host data or perform features you enable. This page describes service categories; it is not a verified supplier register for a particular hosted instance."
    >
      <PolicySection title="Service categories">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong>Hosting and storage:</strong> the operator&apos;s selected infrastructure host,
            database, runtime coordination, and object-storage services.
          </li>
          <li>
            <strong>AI and retrieval:</strong> model, embedding, reranking, and web-search providers
            configured for the deployment or selected by an authorized user.
          </li>
          <li>
            <strong>Connected tools:</strong> MCP-connected services receive data required for a
            user-authorized tool call, subject to connection scope and approval settings.
          </li>
          <li>
            <strong>Optional delivery:</strong> SMTP email, push, voice, or other integrations may
            process the information needed for the enabled feature.
          </li>
        </ul>
      </PolicySection>

      <PolicySection title="What this repository can confirm">
        <p>
          The source defines PostgreSQL, Redis, and MinIO-compatible storage components and supports
          configurable external providers. It does not identify the live hosting company, data
          region, enabled supplier names, applicable transfer safeguards, or each provider&apos;s
          current contractual role. Those facts are set outside the source repository and must be
          confirmed for the specific deployment.
        </p>
      </PolicySection>

      <PolicySection title="Before using the hosted service">
        <p>
          The service operator must publish the legal names, purpose, processing location, and
          privacy notice for each supplier used by the hosted instance, and update this page when
          that list changes. The codebase does not contain enough information to present a complete
          production subprocessor list. Do not treat the categories above as a substitute for that
          deployment-specific notice.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
