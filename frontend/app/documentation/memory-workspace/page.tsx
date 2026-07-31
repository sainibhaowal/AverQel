import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function MemoryWorkspaceDocsPage() {
  return (
    <DocsShell
      title="Memory & Workspace"
      intro="DeepSpace keeps tenant-scoped memory available across sessions without requiring an IDE-style filesystem or a second memory manager in Settings."
    >
      <DocsCards
        items={[
          {
            title: "Memory Facts",
            body: "DeepSpace stores user-scoped facts and preferences so future conversations can use relevant context.",
          },
          {
            title: "Conversation History",
            body: "Saved conversations are the complete transcript. Memory never copies the whole chat, and conversations can be reopened after a reload.",
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
        <p>AverQel keeps conversation history, temporary working memory, and durable memory separate so recalled context stays useful and small.</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>session memory is temporary, can be linked to a conversation, and expires automatically</li>
          <li>user memory stores durable user-specific facts and preferences</li>
          <li>memory access remains tenant-scoped and permission-checked</li>
        </ul>
      </DocsSection>

      <DocsSection title="What users notice">
        <ul className="list-disc space-y-2 pl-6">
          <li>saved memories can be searched, edited, exported, and removed from DeepSpace</li>
          <li>DeepSpace can save explicit remember requests and lasting preferences through its memory tools</li>
          <li>optional automatic capture creates small reviewable candidates from clear durable preferences; sensitive information is never auto-saved</li>
          <li>only active, relevant memories are recalled, using a bounded relevance, importance, confidence, and freshness ranking</li>
          <li>answers can identify the memories that were used, and inferred candidates can be approved or discarded</li>
          <li>retention, duplicate cleanup, embedding health, and personal-memory clearing stay in the DeepSpace memory workspace</li>
          <li>chat history survives page reloads</li>
          <li>there is no context meter, task ledger, proactive monitor, or runtime dashboard</li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
