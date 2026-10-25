import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function EditorFilesDocsPage() {
  return (
    <DocsShell
      title="Notes & Deliverables"
      intro="AverQel includes a full in-app workspace editor for notes, research drafts, math blocks, markdown import/export, and side-by-side chat-plus-notes workflows."
    >
      <DocsCards
        items={[
          {
            title: "Block-Based Editor",
            body: "The DeepSpace editor is not just a text box. It uses a block editor with markdown import, HTML import, rich block output, and custom math equation blocks.",
          },
          {
            title: "Panel Modes",
            body: "Users can work in split, notes-only, chat-only, or memory-oriented panel layouts so conversation and drafting stay connected.",
          },
          {
            title: "Export Surface",
            body: "DeepSpace notes can be exported to PDF, DOCX, or Markdown from the same workspace without leaving the app.",
          },
        ]}
      />

      <DocsSection title="What the editor actually supports">
        <ul className="list-disc space-y-2 pl-6">
          <li>rich block editing for working notes and generated drafts</li>
          <li>combined inline formatting and hyperlinks in saved notes</li>
          <li>markdown insertion from chat output</li>
          <li>HTML import and lossy HTML/Markdown export</li>
          <li>custom slash-menu insertion for math equations</li>
          <li>server autosave with recovery for pending drafts in the current tab</li>
          <li>panel switching between chat, notes, split, and memory-oriented views</li>
        </ul>
      </DocsSection>

      <DocsSection title="Note saving and draft recovery">
        <p>
          Note edits are copied to temporary storage in the current browser tab immediately, then
          autosaved to the note&apos;s authoritative storage after you pause typing. The editor
          shows <strong>Saving</strong> while the write is pending and <strong>Saved</strong> only
          after that storage confirms it. If the storage client or server cannot confirm the save,
          the toolbar says <strong>Saved on this tab</strong> when a recovery copy is available, and
          offers a retry.
        </p>
        <p>
          Pending drafts are restored when you reopen the note in the same tab, including after a
          refresh or sign-in flow. If the saved conversation changed since the draft was made, the
          editor asks whether to restore the local draft or discard it; it never silently replaces
          the newer saved version. If a newer recovery copy exists than the connected device&apos;s
          note, DeepSpace opens that copy and restores it on the next confirmed edit if the note has
          not changed in the meantime. Tab recovery is device- and tab-specific, so wait for{" "}
          <strong>Saved</strong> before closing the tab or switching devices.
        </p>
      </DocsSection>

      <DocsSection title="Why this matters">
        <p>
          AverQel&apos;s editor is designed as a working surface, not only a passive note viewer.
          Agent output can become structured notes, draft content, or exportable deliverables in the
          same session.
        </p>
        <p>
          This is especially important for long research missions and note-driven workflows where
          users need to move between live chat, generated structure, and editable content without
          context switching into another app.
        </p>
      </DocsSection>

      <DocsSection title="How it connects to chat">
        <p>
          The editor is wired into DeepSpace rather than isolated from it. Chat can stream output
          into notes, and the user can refine the result into a durable deliverable.
        </p>
        <p>In practice this means the editor can function as:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>a working notebook for research</li>
          <li>a draft memo surface for writing</li>
          <li>an exportable deliverable workspace for final output</li>
        </ul>
      </DocsSection>

      <DocsSection title="What this is not">
        <p>
          The editor is not only a lightweight markdown viewer. It is a live productivity surface
          that sits beside chat and memory, accepts streamed content, supports equations and rich
          formatting, and can participate in research and productivity workflows.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
