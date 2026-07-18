import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function TermsPage() {
  return (
    <PolicyLayout
      eyebrow="Terms Of Service"
      title="The operating rules for using AverQel."
      intro="These terms explain the relationship between AverQel and its users, including acceptable use, service operation, and account controls."
    >
      <PolicySection title="Account Responsibility">
        <p>
          Users are responsible for protecting their account credentials and maintaining their workspaces in a secure manner.
        </p>
      </PolicySection>

      <PolicySection title="Acceptable Use">
        <p>
          AverQel may not be used for unlawful activity, abuse, credential attacks, malicious
          uploads, harassment, or attempts to compromise the service or other users.
        </p>
      </PolicySection>

      <PolicySection title="Content and Service Operation">
        <p>
          Users retain ownership of the codebases, notes, and documents they load into the system.
          AverQel processes and stores this content on secure VPS servers to run agent queries and coordinate workspaces.
        </p>
      </PolicySection>

      <PolicySection title="Changes and Notices">
        <p>
          AverQel may update product features, database architectures, and security controls over time. Material
          changes will be communicated clearly through the app or website.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
