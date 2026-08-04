"use client";

import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import type { Extension } from "@codemirror/state";
import CodeMirror from "@uiw/react-codemirror";
import { Code2, Eye, PanelLeft, PencilLine } from "lucide-react";
import { useMemo, useState } from "react";

import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";

type PreviewMode = "edit" | "split" | "preview";

function languageForFile(name: string, contentType: string): Extension[] {
  const extension = name.split(".").pop()?.toLowerCase();
  if (contentType === "text/markdown" || extension === "md" || extension === "mdx") {
    return [markdown()];
  }
  if (contentType === "application/json" || extension === "json") return [json()];
  if (contentType === "text/x-python" || extension === "py") return [python()];
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
  const isMarkdown = contentType === "text/markdown" || name.endsWith(".md");
  const [mode, setMode] = useState<PreviewMode>(isMarkdown ? "split" : "edit");
  const extensions = useMemo(() => languageForFile(name, contentType), [contentType, name]);
  const editorVisible = !isMarkdown || mode !== "preview";
  const previewVisible = isMarkdown && mode !== "edit";

  return (
    <section className="min-h-0 flex-1 overflow-hidden rounded-xl border border-white/10 bg-black/15">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-white/8 bg-white/[0.025] px-2.5 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Code2 size={13} className="shrink-0 text-cyan-300" />
          <span className="truncate font-mono text-[10px] text-cyan-50">{name}</span>
          <span className="text-foreground/45 rounded border border-white/10 bg-black/20 px-1.5 py-0.5 text-[9px] font-semibold tracking-[0.1em] uppercase">
            {languageLabel(name, contentType)}
          </span>
        </div>
        {isMarkdown ? (
          <div className="flex items-center rounded-lg border border-white/10 bg-black/20 p-0.5 text-[10px]">
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
                    ? "bg-cyan-300/15 text-cyan-100"
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
        className={`min-h-[26rem] ${
          editorVisible && previewVisible
            ? "grid grid-cols-1 divide-y divide-white/10 lg:grid-cols-2 lg:divide-x lg:divide-y-0"
            : ""
        }`}
      >
        {editorVisible ? (
          <div className="min-w-0 bg-[#06100d]">
            <CodeMirror
              value={value}
              height="26rem"
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
              className="h-full text-xs [&_.cm-editor]:h-full [&_.cm-editor]:outline-none [&_.cm-gutters]:border-r-white/10 [&_.cm-gutters]:bg-black/20"
            />
          </div>
        ) : null}
        {previewVisible ? (
          <div className="custom-scrollbar max-h-[26rem] min-w-0 overflow-auto bg-[#08120f] p-4 text-sm">
            <DeepSpaceMarkdownRenderer content={value} />
          </div>
        ) : null}
      </div>
    </section>
  );
}
