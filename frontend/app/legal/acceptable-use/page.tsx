import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function AcceptableUsePage() {
  return (
    <PolicyLayout
      eyebrow="Acceptable Use"
      title="Acceptable Use Policy"
      intro="AverQel should be used for legitimate document search, analysis, and productivity work. This page sets the baseline rules for abuse, misuse, and unsafe activity."
    >
      <PolicySection title="Allowed use">
        <p>
          Use AverQel for your own lawful documents, research, private analysis, and approved
          collection sharing.
        </p>
      </PolicySection>
      <PolicySection title="Not allowed">
        <p>
          Do not use AverQel for malware, credential theft, privacy invasion, unlawful surveillance,
          harassment, or uploading content you do not have the right to use.
        </p>
      </PolicySection>
      <PolicySection title="Enforcement">
        <p>
          Accounts may be suspended or terminated when activity presents abuse, security, or legal
          risk to the service or other users.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
