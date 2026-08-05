import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ArchitectureDocsPage() {
  return (
    <DocsShell
      title="Architecture"
      intro="A high-level map of AverQel's chat, documents, memory, providers, integrations, and security boundaries."
    >
      <DocsCards
        items={[
          {
            title: "Frontend surfaces",
            body: "Dashboard pages, grounded queries, DeepSpace chat, documents, memory, settings, MCP, and documentation are separate product surfaces.",
          },
          {
            title: "Backend services",
            body: "Backend services handle authentication, retrieval, answer generation, safe tool execution, memory, providers, and integrations.",
          },
          {
            title: "Persistence",
            body: "PostgreSQL stores tenant-scoped conversations, messages, memory, provider configuration, and integration state.",
          },
          {
            title: "MCP boundary",
            body: "MCP discovery, authorization, catalog, and remote tool execution remain isolated from the normal chat and memory surfaces.",
          },
        ]}
      />

      <DocsSection title="How a request moves">
        <ol className="list-decimal space-y-3 pl-6">
          <li>The frontend sends a tenant-authenticated chat or query request.</li>
          <li>The backend loads scoped history and relevant document or memory context.</li>
          <li>
            The selected provider generates the answer, with permitted tools available when needed.
          </li>
          <li>The result streams to the frontend and is persisted as conversation history.</li>
        </ol>
      </DocsSection>

      <DocsSection title="Safety boundaries">
        <p>
          Authentication, tenant isolation, encrypted secrets, provider policy, approval checks, and
          MCP authorization remain backend responsibilities. Removing the orchestration and
          IDE-style surfaces does not weaken those boundaries.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
