import Link from "next/link";
import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function GettingStartedPage() {
  return (
    <DocsShell
      title="Getting started"
      intro="Start with the workspace basics, then choose the product area that matches the work you want to do. Provider and optional-service setup depends on your deployment."
    >
      <DocsCards
        items={[
          {
            title: "1. Secure your account",
            body: "Use a strong sign-in password and configure two-factor authentication if it is available to your account.",
          },
          {
            title: "2. Add source documents",
            body: "Open Documents Hub, upload a supported file, and wait for scanning, extraction, and indexing to finish.",
          },
          {
            title: "3. Ask a grounded question",
            body: "Use Query for focused questions about sources you can access, then inspect the returned citations and source context.",
          },
          {
            title: "4. Continue work in DeepSpace",
            body: "Use DeepSpace for broader research, drafting, analysis, or ongoing conversation. Its working Library is separate from Documents Hub.",
          },
          {
            title: "5. Connect optional tools",
            body: "Set up an AI provider or supported MCP connection only when needed and when your account and deployment expose the required controls.",
          },
          {
            title: "6. Get help",
            body: "Open Support Centre for an issue, or Share Feedback for suggestions and product feedback.",
          },
        ]}
      />
      <DocsSection title="Choose your next guide">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <Link className="text-primary underline" href="/documentation/documents-hub">
              Documents Hub
            </Link>{" "}
            for source files and processing.
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/grounded-query">
              Grounded Query
            </Link>{" "}
            for document-based questions.
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/deepspace">
              DeepSpace
            </Link>{" "}
            for broader work and its related tools.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Provider setup">
        <p>
          A configured model provider is required for AI-generated answers. Depending on the
          deployment, provider setup may be managed by an administrator or exposed in your account
          settings. Adding a provider does not by itself guarantee that a model is reachable or
          enabled for every feature; use the available status or test controls and contact your
          administrator if setup is restricted.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
