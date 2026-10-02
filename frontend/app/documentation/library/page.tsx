import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function LibraryDocsPage() {
  return (
    <DocsShell
      title="Library, OCR & RAG"
      intro="Library is the governed source layer for document previews, extraction, OCR, retrieval, sandbox inputs, and private artifacts."
    >
      <DocsCards
        items={[
          {
            title: "Broad file intake",
            body: "Native extraction covers PDF, DOCX, PPTX, XLSX, CSV, Markdown, text, code, and OCR-capable images. Legacy office conversion is handled only when the configured worker is enabled.",
          },
          {
            title: "OCR before answering",
            body: "Images and scanned pages pass through the existing OCR extractor during ingestion. Extracted text and quality signals are reused by grounded query and DeepSpace instead of re-reading files in every answer.",
          },
          {
            title: "Embedding + reranking",
            body: "Indexed chunks use the configured embedding model for retrieval and the existing reranker for relevance ordering. Deterministic lexical matching remains the safe fallback when an index or model is unavailable.",
          },
          {
            title: "Preview and ownership",
            body: "Users can inspect processing state, extracted text, chunks, versions, and safe previews. Every read, download, sandbox input, and artifact output is checked against tenant and user ownership.",
          },
        ]}
      />

      <DocsSection title="Source-to-answer flow">
        <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-black/30 p-5 text-xs leading-6 text-slate-300">
          <code>{`upload → MIME/virus/archive checks → extract/OCR → chunks
       → embeddings + retrieval → reranking → cited answer
       → optional sandbox input or private artifact`}</code>
        </pre>
      </DocsSection>

      <DocsSection title="What users can do">
        <ol className="list-decimal space-y-2 pl-6">
          <li>
            Upload one or many supported files into Library and monitor each processing state.
          </li>
          <li>Open a safe preview or inspect extracted text before asking a question.</li>
          <li>
            Ask DeepSpace or Grounded Query for a summary, comparison, citation, or calculation.
          </li>
          <li>
            Send authorized files to the sandbox for bounded analysis and save the result as an
            artifact.
          </li>
        </ol>
      </DocsSection>
    </DocsShell>
  );
}
