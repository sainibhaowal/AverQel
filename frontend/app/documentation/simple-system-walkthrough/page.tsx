import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function SimpleSystemWalkthroughPage() {
  return (
    <DocsShell
      title="System walkthrough"
      intro="A plain-language map of how a source document moves through AverQel and where Query and DeepSpace fit."
    >
      <DocsSection title="Documents Hub to Query">
        <ol className="list-decimal space-y-3 pl-6">
          <li>You upload a source file in Documents Hub.</li>
          <li>
            The backend validates and stores the file, scans it, and extracts or OCRs supported
            content.
          </li>
          <li>Processing prepares authorized text for search and retrieval.</li>
          <li>
            You ask a focused question in Query; the answer provider receives retrieved context.
          </li>
          <li>Review the response and cited sources in the Query experience.</li>
        </ol>
      </DocsSection>
      <DocsSection title="Where DeepSpace fits">
        <p>
          DeepSpace is a separate conversation-led area for broader work. It can use configured
          providers and allowed tools, and it has its own Library for working files and outputs. A
          user can attach eligible files from a supported source, but this does not merge the two
          Libraries or change their access rules.
        </p>
      </DocsSection>
      <DocsSection title="Other workspace areas">
        <ul className="list-disc space-y-2 pl-6">
          <li>Collections provide explicit collaboration and sharing with invited members.</li>
          <li>
            Providers configure model runtimes; MCP connections configure separately permissioned
            remote tools.
          </li>
          <li>
            Account, trust, notifications, support, and feedback each have dedicated settings and
            access boundaries.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="A useful mental model">
        <p>
          Documents Hub manages sources. Query finds evidence in sources. DeepSpace helps you carry
          out broader work using a conversation and its own working Library. Collections share
          selected content with invited people. Backend authorization controls which data and tools
          each request may access.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
