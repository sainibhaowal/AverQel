import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ArtifactsDocsPage() {
  return (
    <DocsShell
      title="Artifacts & Exports"
      intro="DeepSpace can turn research and analysis into private, durable files that are previewable in the workspace and downloadable through authenticated routes."
    >
      <DocsCards
        items={[
          {
            title: "Generated Files panel",
            body: "Created files are collected in the DeepSpace artifact panel with status, type, preview, open, save, and download actions.",
          },
          {
            title: "Broad output types",
            body: "Markdown, HTML, text, JSON, CSV, SVG, Mermaid/UML diagrams, tables, charts, images, audio, video, PDF, DOCX, and PPTX are represented by explicit artifact metadata.",
          },
          {
            title: "Durable and private",
            body: "Artifact jobs persist status and ownership. Files remain tenant-scoped and are served only by authenticated Library/download routes.",
          },
          {
            title: "Safe previews",
            body: "Text is rendered as text, structured data uses bounded previews, and binary content is not injected into the chat response as giant base64 payloads.",
          },
        ]}
      />

      <DocsSection title="Recommended output path">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Ask DeepSpace to create a report, table, chart, diagram, or presentation.</li>
          <li>Review the queued, running, completed, or failed status in Generated Files.</li>
          <li>Open a safe preview, then save or download the authenticated artifact.</li>
          <li>Find durable files again in Library without relying on conversation text.</li>
        </ol>
      </DocsSection>

      <DocsSection title="Artifact lifecycle">
        <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-black/30 p-5 text-xs leading-6 text-slate-300">
          <code>{`request → validated artifact job → worker materialization
        → private Library record → preview/download/export`}</code>
        </pre>
      </DocsSection>

      <DocsSection title="What is intentionally protected">
        <p>
          Artifact creation never grants a model direct storage access. Content is validated before
          persistence, output sizes are bounded, and download authorization checks the owning tenant
          and user. Existing PDF, DOCX, Markdown, and authenticated export behavior remains intact.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
