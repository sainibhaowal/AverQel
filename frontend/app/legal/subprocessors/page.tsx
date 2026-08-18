import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function SubprocessorsPage() {
  return (
    <PolicyLayout
      eyebrow="Infrastructure and external services"
      title="Infrastructure and external services"
      intro="This page describes the infrastructure categories currently visible in the AverQel deployment. It is not a claim that every provider below is enabled in every deployment."
    >
      <PolicySection title="Cloud Infrastructure">
        <p>
          The current Docker deployment runs PostgreSQL, Redis, and MinIO-compatible object storage
          as separate service components. The public repository does not identify a single hosting
          vendor, so AverQel does not claim DigitalOcean or Hetzner as a confirmed subprocessor
          here. The active hosting vendor and region must be confirmed for the production deployment
          before publication.
        </p>
        <ul className="mt-2 list-disc space-y-2 pl-5">
          <li>
            <strong>Infrastructure host:</strong> The VPS or cloud provider selected for the active
            AverQel deployment; its identity, region, and current status must be published here.
          </li>
          <li>
            <strong>AI and search providers:</strong> A provider receives request data only when an
            administrator or user configures and authorizes that provider. The applicable provider
            terms and privacy policy govern its processing.
          </li>
        </ul>
        <p>
          MCP-connected services such as Google or GitHub may receive data for a user-authorized
          tool call. Access is limited by connection scope, tool policy, and approval state. Before
          commercial launch, publish the legal names, purposes, regions, and change-notice process
          for each actual infrastructure and external service provider.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
