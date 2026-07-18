import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function InsightsPanelDocsPage() {
  return (
    <DocsShell
      title="Insights Panel"
      intro="The DeepSpace insights panel is the runtime sidecar for context usage, compaction, vitals, active tools, subagent monitoring, and live execution confidence."
    >
      <DocsCards
        items={[
          {
            title: "Context Meter",
            body: "Shows used tokens, remaining headroom, context limit source, near-limit warnings, and the latest compaction result.",
          },
          {
            title: "Compact Now",
            body: "Users can trigger compaction manually, while the runtime also auto-compacts when the session gets too close to the limit.",
          },
          {
            title: "Runtime Vitals",
            body: "The panel summarizes internet, LLM, web-search, and proactive daemon posture so the user can tell if the system is healthy.",
          },
          {
            title: "Subagent Monitor",
            body: "Recent and active subagent runs are visible from the panel so users can tell whether delegated work is actually happening.",
          },
        ]}
      />

      <DocsSection title="What appears here">
        <ul className="list-disc space-y-2 pl-6">
          <li>context usage and token counts</li>
          <li>model and provider information</li>
          <li>phase information</li>
          <li>compaction summary and saved tokens</li>
          <li>latency timeline and active tools</li>
          <li>runtime vitals</li>
          <li>active or recent subagent runs</li>
        </ul>
      </DocsSection>

      <DocsSection title="Why this panel matters">
        <p>
          Without this panel, long agentic sessions would feel much more opaque. The insights panel
          gives users and operators a quick read on session health, whether the context window is
          under pressure, whether compaction already happened, and whether subagents are actually
          running or stuck.
        </p>
      </DocsSection>

      <DocsSection title="How it connects to phase 1 and phase 2">
        <ul className="list-disc space-y-2 pl-6">
          <li>Phase 1 made compaction visible and durable.</li>
          <li>
            Phase 2 made runtime posture and observability more meaningful through richer mission
            diagnostics.
          </li>
          <li>
            The insights panel is the fast-glance surface, while the mission canvas is the deeper
            mission-specific inspection surface.
          </li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
