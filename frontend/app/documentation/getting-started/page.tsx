import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function GettingStartedPage() {
  return (
    <DocsShell
      title="Getting Started"
      intro="Start with providers and documents, then use grounded chat, DeepSpace, memory, and MCP integrations when needed."
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
            body: "Use the protected MCP surface for authorized remote tools and integrations.",
          },
          {
            title: "5. Use DeepSpace",
            body: "Use DeepSpace for research, drafting, analysis, and other productivity work in one conversation.",
          },
          {
            title: "6. Save Useful Context",
            body: "Turn outputs into notes, exports, and persistent memory facts without leaving the app.",
          },
        ]}
      />
      <DocsSection title="Provider Setup">
        <p>
          Today, users can add personal providers from Settings &gt; Providers. Personal provider
          keys are encrypted and private to the owning account. AverQel can route requests to the
          best available provider for chat, reasoning, or web search.
        </p>
      </DocsSection>
      <DocsSection title="Productivity Chat">
        <p>
          DeepSpace is a productivity chat surface for research, drafting, analysis, notes, memory,
          and durable conversation history. It is not an IDE or background orchestration console.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
