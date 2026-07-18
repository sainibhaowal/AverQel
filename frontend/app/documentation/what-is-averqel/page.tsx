import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function WhatIsAverQelPage() {
  return (
    <DocsShell
      title="What Is AverQel?"
      intro="AverQel is a private document intelligence and autonomous agent platform for uploading, indexing, searching, streaming, and acting on your own data with grounded AI answers."
    >
      <DocsSection title="Core Idea">
        <p>
          AverQel turns private documents and connected apps into a searchable knowledge and action
          layer. It is not a public document library. Each user account owns its documents, chats,
          queries, notes, connectors, and personal providers, with sharing happening only through
          explicit product features such as collections.
        </p>
      </DocsSection>
      <DocsSection title="What It Does">
        <p>
          It processes documents, extracts text, creates retrievable chunks and embeddings, lets
          users ask questions, streams agent steps in DeepSpace, and returns answers grounded in
          source evidence. This is a server-processed SaaS workflow with application-level user
          isolation.
        </p>
      </DocsSection>
      <DocsSection title="What It Does Not Mean">
        <p>
          AverQel does not make every user&apos;s data visible to other users. Admin views are
          designed around metadata and operational controls, not casual reading of private user
          content, provider secrets, or normal chat/document bodies.
        </p>
      </DocsSection>
      <DocsSection title="What It Has Become">
        <p>
          AverQel now includes autonomous grounded chat, DeepSpace streaming, a proactive workspace,
          connector automation, durable task ledgers, and recurring rules. It is still
          tenant-isolated and approval-gated, but the platform is now designed to behave like a
          production-grade agent system rather than only a document assistant.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
