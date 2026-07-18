import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function RoadmapPage() {
  return (
    <DocsShell
      title="Roadmap"
      intro="The practical direction for AverQel after the current DeepSpace hardening work: keep the native architecture strong, improve maintainability, and extend safely."
    >
      <DocsCards
        items={[
          {
            title: "Now: Stable Native Runtime",
            body: "Preserve the current AverQel-native DeepSpace, orchestration, memory, provider, and connector ownership instead of replacing it with an external SDK runtime.",
          },
          {
            title: "Next: MCP Standardization",
            body: "Keep moving connectors toward a more MCP-centric model where dynamic tool discovery reduces hardcoded per-service maintenance.",
          },
          {
            title: "Next: Operator Acceptance",
            body: "Continue browser-level operational audits for research, coding, approval, and proactive mission types so documentation and runtime stay aligned.",
          },
          {
            title: "Later: Team And Platform Layers",
            body: "Shared provider control, richer workspace ownership, and deeper fleet tooling should come only when they solve real product needs.",
          },
        ]}
      />
      <DocsSection title="Not Current Scope">
        <p>
          A risky rewrite of the current runtime is not the goal. The path is additive hardening,
          better docs, safer observability, stronger runtime contracts, and maintainable connector
          evolution.
        </p>
        <p>
          The immediate focus remains stability, streaming clarity, connector control, local/cloud
          provider flexibility, and agent execution parity across the main DeepSpace workflow.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
