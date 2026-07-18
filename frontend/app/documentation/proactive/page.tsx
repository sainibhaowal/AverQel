import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ProactiveDocsPage() {
  return (
    <DocsShell
      title="Proactive Agents"
      intro="AverQel's Proactive system runs background autonomous operations. It acts on system events, analyzes workspace changes, and performs scheduled tasks without waiting for a direct user query."
    >
      <DocsCards
        items={[
          {
            title: "Background Automation",
            body: "Autonomous tasks like document index compaction, model health checks, and routine connectors sync run silently in the background.",
          },
          {
            title: "Approval Gates",
            body: "Any write operation, script execution, or third-party API dispatch requires explicit operator authority before execution.",
          },
          {
            title: "Event-Driven Triggers",
            body: "Monitors changes across connect archives, workspaces, and system channels to kickstart indexing and suggest context optimizations.",
          },
          {
            title: "Lane Scheduling",
            body: "Dynamically distributes execution loads across background lanes, ensuring zero latency interference with real-time E2EE messaging.",
          },
        ]}
      />

      <DocsSection title="Autonomous Background Loops">
        <p>
          AverQel is not just a reactive query shell; it features a dedicated background worker system running tasks proactively. When files are added or connectors sync new documents, the Proactive engine triggers semantic segmentation, creates embeddings, and updates the index automatically.
        </p>
      </DocsSection>

      <DocsSection title="Security & Authority Gating">
        <p>
          Because proactive agents can propose workspace changes, AverQel operates under a strict **Zero-Trust Delegation model**. The agent can propose changes, but it is gated by policies. Write permissions, connectors dispatching, and system adjustments require the operator to approve the execution lane in the Control Room.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
