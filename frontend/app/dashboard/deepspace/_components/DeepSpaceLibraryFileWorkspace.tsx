"use client";

import { cpp } from "@codemirror/lang-cpp";
import { css } from "@codemirror/lang-css";
import { go } from "@codemirror/lang-go";
import { java } from "@codemirror/lang-java";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { rust } from "@codemirror/lang-rust";
import { sql } from "@codemirror/lang-sql";
import { xml } from "@codemirror/lang-xml";
import { yaml } from "@codemirror/lang-yaml";
import { RangeSetBuilder, StateField, type Extension } from "@codemirror/state";
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view";
import CodeMirror from "@uiw/react-codemirror";
import { Code2, Eye, PanelLeft, PencilLine } from "lucide-react";
import { useMemo, useState } from "react";

import { LibraryPreview } from "./DeepSpaceLibraryPreview";
import {
  libraryFileKind,
  libraryKindSupportsEditor,
  libraryKindSupportsPreview,
} from "./DeepSpaceLibraryFormats";

type PreviewMode = "edit" | "split" | "preview";

function buildDiffDecorations(doc: {
  lines: number;
  line: (number: number) => { from: number; text: string };
}) {
  const builder = new RangeSetBuilder<Decoration>();
  for (let number = 1; number <= doc.lines; number += 1) {
    const line = doc.line(number);
    const className =
      line.text.startsWith("+++") ||
      line.text.startsWith("---") ||
      line.text.startsWith("diff ") ||
      line.text.startsWith("index ")
        ? "cm-diff-header"
        : line.text.startsWith("@@")
          ? "cm-diff-hunk"
          : line.text.startsWith("+")
            ? "cm-diff-added"
            : line.text.startsWith("-")
              ? "cm-diff-removed"
              : null;
    if (className)
      builder.add(line.from, line.from, Decoration.line({ attributes: { class: className } }));
  }
  return builder.finish();
}

const diffHighlighting: Extension[] = [
  StateField.define<DecorationSet>({
    create: (state) => buildDiffDecorations(state.doc),
    update: (decorations, transaction) =>
      transaction.docChanged ? buildDiffDecorations(transaction.state.doc) : decorations,
    provide: (field) => EditorView.decorations.from(field),
  }),
  EditorView.baseTheme({
    ".cm-diff-added": { backgroundColor: "rgba(52, 211, 153, 0.12)", color: "#bbf7d0" },
    ".cm-diff-removed": { backgroundColor: "rgba(251, 113, 133, 0.12)", color: "#fecdd3" },
    ".cm-diff-hunk": { backgroundColor: "rgba(34, 211, 238, 0.1)", color: "#a5f3fc" },
    ".cm-diff-header": { color: "#c4b5fd", fontWeight: "600" },
  }),
];

function languageForFile(name: string, contentType: string): Extension[] {
  const extension = name.split(".").pop()?.toLowerCase();
  if (contentType === "text/markdown" || extension === "md" || extension === "mdx") {
    return [markdown()];
  }
  if (contentType === "application/json" || extension === "json") return [json()];
  if (contentType === "text/x-python" || extension === "py") return [python()];
  if (extension === "diff" || extension === "patch") return diffHighlighting;
  if (extension === "yaml" || extension === "yml") return [yaml()];
  if (extension === "sql" || contentType === "text/sql" || contentType === "application/sql") {
    return [sql()];
  }
  if (extension === "xml" || ["html", "htm"].includes(extension ?? "")) return [xml()];
  if (extension === "css" || extension === "scss") return [css()];
  if (["java"].includes(extension ?? "")) return [java()];
  if (["c", "h", "cc", "cpp", "cxx", "hpp"].includes(extension ?? "")) return [cpp()];
  if (extension === "go") return [go()];
  if (extension === "rs") return [rust()];
  if (["js", "mjs", "cjs", "ts", "tsx", "jsx"].includes(extension ?? "")) {
    return [javascript({ typescript: ["ts", "tsx"].includes(extension ?? "") })];
  }
  return [];
}

function languageLabel(name: string, contentType: string) {
  const extension = name.split(".").pop()?.toUpperCase();
  return extension || contentType.replace("text/", "").replace("application/", "").toUpperCase();
}

export default function DeepSpaceLibraryFileWorkspace({
  name,
  contentType,
  value,
  onChange,
}: {
  name: string;
  contentType: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const kind = libraryFileKind(name, contentType);
  const editorSupported = libraryKindSupportsEditor(kind);
  const previewSupported = libraryKindSupportsPreview(kind);
  const defaultMode: PreviewMode =
    editorSupported && previewSupported ? "split" : editorSupported ? "edit" : "preview";
  const [mode, setMode] = useState<PreviewMode>(defaultMode);
  const extensions = useMemo(() => languageForFile(name, contentType), [contentType, name]);
  const editorVisible = editorSupported && mode !== "preview";
  const previewVisible = previewSupported && mode !== "edit";

  return (
    <section className="border-glass-border bg-surface-1/40 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border">
      <header className="border-glass-border bg-surface-1/60 flex shrink-0 flex-wrap items-center justify-between gap-2 border-b px-2.5 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Code2 size={13} className="text-primary shrink-0" />
          <span className="text-foreground truncate font-mono text-[10px]">{name}</span>
          <span className="border-glass-border bg-surface-0 text-foreground/45 rounded border px-1.5 py-0.5 text-[9px] font-semibold tracking-[0.1em] uppercase">
            {languageLabel(name, contentType)}
          </span>
        </div>
        {editorSupported && previewSupported ? (
          <div className="border-glass-border bg-surface-0/70 flex items-center rounded-lg border p-0.5 text-[10px]">
            {(
              [
                ["edit", PencilLine, "Edit"],
                ["split", PanelLeft, "Split"],
                ["preview", Eye, "Preview"],
              ] as const
            ).map(([nextMode, Icon, label]) => (
              <button
                key={nextMode}
                type="button"
                onClick={() => setMode(nextMode)}
                aria-pressed={mode === nextMode}
                className={`inline-flex items-center gap-1 rounded-md px-2 py-1 transition ${
                  mode === nextMode
                    ? "bg-primary/15 text-primary"
                    : "text-foreground/50 hover:text-foreground"
                }`}
              >
                <Icon size={11} /> {label}
              </button>
            ))}
          </div>
        ) : null}
      </header>
      <div
        className={`flex min-h-0 flex-1 ${
          editorVisible && previewVisible
            ? "divide-glass-border grid grid-cols-1 grid-rows-2 divide-y lg:grid-cols-2 lg:grid-rows-1 lg:divide-x lg:divide-y-0"
            : ""
        }`}
      >
        {editorVisible ? (
          <div className="bg-surface-0 min-h-0 min-w-0 flex-1">
            <CodeMirror
              value={value}
              height="100%"
              extensions={extensions}
              onChange={onChange}
              basicSetup={{
                lineNumbers: true,
                foldGutter: true,
                highlightActiveLine: true,
                bracketMatching: true,
                autocompletion: true,
                closeBrackets: true,
              }}
              theme="dark"
              className="[&_.cm-gutters]:border-r-glass-border [&_.cm-gutters]:bg-surface-1 h-full text-xs [&_.cm-editor]:h-full [&_.cm-editor]:outline-none"
            />
          </div>
        ) : null}
        {previewVisible ? (
          <div className="custom-scrollbar bg-surface-0 min-h-0 min-w-0 flex-1 overflow-auto p-4 text-sm">
            <LibraryPreview kind={kind} contentType={contentType} value={value} />
          </div>
        ) : null}
      </div>
    </section>
  );
}
