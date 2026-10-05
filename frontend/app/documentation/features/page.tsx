import Link from "next/link";
import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function FeaturesPage() {
  return (
    <DocsShell
      title="Product overview"
      intro="AverQel is organized around distinct work areas. Use each area for its intended job; related capabilities and their limits are documented together below."
    >
      <DocsCards
        items={[
          {
            title: "Documents Hub",
            href: "/documentation/documents-hub",
            body: "Source-file upload, processing, OCR, previews, organization, versions, and controlled sharing.",
          },
          {
            title: "Query",
            href: "/documentation/grounded-query",
            body: "Retrieval-first questions with source references over documents available to your account.",
          },
          {
            title: "DeepSpace",
            href: "/documentation/deepspace",
            body: "Conversational research and productivity work with its own Library, editor, and optional tools.",
          },
          {
            title: "Collections",
            href: "/documentation/collections-sharing",
            body: "Explicit member invitations and shared content within collection access boundaries.",
          },
          {
            title: "Providers & MCP",
            href: "/documentation/providers",
            body: "Model providers and separately governed remote tool connections.",
          },
          {
            title: "Account & trust",
            href: "/documentation/workspace-settings",
            body: "Account security, sessions, storage, privacy actions, and notifications.",
          },
          {
            title: "Support & feedback",
            href: "/documentation/support",
            body: "Private ticket conversations and trackable feedback submissions.",
          },
        ]}
      />
      <DocsSection title="Keep the product areas distinct">
        <ul className="list-disc space-y-2 pl-6">
          <li>Documents Hub manages source documents and their ingestion lifecycle.</li>
          <li>Query retrieves evidence from accessible sources for focused questions.</li>
          <li>
            DeepSpace is the broader conversation surface; its Library holds working attachments and
            outputs.
          </li>
          <li>
            Collections share selected content with invited members under explicit access controls.
          </li>
          <li>
            Providers supply model or service capability; MCP connections provide separately
            permissioned remote tools.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Feature status">
        <p>
          Some features need a particular account role, provider credential, worker, scheduler,
          scanner, storage service, or external service. Read the linked guide for those
          prerequisites. The codebase documents the implementation; the deployment operator must
          publish current release and service status for a hosted environment.
        </p>
        <p>
          <Link className="text-primary underline" href="/documentation/architecture">
            Read the architecture overview
          </Link>{" "}
          for a high-level map, or open the specific product guide before relying on an optional
          capability.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
