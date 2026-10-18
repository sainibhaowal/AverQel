import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function CollectionsSharingDocsPage() {
  return (
    <DocsShell
      title="Qel Connect & sharing"
      intro="Qel Connect provides an explicit membership boundary for sharing selected documents and collaborating with invited members. The feature is currently described by the repository as experimental beta; verify release and staging status for the deployment you use."
    >
      <DocsSection title="What Qel Connect is for">
        <ul className="list-disc space-y-2 pl-6">
          <li>Invite or connect members through an explicit accept/decline flow.</li>
          <li>Share selected documents by reference under Qel Connect permissions.</li>
          <li>Use Qel Connect chat, presence, notifications, and supported media features.</li>
          <li>Block a member or submit a report when the product offers those controls.</li>
        </ul>
        <p>
          A Qel Connect space is not a workspace-wide document browser. Membership and document
          access are enforced by the API; shared documents continue to use server-side storage and
          processing for features such as preview, OCR, and indexing.
        </p>
      </DocsSection>
      <DocsSection title="Encryption: important limits">
        <p>
          The client includes AES-GCM chat and media encryption code, and the API also has an
          optional sealed-chat mode. These are distinct layers. The current client derives its key
          from the Qel Connect ID and connection code, and the Qel Connect API returns that code to
          clients. The optional sealed-chat mode is explicitly server-mediated: the API can open
          messages for authorized members. Therefore the current implementation must not be
          represented as zero-knowledge, server-blind, or audited Signal/libsignal end-to-end
          encryption.
        </p>
        <p>
          Safety fingerprints are informational comparison values, not proof of an independently
          verified identity key or protection against an active server compromise. Do not use them
          as a security guarantee. Shared source documents are server-readable for normal product
          processing.
        </p>
      </DocsSection>
      <DocsSection title="Reports and moderation">
        <p>
          Members can submit reports about Qel Connect activity. The moderation queue is a
          restricted workflow for designated moderators. Each moderator can review only reports
          from the active tenant. The queue is not a feature for browsing users&apos; Qel Connect
          spaces or private chat histories. Report text loads only when a moderator opens a report;
          reads and decisions are recorded in the audit history.
        </p>
      </DocsSection>
      <DocsSection title="Retention and beta status">
        <p>
          Qel Connect chat has owner-controlled expiry and clear-history actions in the current
          implementation. Expiry cleanup is tied to the chat lifecycle and associated media cleanup;
          it should not be interpreted as immediate removal from every backup, device, export, or
          downstream copy. Check the product confirmation text before clearing history.
        </p>
        <p>
          Qel Connect is experimental beta until the release owner records deployment-specific
          staging, multi-account/device, recovery, and security evidence. Local tests or the
          presence of a page do not certify the hosted service.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
