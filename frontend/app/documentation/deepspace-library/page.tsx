import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function DeepSpaceLibraryDocsPage() {
  return (
    <DocsShell
      title="DeepSpace Library"
      intro="DeepSpace Library holds working files associated with DeepSpace conversations and analysis. It is separate from Documents Hub, which manages the user’s source document collection."
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
          <li>Use supported preview and extraction flows to inspect content.</li>
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
