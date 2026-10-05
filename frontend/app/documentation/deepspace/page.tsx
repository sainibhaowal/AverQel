import Link from "next/link";
import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function DeepSpaceDocsPage() {
  return (
    <DocsShell
      title="DeepSpace workspace"
      intro="DeepSpace is AverQel’s conversation-led workspace for research, writing, analysis, and continuing work. It brings the conversation and DeepSpace-owned working files together, while using optional providers and tools only when the deployment and user permissions allow them."
    >
      <DocsCards
        items={[
          {
            title: "Conversations",
            body: "Open and continue saved conversations. Responses may stream, and work that uses background execution can show queued or running state.",
          },
          {
            title: "Research & tools",
            body: "Configured web research, approved MCP tools, and other enabled capabilities can extend a conversation. Provider choice, policy, approvals, and service availability determine which actions can run.",
          },
          {
            title: "Working Library & notes",
            body: "DeepSpace has a Library and editor for files and deliverables associated with DeepSpace work. This is distinct from the source-file Documents Hub.",
          },
          {
            title: "Optional capabilities",
            body: "Sandbox execution, schedules, voice, and some integrations require additional services or credentials. See each guide for its limits and setup needs.",
          },
        ]}
      />
      <DocsSection title="Choose the right area">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Documents Hub:</strong> upload, inspect, organize, and manage source documents.
          </li>
          <li>
            <strong>Query:</strong> ask focused questions over accessible source documents and
            inspect cited evidence.
          </li>
          <li>
            <strong>DeepSpace:</strong> conduct broader conversational work and use supported tools,
            notes, or DeepSpace Library files when available.
          </li>
          <li>
            <strong>Collections:</strong> collaborate with invited members around explicitly shared
            content.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="DeepSpace guides">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <Link className="text-primary underline" href="/documentation/deepspace-library">
              DeepSpace Library
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/editor-files">
              Notes and editor
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/web-research">
              Web research
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/sandbox">
              Sandbox and data analysis
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/artifacts">
              Artifacts and exports
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/automation">
              Schedules and automation
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/memory-workspace">
              Memory
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/voice">
              Voice
            </Link>
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Availability and limits">
        <p>
          DeepSpace behavior depends on a configured model provider. Tool use is constrained by
          connection ownership, provider and tool policy, approval settings, and backend
          authorization. A model response is not itself proof that an external action completed;
          review the tool result or generated artifact status shown in the app.
        </p>
        <p>
          Durability and feature availability depend on the running API, database, workers, and any
          optional services used by a particular action. This guide does not claim a deployment is
          production-ready solely because the feature exists in the repository.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
