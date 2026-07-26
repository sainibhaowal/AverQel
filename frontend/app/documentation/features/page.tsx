import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function FeaturesPage() {
  return (
    <DocsShell
      title="Platform Features"
      intro="AverQel combines grounded retrieval, productivity chat, rich editing, provider routing, protected integrations, and persistent memory."
    >
      <DocsCards
        items={[
          {
            title: "Grounded Retrieval",
            body: "Documents are parsed, indexed, and retrieved so answers can stay tied to private source material.",
          },
          {
            title: "DeepSpace Chat",
            body: "DeepSpace supports research, drafting, analysis, streaming answers, notes, memory, and durable history in one conversation.",
          },
          {
            title: "Notes + Deliverables",
            body: "The workspace supports notes, Markdown, diagrams, math blocks, and exports.",
          },
          {
            title: "Connectors + MCP",
            body: "Authorized integrations remain isolated behind encrypted credentials, catalog checks, policy, and approval controls.",
          },
          {
            title: "Provider Flexibility",
            body: "AverQel can use cloud or local providers for chat, embeddings, reranking, and web search.",
          },
          {
            title: "Safety + Tenant Isolation",
            body: "Authentication, encrypted secrets, RBAC, tenant scoping, and approval gates remain backend responsibilities.",
          },
        ]}
      />

      <DocsSection title="The product surface">
        <ul className="list-disc space-y-2 pl-6">
          <li>documents and grounded query</li>
          <li>DeepSpace productivity chat, notes, and memory</li>
          <li>notes, diagrams, and exports</li>
          <li>persistent memory and conversation history</li>
          <li>connectors, MCP, and provider management</li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
