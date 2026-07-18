import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function OrchestrationDocsPage() {
  return (
    <DocsShell
      title="Global Orchestration"
      intro="How AverQel coordinates DeepSpace, the inline agent loop, parallel subagents, proactive follow-up, connector handoffs, approvals, and durable mission state in one federated control plane."
    >
      <DocsSection title="What the orchestration layer does now">
        <p>
          AverQel now has a global mission registry and a live orchestration stream. Instead of
          treating chat, subagents, proactive jobs, and connectors as separate islands, the system
          builds a mission graph, tracks lane state, persists handoffs, and synthesizes the final
          result from all active paths.
        </p>
        <p>
          The control room at <code>/dashboard/orchestration</code> reflects the live plan, active
          subagent swarm, durable memory lane, proactive workspace, connector mesh, mission fleet,
          and runtime status in real time.
        </p>
      </DocsSection>

      <DocsCards
        items={[
          "Mission graph",
          "Dynamic parallel lanes",
          "Durable handoff",
          "Approval-aware execution",
        ].map((title) => {
          if (title === "Mission graph") {
            return {
              title,
              body: "Each mission becomes a structured DAG with dependencies, priorities, approvals, and lane metadata.",
            };
          }
          if (title === "Dynamic parallel lanes") {
            return {
              title,
              body: "AverQel can fan out into research, analysis, writer, executor, memory, proactive, and connector lanes as needed.",
            };
          }
          if (title === "Durable handoff") {
            return {
              title,
              body: "Lane outputs are stored in the mission registry and memory ledger so later work can continue from the same context.",
            };
          }
          return {
            title,
            body: "Risky or destructive work still pauses for explicit approval, while safe work can continue in parallel.",
          };
        })}
      />

      <DocsSection title="How to read the control room">
        <p>
          The orchestration page is not just decorative. It is a live operational surface for the
          system brain:
        </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>AverQel is the primary mission core.</li>
          <li>Subagents fan out for research, analysis, writing, and execution.</li>
          <li>Proactive tasks continue after the current mission ends.</li>
          <li>
            Connector lanes can execute follow-up work and persist the result or handoff state.
          </li>
          <li>The mission registry records state transitions, approvals, and summaries.</li>
          <li>
            Active mission cards now expose planner validation, hooks state, and approval pressure.
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="What phase 2 added to orchestration visibility">
        <ul className="list-disc space-y-2 pl-6">
          <li>mission-level runtime diagnostics</li>
          <li>lane delegation rationale metadata</li>
          <li>tool density summaries per lane</li>
          <li>hook and policy observability summaries</li>
          <li>operator diagnostics inside the inline mission canvas</li>
          <li>richer active-mission runtime badges in the orchestration overview</li>
        </ul>
      </DocsSection>

      <DocsSection title="Operational guarantees">
        <p>
          The orchestration engine was built to preserve existing answer quality while improving
          structure and visibility. It uses the same underlying agent runtime for the main answer,
          but now adds mission coordination, dependency scheduling, approval resume, durable
          tracking, proactive follow-up execution, connector sync execution, and a full
          orchestration view for operators. The lane plan is now shaped by a policy-aware or
          model-authored planner JSON instead of only inline heuristics. The recurring proactive
          worker and connector sync worker now route through the same orchestrator instead of
          bypassing it.
        </p>
        <p>
          The approval endpoint at{" "}
          <code>/deepspace/chats/orchestrations/missions/&#123;mission_id&#125;/approval</code>
          resumes paused work safely after approve or decline.
        </p>
        <p>
          Operators also have fleet-level visibility endpoints for the live system state:
          <code>/api/v1/integrations/connectors/summary</code> shows connector health, checkpoint
          age, retry state, and sync pressure,{" "}
          <code>/api/v1/deepspace/chats/subagents/summary</code>
          summarizes the active subagent fleet, <code>/api/v1/deepspace/chats/tasks/summary</code>
          reports proactive task pressure, <code>/api/v1/deepspace/chats/memory/evaluation</code>
          exposes memory quality checks, and <code>/api/v1/deepspace/chats/memory/lifecycle</code>
          previews stale-session pressure without deleting data. These are the production surfaces
          used for observability, not demo-only dashboards.
        </p>
      </DocsSection>

      <DocsSection title="Rollout gates">
        <p>
          Durable orchestration is enabled through staged reliability gates: durable schema and
          event recording, shadow observation, recovery and pause/resume, idempotent tool intent,
          observe-only cognitive supervision, selected-tenant execution, then multi-worker replay,
          chaos, and deployment-specific load validation.
        </p>
        <p>
          Local test results prove the code contracts. They do not claim unlimited throughput or
          live provider, connector, or VPS capacity. See the backend rollout checklist for the
          evidence required before default enablement.
        </p>
      </DocsSection>

      <DocsCards
        items={[
          {
            title: "Mission canvas",
            body: "The DeepSpace thread now materializes mission start, plan, graph, lane, approval, summary, and completion events inline so users can inspect the workflow where the answer happens.",
          },
          {
            title: "Layered lane view",
            body: "Lanes are grouped into mission control, support/proactive, discovery/analysis, and delivery/execution layers for clearer debugging.",
          },
          {
            title: "Operator confidence",
            body: "This surface is where planning, delegation, approvals, compaction, and runtime safety become inspectable instead of hidden.",
          },
        ]}
      />
    </DocsShell>
  );
}
