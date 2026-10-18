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
      <DocsSection title="Review citations and previews">
        <p>
          Open a citation to see a format-aware preview of its source. PDFs and Office files
          supported by the server&apos;s LibreOffice renderer can be viewed page by page; other
          files use the matching table, media, or text preview when their content is available.
          Large CSV files load in bounded row pages so the browser does not need to display the
          whole file at once. If a visual renderer is unavailable, Query reports that and keeps the
          available format preview accessible.
        </p>
      </DocsSection>
      <DocsSection title="Ask exact questions about CSV and TSV files">
        <p>
          CSV and TSV attachments use the same saved, security-scanned file in Documents Hub. If an
          accessible copy already exists, Query attaches it by its document ID without uploading a
          duplicate. After the normal Documents Hub indexing finishes, a separate Grounded Query
          worker builds a complete table index and shows its stage and progress in the composer.
        </p>
        <p>
          Grounded Query accepts tables up to 25 MiB, 1,000,000 data rows, and 256 columns. It
          rejects malformed or over-limit files instead of silently leaving rows out. Ask for
          calculations such as counts, sums, averages, filters, sorting, or grouped results. Those
          operations run against the full indexed table; retrieval supplies explanations and source
          context. The model that plans a table operation receives the schema, not every table cell.
        </p>
        <p>
          Answers cite the file and show the matching-row count plus source-row examples. Open a
          citation to inspect the table, page through 100 rows, or jump directly to a source row.
          Row 1 contains the column names.
        </p>
      </DocsSection>
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
      <DocsSection title="Choose a model and attach files">
        <ol className="list-decimal space-y-2 pl-6">
          <li>
            Search the model menu and choose an available chat model under its provider. Each
            provider row shows its icon, and opening another provider closes the current one.
          </li>
          <li>
            Use the paperclip to upload files. They follow the normal Documents Hub security and
            indexing process. Uploads continue while you move between pages in the same open app
            window or browser tab. Documents Hub shows the in-progress upload live, then replaces it
            with the saved document and its normal indexing status after acceptance. The temporary
            upload row is not restored after a full page reload. Wait until each file shows Ready
            before sending your question.
          </li>
          <li>
            Attachments are included with the selected document or Qel Connect scope, and answers
            continue to use the existing grounded retrieval and citation path.
          </li>
          <li>
            While an answer is streaming, send another prompt to add it to the session queue. You
            can pause or resume the queue, remove queued prompts, or stop the current answer. Queued
            prompts are limited to 20. If an answer fails, the queue pauses and keeps that prompt
            available to retry before later prompts continue. Queued prompts are cleared when you
            switch conversations and are not saved across page sessions.
          </li>
        </ol>
        <p className="text-muted-foreground mt-3 text-sm">
          Removing an attachment from the composer only detaches it from that query. The uploaded
          source remains in Documents Hub, where its existing retention and deletion controls apply.
        </p>
      </DocsSection>
      <DocsSection title="Limits and availability">
        <p>
          Answer quality depends on the source content, extraction/OCR, indexing, retrieval
          settings, and configured model provider. A citation shows what the answer references; it
          does not prove that the source itself is correct or that the response is complete.
          Provider and search failures may make some paths unavailable. CSV and TSV files above the
          published size, row, or column limits, or with malformed rows, are rejected and must be
          corrected before Query can use them.
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
