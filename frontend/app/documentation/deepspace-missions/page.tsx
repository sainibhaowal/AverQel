import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function DeepSpaceMissionsDocsPage() {
  return (
    <DocsShell
      title="DeepSpace Missions"
      intro="Every new DeepSpace message runs through a durable, checkpointed workflow that can plan, delegate, pause, recover, verify, repair, and reconstruct the final answer after a restart."
    >
      <DocsCards
        items={[
          {
            title: "Research mission",
            body: "The system can fan out into research and analysis lanes, collect evidence, and then synthesize a final answer or memo.",
          },
          {
            title: "Coding mission",
            body: "Workspace-aware tasks can inspect files, reason about repo state, and request approval before making risky changes.",
          },
          {
            title: "Approval-required mission",
            body: "If a tool or lane hits a risky action, the mission pauses visibly and moves into an approval-aware state until the user decides.",
          },
          {
            title: "Proactive or support mission",
            body: "A mission can also create or continue background follow-up work, connector handoffs, support sweeps, or durable memory updates.",
          },
        ]}
      />

      <DocsSection title="What a mission is">
        <p>
          A mission is one orchestrated execution for one user request. Instead of handling the
          prompt as only a single answer turn, AverQel can create a plan, build lane dependencies,
          execute work in parallel, pause for approval, persist follow-up state, and then synthesize
          the final output.
        </p>
      </DocsSection>

      <DocsSection title="What users see during a mission">
        <ul className="list-disc space-y-2 pl-6">
          <li>an inline mission canvas inside the DeepSpace thread</li>
          <li>mission status, phase, planner source, and runtime badges</li>
          <li>lane cards with summaries, recent activity, dependencies, and profile data</li>
          <li>approval queue items when a lane requires human confirmation</li>
          <li>operator diagnostics for policy, hooks, compaction, and lane work density</li>
          <li>durable run status, graph nodes, event timeline, replay, and recovery state</li>
          <li>reconnect cursors that resume after the last acknowledged PostgreSQL event sequence</li>
          <li>read-only replay and operator controls from both chat and the orchestration control room</li>
          <li>the final assistant answer restored into the normal conversation history</li>
        </ul>
      </DocsSection>

      <section id="durable-runtime">
        <DocsSection title="Durable runtime">
          <p>
            DeepSpace uses the native durable runtime automatically. There is no Durable toggle and
            users do not choose between legacy and durable execution. Each new chat run persists its
            graph, node state, ordered PostgreSQL event ledger, checkpoints, approvals, replay data,
            memory context, compaction state, and idempotent tool records.
          </p>
          <p>
            A short scheduler lease protects ordered run decisions, while ready independent nodes
            receive individual leases and may be claimed by separate workers within a bounded
            concurrency contract. The cognitive loop uses planner, executor, critic, verifier, and
            repair/branch nodes. Completion requires concrete evidence and an independent verifier.
            Low-risk automatic decisions are deterministic policy only; external, destructive,
            privileged, or ambiguous work still waits for a human decision.
          </p>
          <p>
            Streaming can reconnect from a PostgreSQL event sequence through SSE or WebSocket. If a
            browser, API process, or worker restarts, the thread can rehydrate from durable events,
            checkpoints, and the persisted assistant message instead of guessing from partial text.
          </p>
          <p>
            Durable work is not capped at twelve lifetime steps. Each execution epoch has explicit
            time, token, cost, retry, concurrency, side-effect, risk, goal, and escalation limits.
            Verified progress can continue into another epoch; uncertain work asks for approval;
            repeated work invokes repair; unsafe or impossible work stops with evidence and a
            recovery recommendation.
          </p>
        </DocsSection>
      </section>

      <DocsSection title="Cognitive supervision and self-correction">
        <p>
          DeepSpace evaluates the mission trajectory from durable evidence, not from an assistant
          claim that the work is complete. It measures node progress, tool success and retry
          patterns, repeated work, validator results, artifact changes, goal coverage, strategy
          diversity, budget burn, unresolved risk, and approval pressure.
        </p>
          <p>
            An independent supervisor can recommend continuing, branching, repairing, retrying,
          asking for approval, finishing, or stopping. The scheduler and policy engine enforce the
          recommendation. The supervisor cannot call tools or authorize itself, and only redacted
            structured summaries are persisted for the operator timeline and replay view.
          </p>
          <p>
            Mission plans use typed graph nodes and dependencies. The runtime validates duplicate
            keys, missing or circular dependencies, explicit entry-point reachability, and legal
            node-state transitions before the scheduler can execute a plan. Repairs and branches
            are revisions of that same typed graph.
          </p>
        <ul className="list-disc space-y-2 pl-6">
          <li>Planner creates the typed mission graph.</li>
          <li>Executor performs only the scoped node work.</li>
          <li>Critic identifies missing or contradictory evidence.</li>
          <li>Verifier checks objective completion independently.</li>
          <li>Repair planner creates the smallest bounded correction when needed.</li>
        </ul>
      </DocsSection>

      <DocsSection title="Advanced approvals and tool safety">
        <p>
          Every tool has an explicit contract describing its risk, read/write and external
          capability, idempotency, retry policy, timeout, compensation requirement, approval rule,
          tenant scope, and workspace scope. Deterministic low-risk reads can proceed automatically
          when their scope is valid.
        </p>
        <p>
          Writes, external side effects, destructive or privileged actions, ambiguous work, and
          untrusted connector capabilities pause for human approval. Durable runs persist the exact
          pending action, contract evidence, event history, and idempotency intent in PostgreSQL,
          so approval can safely remain pending across restarts and return later without silently
          repeating an external side effect.
        </p>
      </DocsSection>

      <DocsSection title="Operational status and boundaries">
        <p>
          The durable runtime is implemented as a native DeepSpace execution layer and has passed
          focused scheduler, recovery, compatibility, chaos, API, frontend, and synthetic database
          load checks. These checks use isolated infrastructure and synthetic data; they do not
          certify live provider capacity or customer traffic.
        </p>
        <p>
          These controls are production-oriented, but capacity is deployment-specific. Provider
          rate limits, model latency, PostgreSQL sizing, Redis sizing, worker replicas, queue
          settings, and connector policies determine the safe operating envelope. Teams should
          load-test their expected concurrency and run a soak test before broad production rollout.
        </p>
        <p>
          A short test is not a promise of unlimited throughput. DeepSpace can extend work through
          continuation epochs, but every epoch remains bounded by time, token, cost, retry,
          concurrency, side-effect, risk, goal, and escalation rules.
        </p>
      </DocsSection>

      <DocsSection title="Mission examples">
        <p>
          <strong>Research prompt:</strong> compare recent provider pricing and write a
          recommendation.
        </p>
        <p>
          <strong>Coding prompt:</strong> inspect a repo, locate a configuration issue, and propose
          a safe fix.
        </p>
        <p>
          <strong>Approval prompt:</strong> perform the analysis, but ask before editing files or
          changing configuration.
        </p>
        <p>
          <strong>Proactive prompt:</strong> if a risk is detected, create a follow-up task or
          recurring monitor.
        </p>
        <p>
          <strong>Connector prompt:</strong> fetch current information from GitHub, Drive, Slack, or
          Gmail and combine it with the current task.
        </p>
      </DocsSection>

      <DocsSection title="Mission types the current system can express">
        <ul className="list-disc space-y-2 pl-6">
          <li>main chat lane for the primary answer path</li>
          <li>research and analysis lanes for evidence gathering and reasoning</li>
          <li>writer and executor lanes for delivery or action-focused work</li>
          <li>memory lanes for durable storage and work ledger updates</li>
          <li>proactive lanes for follow-up task creation</li>
          <li>connector lanes for external system actions and handoffs</li>
          <li>approval lanes when risky actions must stop and wait</li>
        </ul>
      </DocsSection>

      <DocsSection title="Why this matters">
        <p>
          Mission mode is what makes AverQel feel like an agentic system instead of just a chatbot.
          It gives the product room to plan, delegate, remember, pause safely, continue later, and
          show the user what is really happening.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
