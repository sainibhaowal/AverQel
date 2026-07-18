import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function SupportDocsPage() {
  return (
    <DocsShell
      title="Support Centre"
      intro="AverQel Support Centre provides self-help troubleshooting databases, system state verification diagnostics, and developer ticket submission forms."
    >
      <DocsCards
        items={[
          {
            title: "Troubleshooting Guide",
            body: "Find immediate answers to common issues regarding E2EE key synchronization, connector OAuth failures, or container timeouts.",
          },
          {
            title: "System Diagnostics",
            body: "Run diagnostic checks directly from the help drawer to inspect your local IndexedDB limits and WebSocket ping latency.",
          },
          {
            title: "Developer Tickets",
            body: "Submit a support ticket with system diagnostic attachments so platform administrators can audit logs and address problems.",
          },
          {
            title: "Documentation Index",
            body: "Navigate the entire technical manual index to understand DeepSpace routing, vector compaction, and privacy boundaries.",
          },
        ]}
      />

      <DocsSection title="System State Verification">
        <p>
          Before opening support tickets, you can run diagnostic tests directly in the app. The diagnostics scanner inspects IndexedDB size constraints, Web Crypto API availability, WebSocket latency, and Redis pub/sub connectivity to pinpoint connection bottlenecks.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
