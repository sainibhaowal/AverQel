import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function AcceptableUsePage() {
  return (
    <PolicyLayout
      eyebrow="Acceptable Use"
      title="Acceptable Use Policy"
      intro="Effective 15 August 2026. This policy sets the baseline rules for lawful document, research, productivity, and collaboration use of the independently operated AverQel project."
    >
      <PolicySection title="Allowed use">
        <p>
          Use AverQel for lawful documents, research, analysis, drafting, private work, and
          collection sharing where you have the necessary rights and permissions.
        </p>
      </PolicySection>
      <PolicySection title="Not allowed">
        <p>
          Do not use AverQel for malware, credential theft, unauthorized access, privacy invasion,
          unlawful surveillance, harassment, deceptive impersonation, abusive automation, or
          uploading, sharing, or processing content you do not have the right to use.
        </p>
      </PolicySection>
      <PolicySection title="Enforcement">
        <p>
          Access may be limited, suspended, or terminated when activity creates abuse, security, or
          legal risk. Where appropriate, AverQel may preserve relevant security records and provide
          a route to contact support.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
