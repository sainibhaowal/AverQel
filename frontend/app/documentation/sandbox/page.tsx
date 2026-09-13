import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function SandboxDocsPage() {
  return (
    <DocsShell
      title="Sandboxed Analysis"
      intro="Run bounded Python or read-only SQL against selected Library files without exposing the API host, credentials, or private network."
    >
      <DocsCards
        items={[
          {
            title: "Library-first inputs",
            body: "Select authorized file IDs from Library. AverQel stages a temporary copy after tenant, user, and conversation checks; raw host paths and arbitrary URLs are never accepted.",
          },
          {
            title: "Supported analysis",
            body: "CSV and JSON analysis, pandas/OpenPyXL transformations, read-only SQL, and Matplotlib chart generation are supported in the isolated image.",
          },
          {
            title: "Bounded execution",
            body: "The executor uses a private Docker network, no host mounts, dropped capabilities, import checks, CPU/memory/time limits, and capped output.",
          },
          {
            title: "Automatic cleanup",
            body: "Staged inputs, generated files, and temporary working directories are removed after each run. Persisted outputs become private, authenticated artifacts only when requested.",
          },
        ]}
      />

      <DocsSection title="Request flow">
        <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-black/30 p-5 text-xs leading-6 text-slate-300">
          <code>{`Library file IDs → authorization → temporary staging
                  → sandbox-executor → result validation
                  → optional private artifact → DeepSpace panel`}</code>
        </pre>
      </DocsSection>

      <DocsSection title="Limits and safe usage">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Up to five input files per execution, with per-file and aggregate size limits.</li>
          <li>Execution time and generated output are capped; failures return a visible status.</li>
          <li>Network access, host filesystem access, secrets, and unsafe imports are blocked.</li>
          <li>
            Use this for calculations, transformations, validation, and charts—not arbitrary server
            administration.
          </li>
        </ol>
      </DocsSection>

      <DocsSection title="Deployment contract">
        <p>
          The API remains compatible when the feature is disabled. To execute locally, start the
          sandbox Compose profile and set the API&apos;s sandbox URL, token, and enabled flag. Keep
          the token unique per environment and do not place it in frontend code or chat prompts.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
