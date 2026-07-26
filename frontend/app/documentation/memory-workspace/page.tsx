import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function MemoryWorkspaceDocsPage() {
  return (
    <DocsShell
      title="Memory & Workspace"
      intro="AverQel keeps persistent user memory and conversation history available across sessions without requiring an IDE-style filesystem or background task system."
    >
      <DocsCards
        items={[
          {
            title: "Memory Facts",
            body: "DeepSpace stores user-scoped facts and preferences so future conversations can use relevant context.",
          },
          {
            title: "Conversation History",
            body: "Saved conversations remain available through the chat history surface and can be reopened after a reload.",
          },
          {
            title: "Search",
            body: "Search memory directly when you need to find a stored preference or project fact.",
          },
          {
            title: "MCP Separation",
            body: "MCP connections and remote tools stay in their own protected runtime and are not mixed into memory storage.",
          },
        ]}
      />

      <DocsSection title="Memory scopes">
        <p>AverQel distinguishes between temporary conversation context and durable user memory.</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>session context supports the current conversation</li>
          <li>user memory stores durable user-specific facts and preferences</li>
          <li>memory access remains tenant-scoped and permission-checked</li>
        </ul>
      </DocsSection>

      <DocsSection title="What users notice">
        <ul className="list-disc space-y-2 pl-6">
          <li>saved memories can be searched and removed</li>
          <li>chat history survives page reloads</li>
          <li>there is no context meter, task ledger, proactive monitor, or runtime dashboard</li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
