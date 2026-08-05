import { DocsCards, DocsSection, DocsShell } from "./_components/DocsShell";
import { docsNavGroups } from "./_components/docsNav";

export default function DocsIndex() {
  const cardBodyByTitle: Record<string, string> = {
    "Getting Started":
      "Start with the real user flow: providers, documents, connectors, DeepSpace, approvals, and exportable workspaces.",
    "What Is AverQel":
      "Product definition, privacy model, and how AverQel evolved from document intelligence into an agentic operating layer.",
    Features:
      "Explore grounded retrieval, DeepSpace chat, note editing, memory, providers, and visual answer rendering.",
    "Grounded Queries":
      "Document ingestion, grounded retrieval, source-backed answers, rich rendering, and how the classic query layer fits beside DeepSpace.",
    "Documents Hub":
      "See how the note editor, math blocks, exports, and split panels work together.",
    "Collections & Sharing":
      "Zero-knowledge E2EE bridge with safety numbers, encrypted backups, self-destruct timers, real-time delivery ticks, and peer-to-peer document sharing.",
    "Connectors & MCP":
      "See the current connector model, OAuth posture, MCP runtime foundations, and the long-term MCP standardization path.",
    "Runtime & Streaming":
      "See how DeepSpace streams answers, safety prompts, persistence, and reconnectable chat state.",
    "Memory & Workspace":
      "Understand persistent memory facts and how they support future conversations.",
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
    "System Walkthrough":
      "A plain-language step-by-step guide to how the UI, chat service, tools, memory, and approvals work together.",
  };

  return (
    <DocsShell
      title="AverQel Documentation"
      intro="The in-app source of truth for AverQel: grounded chat, DeepSpace, documents, memory, connectors and MCP, providers, privacy, and product architecture."
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
              <h3 className="text-foreground flex items-center gap-3 text-lg font-black tracking-tight">
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
          AverQel combines grounded retrieval, DeepSpace chat, provider routing, connector and MCP
          integrations, persistent memory, and a working document editor.
        </p>
        <p>
          The command surface is chat. DeepSpace keeps the conversation, provider selection, safe
          tool execution, memory, and assistant-message persistence tenant-scoped and separate from
          the MCP runtime.
        </p>
      </DocsSection>
      <DocsSection title="Durable runtime readiness">
        <p>
          DeepSpace keeps chat history and assistant answers durable so a reload can restore the
          conversation without requiring an IDE-style workspace or control room.
        </p>
        <p>
          The implementation has been validated with focused integration, recovery, chaos, and short
          real-provider staging tests. This documentation does not promise a universal throughput
          number: every deployment must validate its own provider, worker, database, Redis,
          connector, and concurrency limits before broad rollout.
        </p>
      </DocsSection>
      <DocsSection title="How To Use This Documentation">
        <p>
          This documentation set is written to replace guesswork with product truth. It covers what
          the app has now, how the main systems connect, what changed in the recent DeepSpace
          hardening phases, and where future development should stay careful.
        </p>
        <p>
          If you are a user, start with Getting Started, Grounded Queries, Documents Hub, and Memory
          & Workspace. If you are developing the system, also read Connectors & MCP, Providers,
          Privacy & Security, and Architecture.
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
          <li>DeepSpace chat, streaming answers, and safe approval prompts</li>
          <li>note editor, research tasks, exports, and working surfaces</li>
          <li>persistent memory and conversation history</li>
          <li>connectors, MCP transition direction, and external system handling</li>
          <li>provider routing across cloud and local runtimes</li>
          <li>privacy, secret handling, tenant boundaries, and admin posture</li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
