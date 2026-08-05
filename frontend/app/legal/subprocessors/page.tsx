import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function SubprocessorsPage() {
  return (
    <PolicyLayout
      eyebrow="Subprocessors"
      title="Subprocessors and Infrastructure"
      intro="AverQel utilizes secure cloud infrastructure to host services and databases. This page details our subprocessors."
    >
      <PolicySection title="Cloud Infrastructure">
        <p>
          Our remote cloud VPS server hosts your account, workspaces, documents, and chat records.
          The VPS and database infrastructure is provided by:
        </p>
        <ul className="mt-2 list-disc space-y-2 pl-5">
          <li>
            <strong>DigitalOcean / Hetzner:</strong> High-performance VPS cloud servers and
            databases used to host the app and run the orchestrator.
          </li>
          <li>
            <strong>Stripe:</strong> Payment processing and subscription receipts.
          </li>
        </ul>
      </PolicySection>
    </PolicyLayout>
  );
}
