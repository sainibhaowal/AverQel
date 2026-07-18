import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function EditorFilesDocsPage() {
  return (
    <DocsShell
      title="Editor & Files"
      intro="AverQel includes a full in-app workspace editor for notes, file-oriented agent work, math blocks, markdown import/export, and side-by-side chat-plus-notes workflows."
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
            title: "Active File Workflow",
            body: "When the runtime opens a file-oriented task, the editor can bind to an active file path and save changes back through the safe file workflow.",
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
          <li>markdown insertion from agent output</li>
          <li>HTML import and lossy HTML/Markdown export</li>
          <li>custom slash-menu insertion for math equations</li>
          <li>file-aware save actions when a task is bound to a real file path</li>
          <li>panel switching between chat, notes, split, and memory-oriented views</li>
        </ul>
      </DocsSection>

      <DocsSection title="Why this matters">
        <p>
          AverQel&apos;s editor is designed as a working surface, not only a passive note viewer.
          Agent output can become structured notes, draft content, file edits, or exportable
          deliverables in the same session.
        </p>
        <p>
          This is especially important for repo tasks, long research missions, and note-driven
          workflows where users need to move between live chat, generated structure, and editable
          content without context switching into another app.
        </p>
      </DocsSection>

      <DocsSection title="How it connects to agentic work">
        <p>
          The editor is wired into DeepSpace rather than isolated from it. The agent can stream
          output into notes, the user can refine the result, and file-aware tasks can save back to a
          selected path when the workflow allows it.
        </p>
        <p>In practice this means the editor can function as:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>a working notebook for research</li>
          <li>a draft memo surface for writing missions</li>
          <li>a file review pane during coding or config tasks</li>
          <li>an exportable deliverable workspace for final output</li>
        </ul>
      </DocsSection>

      <DocsSection title="What this is not">
        <p>
          The editor is not only a lightweight markdown viewer. It is a live productivity surface
          that sits beside chat and memory, accepts streamed content, supports equations and rich
          formatting, and can participate in file-oriented workflows.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
