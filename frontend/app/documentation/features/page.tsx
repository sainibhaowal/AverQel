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
            body: "DeepSpace supports research, drafting, analysis, streaming answers, notes, memory, durable history, and model-aware reasoning controls in one conversation.",
          },
          {
            title: "Notes + Deliverables",
            body: "The workspace supports notes, Markdown, diagrams, math blocks, and exports. Mermaid source can be copied or exported as Mermaid, SVG, PNG, or PDF; tables export as CSV or Excel.",
          },
          {
            title: "Sandboxed Analysis",
            body: "Authorized Library files can be analyzed with bounded Python or read-only SQL in an isolated executor; temporary data is cleaned up after each run.",
          },
          {
            title: "Artifacts + Schedules",
            body: "DeepSpace can persist private charts, tables, diagrams, and documents, while user-owned schedules keep recurring work auditable and cancellable.",
          },
          {
            title: "Connectors + MCP",
            body: "Authorized integrations remain isolated behind encrypted credentials, catalog checks, policy, and approval controls.",
          },
          {
            title: "Provider Flexibility",
            body: "AverQel can use cloud or local providers for chat, embeddings, reranking, and web search. Supported models expose appropriate Thinking levels and an estimated context budget.",
          },
          {
            title: "Voice Mode",
            body: "With permission, voice dictation transcribes speech into the composer and TTS reads the completed assistant response through the protected realtime voice service.",
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
          <li>sandboxed data analysis and chart generation</li>
          <li>private artifact previews and authenticated downloads</li>
          <li>scheduled and long-running work with durable run history</li>
          <li>persistent memory and conversation history</li>
          <li>model-aware reasoning controls, context diagnostics, and optional voice input/output</li>
          <li>connectors, MCP, and provider management</li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
