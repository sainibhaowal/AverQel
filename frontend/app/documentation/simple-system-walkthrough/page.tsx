import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function SimpleSystemWalkthroughPage() {
  return (
    <DocsShell
      title="Simple System Walkthrough"
      intro="A plain-language explanation of how AverQel handles one user request."
    >
      <DocsSection title="How it works">
        <ol className="list-decimal space-y-3 pl-6">
          <li>You type a request into chat or DeepSpace.</li>
          <li>The backend validates your tenant, account, conversation, and provider scope.</li>
          <li>
            DeepSpace answers through the shared grounded chat service and can use notes, memory,
            and document context.
          </li>
          <li>The answer streams into the conversation and is saved to history.</li>
          <li>
            The answer streams into the conversation and can be inserted into the note editor.
          </li>
        </ol>
      </DocsSection>

      <DocsSection title="The short version">
        <p>
          Chat is the product surface. Memory, documents, providers, and MCP integrations are
          separate capabilities that the chat can use when the request requires them.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
