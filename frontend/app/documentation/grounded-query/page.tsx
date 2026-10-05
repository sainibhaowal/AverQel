import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function GroundedQueryDocsPage() {
  return (
    <DocsShell
      title="Grounded Query"
      intro="Query is the retrieval-first surface for asking focused questions about documents available to your account and examining the source material behind an answer."
    >
      <DocsCards
        items={[
          {
            title: "Question and retrieval",
            body: "The query service searches the accessible indexed material and supplies relevant context to the configured answer provider.",
          },
          {
            title: "Sources and citations",
            body: "Review the source references shown with a response. Check the cited document and passage for important decisions; retrieval and generated summaries can be incomplete.",
          },
          {
            title: "History and follow-up",
            body: "Use the Query interface to continue supported conversations and review saved query history available to your account.",
          },
          {
            title: "Document preparation",
            body: "Upload, inspect, and organize source files in Documents Hub. Query does not replace document processing or become a second file manager.",
          },
        ]}
      />
      <DocsSection title="How to get better results">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Make sure the relevant file has completed processing in Documents Hub.</li>
          <li>
            Ask one clear question and name a document, date, or subject when that helps narrow
            context.
          </li>
          <li>
            Check the cited passages and ask a follow-up if the evidence is incomplete or ambiguous.
          </li>
          <li>
            For work that needs broader research, drafting, analysis, notes, or tools, continue in
            DeepSpace.
          </li>
        </ol>
      </DocsSection>
      <DocsSection title="Limits and availability">
        <p>
          Answer quality depends on the source content, extraction/OCR, indexing, retrieval
          settings, and configured model provider. A citation shows what the answer references; it
          does not prove that the source itself is correct or that the response is complete.
          Provider and search failures may make some paths unavailable.
        </p>
      </DocsSection>
      <DocsSection title="Query is not DeepSpace">
        <p>
          Query is optimized for retrieval-first questions over source documents. DeepSpace is a
          separate broader conversation workspace with its own working Library and optional
          research, sandbox, schedule, memory, and connector capabilities. Documents Hub remains the
          home for source document lifecycle and organization.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
