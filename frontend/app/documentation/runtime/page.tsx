import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function RuntimeDocsPage() {
  return (
    <DocsShell
      title="Durable Runtime & Streaming"
      intro="The native DeepSpace runtime stores execution state, events, checkpoints, approvals, and final answers so work can reconnect and recover without guessing."
    >
      <DocsCards
        items={[
          {
            title: "PostgreSQL source of truth",
            body: "Runs, nodes, checkpoints, approvals, tool intents, leases, cognitive reviews, and ordered events are persisted durably.",
          },
          {
            title: "Reconnectable streams",
            body: "SSE and WebSocket clients resume from an acknowledged event sequence instead of losing the mission timeline.",
          },
          {
            title: "Recoverable workers",
            body: "Leases, heartbeats, recovery sweeps, bounded tenant queues, and safe shutdown let another worker resume unfinished work.",
          },
          {
            title: "Evidence-first supervision",
            body: "Planner, executor, critic, verifier, and cognitive supervision decisions are persisted as structured, redacted evidence.",
          },
        ]}
      />

      <DocsSection title="Runtime lifecycle">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Create a typed mission graph and immutable execution contract.</li>
          <li>Persist the initial event and checkpoint before scheduling work.</li>
          <li>Claim a run or node lease before execution and heartbeat while active.</li>
          <li>Checkpoint before and after tool side effects and node transitions.</li>
          <li>Pause for approval, continue into a bounded epoch, repair, retry, or stop with evidence.</li>
          <li>Persist the final assistant message exactly once and expose the replay projection.</li>
        </ol>
      </DocsSection>

      <DocsSection title="Streaming and replay">
        <p>
          Native runtime clients use the additive run API, event cursor, graph, observability,
          resume, cancel, replay, and approval routes. Existing DeepSpace chat routes and event names
          remain compatibility adapters. The <code>after_sequence</code> cursor is the recovery
          boundary: the client acknowledges the latest applied event and requests only later events.
        </p>
        <p>
          Replay is read-only. It projects the append-only event ledger into status, node, approval,
          and timeline state for UI reconstruction and incident review.
        </p>
      </DocsSection>

      <DocsSection title="Budgets and approvals">
        <p>
          Durable execution is open-ended across continuation epochs, but every epoch has explicit
          wall-clock, token, cost, tool, retry, concurrency, side-effect, risk, stagnation, goal,
          and escalation limits. Low-risk deterministic reads may proceed automatically. Writes,
          external effects, destructive actions, privilege escalation, ambiguity, and untrusted
          tools require human authority or are blocked.
        </p>
      </DocsSection>

      <DocsSection title="Rollout and verification status">
        <p>
          The repository contains unit, database-backed integration, API, frontend, and E2E test
          contracts for recovery, pause/resume, replay, tenant isolation, cursor handling, leases,
          idempotency, cognition, and policy. Local verification does not certify capacity for a
          particular VPS, model provider, connector, or customer workload.
        </p>
        <p>
          Before broad enablement, operators should use the staged gates in the runtime rollout
          checklist: schema recording, shadow scheduling, recovery, approvals, observe-only
          supervision, selected tenants, then multi-worker chaos and load validation.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
