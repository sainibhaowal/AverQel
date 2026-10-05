import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function WhatIsAverQelPage() {
  return (
    <DocsShell
      title="What is AverQel?"
      intro="AverQel is an open-source AI workspace for working with documents, asking evidence-backed questions, and carrying out broader research and productivity work with connected tools."
    >
      <DocsCards
        items={[
          {
            title: "Documents Hub",
            body: "Manage source files, processing, previews, organization, and authorized sharing.",
          },
          {
            title: "Query",
            body: "Ask focused questions over documents you can access and inspect the sources used in the answer.",
          },
          {
            title: "DeepSpace",
            body: "Continue broader conversational work with a separate working Library, notes, and optional tools.",
          },
          {
            title: "Connected workspace",
            body: "Configure supported AI providers and remote MCP connections; each integration has its own permission and setup requirements.",
          },
        ]}
      />
      <DocsSection title="How the areas fit together">
        <p>
          Documents Hub is where source files are managed. Query is retrieval-first and centers its
          work on those sources. DeepSpace is a broader conversation workspace and has its own
          Library for working attachments and outputs. Collections provide explicit sharing with
          invited members. Providers and MCP connections extend model and tool options when they are
          configured and authorized.
        </p>
      </DocsSection>
      <DocsSection title="Data and privacy model">
        <p>
          AverQel processes account data through its application backend and configured services.
          Authentication, tenant boundaries, role permissions, and integration policies control
          access. Some workflows intentionally allow authorized support staff to read submitted
          support or feedback content; collection chat encryption also has limitations documented in
          its guide. Do not assume that all workspace content is client-only or end-to-end
          encrypted.
        </p>
      </DocsSection>
      <DocsSection title="Availability is deployment-specific">
        <p>
          The open-source repository contains optional services and integrations. A feature is
          available in a deployment only when its version, configuration, credentials, workers, and
          dependent services are present and healthy. Release notes and deployment evidence—not a
          source page alone—establish what is live.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
