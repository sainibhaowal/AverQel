import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ArchitectureDocsPage() {
  return (
    <DocsShell
      title="Architecture"
      intro="A high-level developer map of how AverQel fits together across frontend surfaces, backend services, document retrieval, DeepSpace runtime, orchestration, connectors, providers, and memory."
    >
      <DocsCards
        items={[
          {
            title: "Frontend surfaces",
            body: "Dashboard pages, query UI, DeepSpace, orchestration, connectors, settings, and the documentation center all render different views over shared runtime state.",
          },
          {
            title: "Backend runtime",
            body: "Backend services handle retrieval, answer generation, DeepSpace chat, tool execution, mission orchestration, memory, proactive work, connectors, and provider routing.",
          },
          {
            title: "Persistence",
            body: "PostgreSQL persists chat history, durable runs, graph nodes, ordered events, checkpoints, approvals, leases, memory context, dead letters, message versions, provider configs, and connector state.",
          },
          {
            title: "Streaming contract",
            body: "Stable DeepSpace SSE events remain compatible while durable SSE and WebSocket cursors reconnect from PostgreSQL sequence numbers and rebuild the visible timeline.",
          },
        ]}
      />

      <DocsSection title="Main product layers">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Document intelligence layer:</strong> ingestion, parsing, chunking, embeddings,
            retrieval, and grounded answers.
          </li>
          <li>
            <strong>DeepSpace durable runtime layer:</strong> planner, executor, critic, verifier,
            repair loop, tool execution, approvals, checkpoints, budgets, memory, compaction, and
            streamed step visibility.
          </li>
          <li>
            <strong>Mission orchestration layer:</strong> planner, mission graph, lane scheduling,
            subagents, proactive lanes, memory lanes, connector lanes, and approvals.
          </li>
          <li>
            <strong>Integration layer:</strong> connectors, OAuth flows, MCP runtime foundations,
            and connector documents.
          </li>
          <li>
            <strong>Provider layer:</strong> cloud and local runtime routing for chat, embeddings,
            reranking, web search, and model discovery.
          </li>
          <li>
            <strong>Persistence layer:</strong> PostgreSQL is the durable source of truth for runs,
            events, checkpoints, leases, approvals, final assistant messages, memory context, and
            dead-letter recovery. Redis is cache and live-presence infrastructure.
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="How a typical request moves through the system">
        <ol className="list-decimal space-y-3 pl-6">
          <li>The user starts in query, DeepSpace, documents, connectors, or notes.</li>
          <li>
            The backend loads tenant/user scope, settings, preferences, history, and relevant
            context.
          </li>
          <li>
            New DeepSpace chat requests enter the durable runtime automatically; grounded retrieval,
            tools, memory, connectors, and the mission graph become bounded runtime steps.
          </li>
          <li>Providers, tools, connectors, and memory are consulted as needed.</li>
          <li>
            Results stream back into the frontend through stable event contracts and reducer
            materialization.
          </li>
          <li>
            Durable artifacts such as messages, notes, tasks, memory facts, or mission state are
            persisted for later use.
          </li>
        </ol>
      </DocsSection>

      <DocsSection title="What recent DeepSpace phases changed architecturally">
        <ul className="list-disc space-y-2 pl-6">
          <li>planner validation and structured lane normalization became explicit</li>
          <li>runtime hooks and policy surfaces became first-class</li>
          <li>subagent specialization became more structured</li>
          <li>tool context and runtime preferences became clearer and safer</li>
          <li>long-session compaction became durable and visible</li>
          <li>durable chat became the canonical new-message execution path</li>
          <li>restart-safe assistant persistence, cursor streaming, rehydration, and replay were added</li>
          <li>token, cost, tool, time, concurrency, side-effect, and risk budgets became enforceable</li>
          <li>
            observability surfaces became much richer without breaking the existing stream contract
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="Why this architecture documentation matters">
        <p>
          AverQel has grown beyond a small document assistant. The system now has enough moving
          parts that architecture clarity directly affects maintenance cost, onboarding speed, and
          future change safety. This page exists to keep contributors oriented without forcing them
          to reconstruct the whole platform from code search alone.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
