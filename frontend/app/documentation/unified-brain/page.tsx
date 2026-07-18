import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function UnifiedBrainDocsPage() {
  return (
    <DocsShell
      title="Unified Brain Checklist"
      intro="The developer-facing checklist and contract map for how AverQel stays coherent across DeepSpace, orchestration, subagents, memory, connectors, providers, approvals, and UI state."
    >
      <DocsSection title="Checklist: What must stay true">
        <ul className="list-disc space-y-2 pl-6">
          <li>AverQel is the visible command surface.</li>
          <li>The master orchestrator decides the mission structure.</li>
          <li>The agent executor still handles the inline reasoning and tool loop.</li>
          <li>The tool executor still runs the actual tools.</li>
          <li>
            Subagents, proactive work, connectors, support sweeps, memory, and approvals remain
            connected.
          </li>
          <li>
            Proactive, connector, and support workers now route through the master orchestrator.
          </li>
          <li>
            Operators can inspect fleet summary endpoints for connectors, subagents, and memory
            evaluation or lifecycle previews without affecting live execution.
          </li>
          <li>Auto-review and Full Access are the same global execution policy everywhere.</li>
          <li>
            The mission planner can come from the model or from policy JSON, then gets normalized.
          </li>
          <li>Execution mode is durable in the database and cached in Redis for runtime reads.</li>
          <li>Nothing should bypass tenant isolation or security gates.</li>
        </ul>
      </DocsSection>

      <DocsCards
        items={[
          {
            title: "AverQel entrypoint",
            body: "User input lands in the chat UI, goes through the DeepSpace backend, and now enters the global orchestration brain before any work is dispatched.",
          },
          {
            title: "Inline tool loop",
            body: "The agent still plans, calls tools, observes results, and streams deltas exactly as before. The orchestration layer sits above it, not inside the tools.",
          },
          {
            title: "Mission graph",
            body: "The master orchestrator can fan a request into research, analysis, writer, executor, memory, proactive, connector, and approval lanes.",
          },
          {
            title: "Approval and safety",
            body: "Risky work pauses for approval. Approved lanes resume through the orchestration approval endpoint. Nothing destructive runs silently.",
          },
        ]}
      />

      <DocsSection title="Human walkthrough: step by step">
        <ol className="list-decimal space-y-3 pl-6">
          <li>
            You type a request into AverQel or DeepSpace. That is the front door of the system.
          </li>
          <li>
            The backend loads your tenant, your conversation, your execution mode, and your stored
            conversation history.
          </li>
          <li>
            The request is handed to the master orchestrator, which decides whether this is a simple
            chat turn, a parallel mission, a proactive follow-up, or a connector-related task.
          </li>
          <li>
            The orchestrator launches lanes. The main chat lane still uses the normal agent loop,
            while other lanes can spawn subagents, store memory, run proactive work, execute
            connector syncs, or run support checks for vitals and daemon health.
          </li>
          <li>
            The agent executor streams its normal events: plan, tool start, tool delta, tool result,
            observing, approval, answer delta, and done.
          </li>
          <li>
            The UI shows the live state. AverQel shows the conversation. The orchestration page
            shows the mission graph, active missions, approval state, tasks, connector health, and
            support-sweep state.
          </li>
          <li>
            If an action needs approval, the user approves or declines it. The mission registry is
            updated, and the live mission stream continues or ends safely.
          </li>
          <li>
            When work is done, results are saved into durable memory, tasks, or mission history so
            the system can continue later without losing context.
          </li>
        </ol>
      </DocsSection>

      <DocsSection title="Developer clarity: core native contracts">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>mission runtime state</strong> carries planner mode, validation status, hook
            state, subagent profile, workspace mode, and mission diagnostics
          </li>
          <li>
            <strong>lane metadata</strong> carries requested and resolved subagent type, delegation
            rationale, lifecycle summaries, tool density, and diagnostics
          </li>
          <li>
            <strong>conversation compaction state</strong> carries trigger, timestamps, before/after
            token counts, and summarized-history metadata
          </li>
          <li>
            <strong>runtime preferences</strong> control planner mode, subagent profile preference,
            hook enablement, workspace mode, and execution mode
          </li>
          <li>
            <strong>event normalization</strong> protects the frontend reducer contract while
            backend internals continue evolving
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="What phase 3 documentation is doing">
        <p>
          This documentation layer exists so future contributors do not have to reverse-engineer the
          whole platform from code alone. It turns the recent implementation work into maintainable
          product knowledge and reduces the chance of contract drift across backend and frontend.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
