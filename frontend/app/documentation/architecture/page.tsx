import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ArchitectureDocsPage() {
  return (
    <DocsShell
      title="Architecture overview"
      intro="A high-level map of the AverQel clients, API, workers, data services, and the boundaries between its main product areas."
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
            title: "Workers and optional services",
            body: "Background workers process configured document, DeepSpace, connector, maintenance, and scheduled work. Local inference, browser rendering, sandbox execution, email, push, and realtime voice require the relevant service configuration.",
          },
          {
            title: "State and storage",
            body: "PostgreSQL stores durable application data, Redis supports configured queue and event paths, and private object storage holds files. Production uploads require the configured storage and malware-scanning services.",
          },
          {
            title: "External providers",
            body: "OAuth providers, model providers, SearXNG, and approved remote MCP servers are reached by the backend through bounded and policy checked integrations.",
          },
          {
            title: "Evidence-first web research",
            body: "Explicit research requests use a provider-independent pipeline: planned search variants, secure page reads, passage ranking, durable source records, source-quality labels, and claim citation instructions before chat synthesis.",
            href: "/documentation/web-research",
          },
        ]}
      />

      <DocsSection title="How a request moves">
        <ol className="list-decimal space-y-3 pl-6">
          <li>The browser or Electron client sends a tenant-authenticated request.</li>
          <li>
            The API checks authentication, tenant scope, ownership, and role permissions for that
            route.
          </li>
          <li>
            Documents Hub handles source-file operations; Query handles retrieval-first document
            questions.
          </li>
          <li>
            DeepSpace handles its own conversation, working Library, and permitted optional tool
            workflows.
          </li>
          <li>
            Configured providers and workers perform only the work allowed by the request and
            policy.
          </li>
          <li>
            The relevant response, event, or durable result returns through its product surface.
          </li>
        </ol>
      </DocsSection>

      <DocsSection title="Runtime boundaries">
        <pre className="overflow-x-auto rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6">
          {`Client
  -> frontend
  -> api
     -> PostgreSQL and Redis
     -> MinIO and ClamAV
     -> configured model and retrieval providers
     -> private object storage and malware scanner
     -> optional sandbox, browser, email, push, or voice services
  -> ingestion, DeepSpace, MCP, maintenance, and scheduler workers`}
        </pre>
        <p className="mt-4">
          Compose files define deployable service layouts, not proof that an environment has started
          or configured every service. Voice, sandbox, research rendering, email, push, and local
          inference each have additional deployment requirements described in their product guides.
        </p>
      </DocsSection>

      <DocsSection title="Safety boundaries">
        <p>
          The backend is the authorization boundary for authenticated requests, tenant access,
          provider credentials, collection sharing, and tool calls. Some product areas process
          content server-side, and support staff can read user-submitted support or feedback threads
          when authorized. Do not infer a client-only or end-to-end encryption guarantee from tenant
          isolation or encrypted storage.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
