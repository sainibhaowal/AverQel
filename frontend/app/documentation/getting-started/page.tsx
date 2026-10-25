import Link from "next/link";
import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function GettingStartedPage() {
  return (
    <DocsShell
      title="Getting started"
      intro="New accounts can take a short welcome tour after signing in. Choose a profile name and appearance, connect a provider if you want, or skip the tour and start using the workspace."
    >
      <DocsCards
        items={[
          {
            title: "1. Add source documents",
            body: "Open Documents Hub, upload a supported file, and wait for scanning, extraction, and indexing to finish.",
          },
          {
            title: "2. Ask a grounded question",
            body: "Use Query for focused questions about sources you can access, then inspect the returned citations and source context.",
          },
          {
            title: "3. Continue work in DeepSpace",
            body: "Use DeepSpace for broader research, drafting, analysis, or ongoing conversation. Its working Library is separate from Documents Hub.",
          },
          {
            title: "4. Connect optional tools",
            body: "Set up an AI provider or supported MCP connection only when needed and when your account and deployment expose the required controls.",
          },
          {
            title: "5. Personalize your profile",
            body: "Open the account menu to update your display name and avatar, review account status and two-factor authentication, or open provider settings.",
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
        <p>
          The welcome flow can save a named provider connection after discovering and selecting a
          chat model. Cloud provider keys are handled by the existing encrypted credential store.
          Ollama and LM Studio must be reachable from the configured AverQel API service. For a
          hosted AverQel web account, a URL such as localhost points to that server, not to your
          browser computer. ChatGPT or Codex CLI sign-in is available through AverQel Desktop and
          its provider settings.
        </p>
      </DocsSection>
      <DocsSection title="Google and GitHub sign-in on desktop">
        <p>
          AverQel Desktop opens Google or GitHub sign-in in a compact separate window and returns
          to the AverQel login page when sign-in finishes. Closing that window cancels sign-in; you
          can retry or use email and password.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
