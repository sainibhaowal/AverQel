import { DocsSection, DocsShell } from "../_components/DocsShell";

/** Kept as a compatibility URL; the guide now names its actual product area. */
export default function LibraryDocsPage() {
  return (
    <DocsShell
      title="Documents Hub: files, OCR & indexing"
      intro="Documents Hub processes source files for preview, search, and retrieval. OCR and format support depend on the file and configured extractors; processing state is shown in the product."
    >
      <DocsSection title="File processing">
        <p>
          An upload is validated before it is stored and processed. Depending on the format, the
          pipeline extracts native text or uses OCR, records processing information, and prepares
          searchable content. The status shown in Documents Hub is the source for whether a file is
          ready, still processing, or needs attention.
        </p>
      </DocsSection>
      <DocsSection title="Preview and retrieval">
        <p>
          Safe previews and extracted text help you inspect the content that is available to Query.
          OCR output, text extraction, embeddings, and search quality vary by document and runtime
          configuration. Confirm important results against the original page or file.
        </p>
      </DocsSection>
      <DocsSection title="Supported formats and deployment services">
        <p>
          The accepted formats are determined by the upload interface and backend extractor
          registry. Legacy Office conversion and some OCR paths require their configured worker or
          converter. Malware scanning and private object storage are required parts of the
          production upload path; a deployment that lacks required services should not be assumed to
          be production-ready.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
