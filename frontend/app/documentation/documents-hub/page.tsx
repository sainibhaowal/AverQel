import Link from "next/link";
import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function DocumentsHubDocsPage() {
  return (
    <DocsShell
      title="Documents Hub"
      intro="Documents Hub is the managed source-file area of AverQel. Upload files, follow processing, inspect extracted content, organize documents, and control access to the sources you own or are allowed to use."
    >
      <DocsCards
        items={[
          {
            title: "Upload and process",
            body: "Files pass through validation, configured malware scanning, private storage, extraction or OCR, and indexing. Processing state and supported actions are shown in the Hub.",
          },
          {
            title: "Inspect sources",
            body: "Review safe previews, extracted text, processing details, and version information where available. A preview or extracted result is not a substitute for checking the original source.",
          },
          {
            title: "Find and organize",
            body: "Use search and available tags or folders to find documents. Additional saved views and automation depend on role permissions.",
          },
          {
            title: "Use the right workspace",
            body: "Documents Hub is the source document area. Ask retrieval-first questions in Query; use DeepSpace when you need a broader conversation and its separate working Library.",
          },
        ]}
      />
      <DocsSection title="Typical document lifecycle">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Upload a supported file through Documents Hub.</li>
          <li>
            Wait for validation, scanning, extraction/OCR, and indexing to finish; review any
            warning or failed state.
          </li>
          <li>Open the source to inspect its preview and extracted content.</li>
          <li>
            Use Query for source-backed questions, or attach an authorized file to DeepSpace when
            doing broader work.
          </li>
          <li>
            Use the Hub&apos;s organization and sharing controls only for files you are authorized
            to manage.
          </li>
        </ol>
      </DocsSection>
      <DocsSection title="Access and availability">
        <p>
          Access is decided by the authenticated API using tenant membership, ownership, sharing,
          and role permissions. Organization controls are not identical for every role: the current
          implementation distinguishes basic organization, editor capabilities, and administrator
          controls. A control that is absent or disabled can reflect role or deployment
          configuration.
        </p>
        <p>
          File processing depends on the deployment&apos;s API, workers, private object storage, and
          malware scanner. OCR and format conversion also depend on the configured extractors. Local
          source code alone does not prove these services are active in a hosted environment.
        </p>
      </DocsSection>
      <DocsSection title="Related guides">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <Link className="text-primary underline" href="/documentation/document-organization">
              Organization and collaboration
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/grounded-query">
              Grounded Query
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/deepspace">
              DeepSpace
            </Link>
          </li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
