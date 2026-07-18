import { DocsCards, DocsSection, DocsShell } from "./_components/DocsShell";
import { docsNavGroups } from "./_components/docsNav";

export default function DocsIndex() {
  const cardBodyByTitle: Record<string, string> = {
    "Getting Started":
      "Start with the real user flow: providers, documents, connectors, DeepSpace, approvals, and exportable workspaces.",
    "What Is AverQel":
      "Product definition, privacy model, and how AverQel evolved from document intelligence into an agentic operating layer.",
    Features:
      "Explore RAG, DeepSpace, orchestration, file-aware editing, proactive work, runtime preferences, and visual answer rendering.",
    "Grounded Queries":
      "Document ingestion, grounded retrieval, source-backed answers, rich rendering, and how the classic query layer fits beside DeepSpace.",
    "Documents Hub":
      "See how the note editor, math blocks, exports, split panels, and file-aware save actions work together.",
    "Collections & Sharing":
      "Zero-knowledge E2EE bridge with safety numbers, encrypted backups, self-destruct timers, real-time delivery ticks, and peer-to-peer document sharing.",
    "Connectors & MCP":
      "See the current connector model, OAuth posture, MCP runtime foundations, and the long-term MCP standardization path.",
    "DeepSpace Missions":
      "Real examples of durable-first research, coding, approval, recovery, repair, and connector missions and what users actually see.",
    "Runtime & Streaming":
      "See how DeepSpace streams durable planning, tool calls, approvals, compaction, replay, and final answers through reconnectable SSE and WebSocket cursors.",
    "Insights Monitor":
      "The live runtime sidecar for context meter, compaction, vitals, latency, and subagent monitoring.",
    "Memory & Workspace":
      "Understand memory facts, task ledgers, compaction, recurring work, and proactive follow-up infrastructure.",
    "Proactive Agents":
      "Background automation, event-driven triggers, lane scheduling, and approval-gated autonomous execution.",
    "Global Orchestration":
      "Explore the federated mission brain, dynamic lane scheduling, live control room, and operator observability surfaces.",
    "Privacy & Security":
      "Deep dive into isolation, encrypted provider and connector secrets, approval gating, and metadata-first admin boundaries.",
    "Trust & Privacy":
      "Trust controls, data retention policies, and fine-grained permission boundaries for secure workspace operation.",
    "Platform Admin":
      "Operational rules for platform admins, what they can see, and what remains intentionally hidden.",
    "Profile Settings":
      "Manage your account identity, connection credentials, active sessions, and permanent peer-to-peer connection IDs.",
    "Autonomous Memory":
      "Configure how AverQel stores, compacts, and recalls durable memory facts across sessions and missions.",
    "Providers Config":
      "Architectural details on provider routing, cloud and local runtimes, OpenRouter coverage, model discovery, and secret safety.",
    "Support Centre":
      "Self-help troubleshooting, system diagnostics, developer ticket submission, and documentation search.",
    "Share Feedback":
      "Submit feature requests, usability evaluations, roadmap voting, and community engagement.",
    "Product Roadmap":
      "What is finished, what is hardened, and where the platform is headed next without rewriting the core.",
    "Architecture Spec":
      "One page that maps frontend surfaces, backend services, persistence, providers, connectors, and runtime flows together.",
    "Unified Brain Guide":
      "Developer-facing contracts and the end-to-end checklist that keeps AverQel, orchestrator, executor, memory, and safety layers aligned.",
    "System Walkthrough":
      "A plain-language step-by-step guide to how the UI, orchestrator, executor, tools, memory, and approvals work together.",
  };

  return (
    <DocsShell
      title="AverQel Documentation"
      intro="The in-app source of truth for AverQel: DeepSpace runtime, orchestration, editor and file workflows, memory and proactive work, connectors and MCP, providers, privacy, and developer-facing architecture clarity."
    >
      {docsNavGroups
        .filter((g) => g.group !== "Core Concept")
        .map((group) => {
          const allItems = group.items.flatMap((item) => {
            const result = [item];
            if (item.items) result.push(...item.items);
            return result;
          });
          return (
            <div key={group.group} className="space-y-4">
              <h3 className="text-foreground text-lg font-black tracking-tight flex items-center gap-3">
                <div className="bg-primary h-4 w-1 rounded-full" />
                {group.group}
              </h3>
              <DocsCards
                items={allItems
                  .filter((item) => item.href !== "/documentation")
                  .map((item) => ({
                    title: item.title,
                    href: item.href,
                    body:
                      cardBodyByTitle[item.title] ??
                      `Comprehensive guide to ${item.title.toLowerCase()}.`,
                  }))}
              />
            </div>
          );
        })}
      <DocsSection title="What AverQel Does Now">
        <p>
          AverQel is no longer only a document question-answering surface. It now combines grounded
          retrieval, DeepSpace agentic execution, mission planning, subagents, provider routing,
          connector automation, durable memory, proactive follow-up, and a full working editor.
        </p>
        <p>
          The command surface is DeepSpace and chat. The execution layer is the backend agent loop
          plus the durable mission orchestrator. New DeepSpace messages automatically use PostgreSQL
          runs, checkpoints, event cursors, approvals, budgets, memory, verification, repair, and
          assistant-message persistence. The working surface is the editor, task ledger, mission
          canvas, and orchestration control room. All of it stays tenant-scoped and streams live
          state into the UI.
        </p>
      </DocsSection>
      <DocsSection title="Durable runtime readiness">
        <p>
          DeepSpace now has a durable execution foundation: PostgreSQL-backed runs, graph nodes,
          ordered events, immutable checkpoints, leases, approvals, budgets, replay, rehydration,
          and persisted assistant answers. Existing chat routes remain compatible adapters, so
          users see one unified DeepSpace experience.
        </p>
        <p>
          The implementation has been validated with focused integration, recovery, chaos, and
          short real-provider staging tests. This documentation does not promise a universal
          throughput number: every deployment must validate its own provider, worker, database,
          Redis, connector, and concurrency limits before broad rollout.
        </p>
      </DocsSection>
      <DocsSection title="How To Use This Documentation">
        <p>
          This documentation set is written to replace guesswork with product truth. It covers what
          the app has now, how the main systems connect, what changed in the recent DeepSpace
          hardening phases, and where future development should stay careful.
        </p>
        <p>
          If you are a user or operator, start with Getting Started, DeepSpace Missions, Runtime &
          Streaming, and Global Orchestration. If you are developing the system, also read Unified
          Brain Checklist, Connectors & MCP, Providers, and Memory & Workspace.
        </p>
      </DocsSection>
      <DocsCards
        items={[
          {
            title: "Durable-first DeepSpace",
            body: "New chats no longer ask users to choose a runtime. Durable execution, restart recovery, replay, rehydration, and final-answer persistence happen automatically.",
          },
          {
            title: "Phase 1",
            body: "Long-session stability and safer runtime contracts are now implemented, including auto-compaction, compaction persistence, and reducer-safe mission state handling.",
          },
          {
            title: "Phase 2",
            body: "Deep observability and operator confidence are now implemented, including runtime diagnostics, hook and policy summaries, richer lane metadata, and canvas diagnostics.",
          },
          {
            title: "Phase 3",
            body: "This in-app documentation work is the practical Phase 3 layer for developer clarity, maintenance ease, onboarding, and safer future development.",
          },
          {
            title: "MCP Strategy",
            body: "The docs now explain what is already MCP-ready, what is still transitional, and how connector standardization fits the current architecture.",
          },
          {
            title: "Editor + Workspace",
            body: "The docs treat the note editor and workspace as core product surfaces, not side utilities.",
          },
          {
            title: "Provider Clarity",
            body: "Cloud, local, OpenRouter, embedding, reranker, and web-search runtime responsibilities are documented in one place.",
          },
        ]}
      />
      <DocsSection title="What The Documentation Covers">
        <p>The documentation now covers:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>document ingestion and grounded query behavior</li>
          <li>DeepSpace runtime and streamed thought/action surfaces</li>
          <li>mission planning, orchestration, subagents, and approvals</li>
          <li>note editor, file-aware tasks, exports, and working surfaces</li>
          <li>memory, task ledgers, compaction, and proactive workflows</li>
          <li>connectors, MCP transition direction, and external system handling</li>
          <li>provider routing across cloud and local runtimes</li>
          <li>privacy, secret handling, tenant boundaries, and admin posture</li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
