import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function MemoryWorkspaceDocsPage() {
  return (
    <DocsShell
      title="Memory & Workspace"
      intro="AverQel combines persistent memory, session memory, task ledgers, proactive rules, and long-session compaction so the system can keep working without losing context."
    >
      <DocsCards
        items={[
          {
            title: "Memory Facts",
            body: "DeepSpace stores deduplicated memory facts with embeddings, tags, importance scoring, retention metadata, and freshness-aware ranking.",
          },
          {
            title: "Task Ledger",
            body: "The todo ledger is durable and agent-writable, so multi-step work can continue as tasks instead of vanishing when the current answer ends.",
          },
          {
            title: "Session Compaction",
            body: "Older conversation turns can be summarized into structured session memory while recent context stays active and the user-visible thread remains stable.",
          },
          {
            title: "Proactive Workspace",
            body: "Recurring or queued work can continue through proactive tasks and triggers even after the original chat turn is complete.",
          },
        ]}
      />

      <DocsSection title="Memory scopes and retention">
        <p>AverQel memory is not a single flat bucket. The system distinguishes between:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>session memory</strong> for temporary conversational continuity
          </li>
          <li>
            <strong>user memory</strong> for durable user-specific facts and preferences
          </li>
          <li>
            <strong>global memory</strong> for shared or system-wide patterns when explicitly
            allowed
          </li>
        </ul>
        <p>
          Memory entries include importance, access counts, freshness signals, and retention logic
          so the runtime can retrieve what matters without blindly replaying raw history forever.
        </p>
      </DocsSection>

      <DocsSection title="How proactive work fits in">
        <p>
          The task ledger and proactive runtime let AverQel turn an insight into ongoing work. A
          conversation can create follow-up tasks, schedule single-run or recurring work, and feed
          those tasks back through the orchestrator instead of treating them as isolated background
          jobs.
        </p>
        <p>
          This is how the product moves from “chat that answered once” to “system that can remember,
          monitor, and follow up”.
        </p>
      </DocsSection>

      <DocsSection title="What phase 1 improved">
        <ul className="list-disc space-y-2 pl-6">
          <li>manual compaction is persisted into conversation metadata</li>
          <li>
            automatic compaction now triggers when context usage approaches the safety threshold
          </li>
          <li>frontend thread state can restore compaction metadata cleanly</li>
          <li>mission and lane state normalization became safer for long threads</li>
        </ul>
      </DocsSection>

      <DocsSection title="What users notice">
        <ul className="list-disc space-y-2 pl-6">
          <li>the context meter can show compaction state and saved token counts</li>
          <li>long sessions remain more stable instead of gradually degrading</li>
          <li>proactive tasks and follow-up work are visible as durable workspace state</li>
          <li>agent memory and task continuity survive beyond one visible answer turn</li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
