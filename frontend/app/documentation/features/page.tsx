import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function FeaturesPage() {
  return (
    <DocsShell
      title="Platform Features"
      intro="AverQel combines grounded retrieval, agentic execution, rich editing, provider routing, connector automation, mission orchestration, and durable memory into one product surface."
    >
      <DocsCards
        items={[
          {
            title: "Grounded Retrieval",
            body: "Documents are parsed, chunked, embedded, indexed, and retrieved so answers can stay tied to private source material instead of only freeform generation.",
          },
          {
            title: "DeepSpace Command Surface",
            body: "Every new DeepSpace chat automatically uses the durable runtime: it plans, calls tools, checkpoints progress, asks for approval, survives restarts, compacts long sessions, verifies results, repairs failures, and reconstructs the final answer.",
          },
          {
            title: "Mission Orchestration",
            body: "Complex requests can become multi-lane missions with planning, dependencies, subagents, approvals, memory updates, connector handoffs, and proactive follow-up.",
          },
          {
            title: "Editor + File Workspace",
            body: "The in-app workspace supports notes, markdown import, math blocks, exports, split layouts, and file-aware save flows for agent-assisted work.",
          },
          {
            title: "Connector + MCP Readiness",
            body: "GitHub, Drive, Gmail, Calendar, Slack, Notion, and crawler-style sources already work through connectors, while MCP runtime foundations support more standardized tool discovery over time.",
          },
          {
            title: "Provider Flexibility",
            body: "AverQel can route work across cloud and local runtimes including OpenRouter, OpenAI-compatible providers, Anthropic, Google, Ollama, LM Studio, rerankers, and web search providers.",
          },
          {
            title: "Safety + Tenant Isolation",
            body: "Approval gates, runtime policy, secret encryption, RBAC, tenant scoping, PostgreSQL event integrity, idempotency, budgets, dead-letter recovery, and metadata-first admin controls keep the powerful runtime bounded and auditable.",
          },
        ]}
      />
      <DocsSection title="The product is broader than one chat feature">
        <p>AverQel now spans multiple connected surfaces:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>documents and grounded query</li>
          <li>DeepSpace chat and agentic execution</li>
          <li>the working note/file editor</li>
          <li>memory and task continuity</li>
          <li>connector control and sync</li>
          <li>orchestration and operator visibility</li>
          <li>provider and runtime management</li>
        </ul>
      </DocsSection>

      <DocsSection title="What makes the current build different">
        <p>
          The current product is not only “chat over documents.” It is a system that can retrieve
          evidence, plan work, run tools, coordinate multiple lanes, persist memory, work with live
          connectors, and render the full journey back to the user.
        </p>
        <p>The recent DeepSpace phases added:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>structured planner validation</li>
          <li>runtime hook and policy layers</li>
          <li>subagent specialization</li>
          <li>tool context and runtime preferences</li>
          <li>compaction visibility and long-session stability</li>
          <li>operator diagnostics and orchestration canvas introspection</li>
          <li>durable-first chat with PostgreSQL checkpoints and event replay</li>
          <li>reconnectable SSE/WebSocket streaming and full thread rehydration</li>
          <li>planner, critic, verifier, repair, memory, compaction, and dead-letter controls</li>
        </ul>
      </DocsSection>

      <DocsSection title="Rich rendering is part of the product, not decoration">
        <p>
          AverQel supports advanced markdown, Mermaid diagrams, and line/bar/pie/area/scatter charts
          inline in both chat and documentation. The runtime keeps these blocks streaming-safe so
          live output stays readable while content is still arriving.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
