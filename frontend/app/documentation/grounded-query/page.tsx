import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function GroundedQueryDocsPage() {
  return (
    <DocsShell
      title="Grounded Query"
      intro="AverQel still has a strong grounded retrieval layer for document-first work: upload, parse, chunk, embed, retrieve, stream, and cite source-backed answers."
    >
      <DocsCards
        items={[
          {
            title: "Document Pipeline",
            body: "Uploaded files are processed into text, chunked for retrieval, embedded, indexed, and tracked with processing status, progress, and extraction metadata.",
          },
          {
            title: "Grounded Answers",
            body: "The query runtime is built to answer from accessible documents and return results tied to actual source material instead of only ungrounded generation.",
          },
          {
            title: "Rich Output",
            body: "The query UI supports markdown, charts, diagrams, and structured blocks so grounded results can be presented as more than plain text.",
          },
          {
            title: "Document Inspection",
            body: "Users can inspect status, full text, versions, chunks, download the original file, and save extracted or selected content into DeepSpace notes.",
          },
        ]}
      />

      <DocsSection title="What the user-facing document system includes">
        <ul className="list-disc space-y-2 pl-6">
          <li>document uploads with live processing progress</li>
          <li>supported format discovery</li>
          <li>download and full-text viewing</li>
          <li>reingest and retry support</li>
          <li>quarantine/extraction quality signals</li>
          <li>query page for grounded question-answering</li>
          <li>save-to-note flows that turn source material into DeepSpace workspace content</li>
        </ul>
      </DocsSection>

      <DocsSection title="How it differs from DeepSpace chat">
        <p>
          Grounded query is best when the user wants evidence-backed answers over documents.
          DeepSpace is best when the user wants a broader productivity conversation with memory,
          safe retrieval, and optional source inspection.
        </p>
        <p>
          Both surfaces are important: Query is retrieval-first, while DeepSpace is the broader
          conversation surface.
        </p>
      </DocsSection>

      <DocsSection title="Why it still matters">
        <p>
          AverQel depends on solid grounded retrieval to turn private files into usable,
          trustworthy context for both query answers and DeepSpace conversations.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
