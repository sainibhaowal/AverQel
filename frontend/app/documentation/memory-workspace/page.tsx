import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function MemoryWorkspaceDocsPage() {
  return (
    <DocsShell
      title="DeepSpace memory"
      intro="DeepSpace includes controls for saved memory associated with your account and conversations. Use them to inspect and manage stored context; memory behavior can depend on deployment and model configuration."
    >
      <DocsCards
        items={[
          {
            title: "Memory Facts",
            body: "Saved memory can make selected account context available in later DeepSpace work, subject to its scope and current settings.",
          },
          {
            title: "Conversation History",
            body: "Conversation history and saved memory are separate product concepts. Memory controls apply to saved context, not as a replacement for reviewing a conversation transcript.",
          },
          {
            title: "Search",
            body: "Use the available memory controls to find and review stored items.",
          },
          {
            title: "MCP Separation",
            body: "MCP connections are managed separately under Providers & Connections and use their own authorization and tool policies.",
          },
        ]}
      />

      <DocsSection title="Memory scopes">
        <p>
          DeepSpace conversations and saved memory have different lifecycles. Check the labels and
          controls in the memory workspace to understand what is saved and what can be changed.
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>some context is conversation-scoped rather than a durable account memory</li>
          <li>
            saved items can be reviewed and managed with the controls currently available in
            DeepSpace
          </li>
          <li>memory access is subject to the authenticated account and backend authorization</li>
        </ul>
      </DocsSection>

      <DocsSection title="What users notice">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Depending on the enabled controls, review, search, edit, approve, reject, or clear saved
            memory.
          </li>
          <li>
            Use conversation history to review what was said; do not assume a summary or saved
            memory contains the full exchange.
          </li>
          <li>Review memory before relying on a future answer that may use it as context.</li>
          <li>
            Deletion or clearing behavior follows the confirmation and retention policy shown by the
            current deployment.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Automatic capture and review">
        <p>
          Automatic capture is off by default. If you turn it on, the Review inferred setting
          controls whether inferred memories stay pending for your approval or can become active
          without a separate approval. Use memory in chat is a separate setting: turning it off
          prevents active saved memories from being recalled in answers, but does not delete them.
        </p>
      </DocsSection>
      <DocsSection title="Privacy and reliability">
        <p>
          The sensitive-content check is limited and may not detect every sensitive detail. Avoid
          asking the system to save credentials or highly sensitive personal data.
          Account export, retention, and deletion behavior is described separately under Trust &amp;
          Privacy and depends on the current deployment policy.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
