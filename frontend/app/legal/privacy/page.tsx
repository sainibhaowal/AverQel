import PolicyLayout from "@/app/components/legal/PolicyLayout";
import PolicySection from "@/app/components/legal/PolicySection";

export default function PrivacyPage() {
  return (
    <PolicyLayout
      eyebrow="Privacy Policy"
      title="How AverQel protects your account and codebase data."
      intro="AverQel is a fully online AI agent platform. Your codebase data, notes, and chats are processed and stored securely in PostgreSQL database environments hosted on our central cloud servers."
    >
      <PolicySection title="What AverQel collects on the Cloud VPS">
        <p>
          We store your account credentials, billing receipts, LLM settings, documents, memories,
          and chat message history securely in our PostgreSQL database.
        </p>
        <p>
          All your developer content, files, prompts, and memory indexes are stored in isolated,
          secure schemas with tenant-level boundary protection.
        </p>
      </PolicySection>

      <PolicySection title="Security & Multi-Tenant Isolation">
        <p>
          Your workspace directories, notes, and active agent execution histories are protected by
          strict security boundaries. Cross-tenant access controls ensure that your data is isolated
          from other users.
        </p>
      </PolicySection>

      <PolicySection title="Authentication and Secret Storage">
        <p>
          Your third-party API credentials and LLM secrets are securely stored on our servers using
          high-strength AES-GCM encryption.
        </p>
      </PolicySection>

      <PolicySection title="Data Retention and Deletion">
        <p>
          You can delete your conversations and files at any time through the workspace settings.
          Deleting your account permanently deletes all associated data from our cloud servers.
        </p>
      </PolicySection>
    </PolicyLayout>
  );
}
