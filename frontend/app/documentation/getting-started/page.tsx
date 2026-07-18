import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function GettingStartedPage() {
  return (
    <DocsShell
      title="Getting Started"
      intro="Start with documents, providers, and connectors, then move into grounded chat, DeepSpace missions, note editing, and approval-aware agentic workflows."
    >
      <DocsCards
        items={[
          {
            title: "1. Create Your Account",
            body: "Sign up, keep your login secure, and enable 2FA from profile settings when available.",
          },
          {
            title: "2. Upload Documents",
            body: "Add PDFs, Office files, images, Markdown, or notebooks. AverQel parses, chunks, embeds, indexes, and makes them available to grounded query flows.",
          },
          {
            title: "3. Configure Providers",
            body: "Set up chat, embedding, reranker, or web-search runtimes. AverQel supports both cloud and local routes depending on the runtime you choose.",
          },
          {
            title: "4. Connect Sources",
            body: "Add GitHub, Drive, Gmail, Calendar, Notion, Slack, or crawler sources so DeepSpace missions can work with live context and connector documents.",
          },
          {
            title: "5. Use DeepSpace",
            body: "Use DeepSpace for agentic work, watch the live tool stream, inspect mission canvas diagnostics, and approve risky actions when AverQel asks for authority.",
          },
          {
            title: "6. Work In Notes And Tasks",
            body: "Turn outputs into editable notes, file-aware drafts, exports, memory facts, and proactive follow-up tasks without leaving the app.",
          },
        ]}
      />
      <DocsSection title="Provider Setup">
        <p>
          Today, users can add personal providers from Settings &gt; Providers. Personal provider
          keys are encrypted and private to the owning account. AverQel can route tasks to the best
          available provider for chat, reasoning, web search, or local execution.
        </p>
      </DocsSection>
      <DocsSection title="Agentic Workflows">
        <p>
          DeepSpace can plan, reason, call tools, populate the proactive workspace with recurring
          rules and tasks, and show its mission structure inline. The same tenant-scoped runtime
          keeps working after logout because long-running work stays on the backend and streams
          state back into the UI.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
