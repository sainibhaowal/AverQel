import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function DeepSpaceLibraryDocsPage() {
  return (
    <DocsShell
      title="DeepSpace Library"
      intro="DeepSpace Library holds working files associated with DeepSpace conversations and analysis. It is separate from Documents Hub, which manages the user’s source documents."
    >
      <DocsSection title="What belongs here">
        <p>
          Files uploaded through the DeepSpace composer or saved from DeepSpace work can be managed
          in the DeepSpace Library. The Library drawer is scoped to the relevant conversation and
          shows the files and folders available to that user in that workspace. DeepSpace
          attachments use authenticated file references; they do not authorize arbitrary host paths
          or public URLs.
        </p>
      </DocsSection>
      <DocsSection title="Working with files">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Browse folders and files, upload working material, and attach authorized files to a
            conversation.
          </li>
          <li>
            Files added from the composer get their own Library ID. If a composer upload repeats a
            name already in that folder, DeepSpace adds a suffix such as <code>(2)</code> so both
            files can be kept and attached separately.
          </li>
          <li>Use supported preview and extraction flows to inspect content.</li>
          <li>
            PDF files open in the in-app viewer. When LibreOffice is installed, Writer, Calc,
            Impress, and Draw files can be converted to a visual PDF preview. Small XLSX files keep
            the interactive table view; other supported spreadsheet formats use the PDF preview.
            PNG, JPEG, BMP, GIF, TIFF, and WebP images are resized for preview, while SVG and AVIF
            use browser image rendering. GIF and multi-page TIFF previews show their first frame or
            page.
          </li>
          <li>
            Image OCR is processed in the background for PNG, JPG/JPEG, TIFF, WebP, BMP, and GIF.
            AVIF and SVG can be previewed but are not in the image OCR extractor. Very large files
            or images can exceed safe preview limits; in that case, use the original download or any
            extracted text that is available.
          </li>
          <li>
            If a file or preview cannot be loaded, use the Retry action shown in the Library. The
            file list also refreshes periodically while the Library is open and the tab is visible.
          </li>
          <li>Move or organize files within the Library and review available versions.</li>
          <li>
            Save generated artifacts to an authenticated, user-scoped Library record when the
            workflow supports it.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Dataset analysis">
        <p>
          Supported data files can be used by DeepSpace analysis flows that are enabled on the
          deployment. The backend exposes bounded dataset operations such as filtering, aggregation,
          chart preparation, and supported joins. Results depend on file format, size limits, the
          selected analysis tool, and deployment configuration. Use the Sandbox guide for execution
          isolation and limits; do not treat every Library file as executable or queryable data.
        </p>
      </DocsSection>
      <DocsSection title="How it differs from Documents Hub">
        <p>
          Documents Hub is the managed source-file and indexing area used by Query and other product
          flows. DeepSpace Library is the working area for files attached to or produced by
          DeepSpace activity. They have separate routes and access checks. A copy or attachment in
          one area does not imply that permissions, retention, or indexing are shared with the
          other.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
