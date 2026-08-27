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
            title: "Web and desktop clients",
            body: "The browser and Electron clients provide the user interface. Electron loads the shared web experience and does not receive provider secrets.",
          },
          {
            title: "API boundary",
            body: "The FastAPI service authenticates requests, applies tenant and user authorization, orchestrates work, and exposes health endpoints.",
          },
          {
            title: "Workers and inference",
            body: "Celery workers process documents, DeepSpace jobs, MCP work, maintenance, and schedules. The inference service handles local model work.",
          },
          {
            title: "State and storage",
            body: "PostgreSQL stores durable state, Redis coordinates queues and events, MinIO stores private objects, and ClamAV scans files before processing.",
          },
          {
            title: "External providers",
            body: "OAuth providers, model providers, SearXNG, and approved remote MCP servers are reached by the backend through bounded and policy checked integrations.",
          },
        ]}
      />

      <DocsSection title="How a request moves">
        <ol className="list-decimal space-y-3 pl-6">
          <li>The browser or Electron client sends a tenant-authenticated request.</li>
          <li>
            The API loads authorized history, document context, memory, and provider configuration.
          </li>
          <li>
            The API selects permitted tools and queues background work when the request needs it.
          </li>
          <li>
            The selected model or remote provider returns data through the backend policy boundary.
          </li>
          <li>The result streams to the client and durable conversation state is persisted.</li>
        </ol>
      </DocsSection>

      <DocsSection title="Runtime boundaries">
        <pre className="overflow-x-auto rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6">
          {`Client
  -> frontend
  -> api
     -> PostgreSQL and Redis
     -> MinIO and ClamAV
     -> inference and SearXNG
     -> approved external providers
  -> worker, ingestion, MCP, maintenance, and scheduler queues`}
        </pre>
        <p className="mt-4">
          The production service layout is defined by the checked-in backend Compose files. Optional
          packages, including the separate LiveKit server materials, are not considered active until
          their service, configuration, networking, and health checks are deployed explicitly.
        </p>
      </DocsSection>

      <DocsSection title="Safety boundaries">
        <p>
          Authentication, tenant isolation, encrypted secrets, provider policy, approval checks, and
          MCP authorization remain backend responsibilities. Clients display authorized results and
          request actions, while the backend makes the final authorization decision immediately
          before execution.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
