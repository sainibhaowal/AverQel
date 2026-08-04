"use client";

import { FileCode2, FileText, FolderOpen, Loader2, Plus, Save, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { fetchWithAuth } from "@/lib/api";

import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";

type LibraryFile = {
  id: string;
  name: string;
  content_type: string;
  source: string;
  size_bytes: number;
  content?: string | null;
};

type DeepSpaceLibraryDrawerProps = {
  open: boolean;
  conversationId: string | null;
  onClose: () => void;
};

function defaultNameForType(type: "markdown" | "text" | "code") {
  if (type === "code") return "untitled.py";
  if (type === "text") return "untitled.txt";
  return "untitled.md";
}

export default function DeepSpaceLibraryDrawer({
  open,
  conversationId,
  onClose,
}: DeepSpaceLibraryDrawerProps) {
  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [selected, setSelected] = useState<LibraryFile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newType, setNewType] = useState<"markdown" | "text" | "code">("markdown");
  const [newName, setNewName] = useState("untitled.md");
  const [draft, setDraft] = useState("");

  const selectedIsMarkdown =
    selected?.content_type === "text/markdown" || selected?.name.endsWith(".md");

  const refresh = async () => {
    if (!conversationId) return;
    setLoading(true);
    try {
      const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/files`, {
        timeoutMs: 8_000,
      })) as Response;
      if (!response.ok) return;
      const nextFiles = (await response.json()) as LibraryFile[];
      setFiles(nextFiles);
      setSelected(
        (current) =>
          nextFiles.find((file) => file.id === current?.id) ?? current ?? nextFiles[0] ?? null,
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void refresh();
  }, [open, conversationId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const handleLibraryChanged = () => {
      if (open) void refresh();
    };
    window.addEventListener("deepspace-library-changed", handleLibraryChanged);
    return () => window.removeEventListener("deepspace-library-changed", handleLibraryChanged);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectFile = async (file: LibraryFile) => {
    setSelected(file);
    if (!conversationId) {
      setDraft("");
      return;
    }
    setLoading(true);
    try {
      const response = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/files/${file.id}`,
        { timeoutMs: 8_000 },
      )) as Response;
      if (!response.ok) return;
      const detail = (await response.json()) as LibraryFile;
      setSelected(detail);
      setDraft(detail.content ?? "");
    } finally {
      setLoading(false);
    }
  };

  const createFile = async () => {
    if (!conversationId || !newName.trim()) return;
    setSaving(true);
    try {
      const contentType =
        newType === "markdown"
          ? "text/markdown"
          : newType === "code"
            ? "text/x-python"
            : "text/plain";
      const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/files`, {
        method: "POST",
        body: JSON.stringify({ name: newName.trim(), content: "", content_type: contentType }),
      })) as Response;
      if (!response.ok) return;
      const file = (await response.json()) as LibraryFile;
      setCreating(false);
      setDraft("");
      await refresh();
      setSelected(file);
    } finally {
      setSaving(false);
    }
  };

  const saveFile = async () => {
    if (!conversationId || !selected) return;
    setSaving(true);
    try {
      const response = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/files/${selected.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ content: draft }),
        },
      )) as Response;
      if (!response.ok) return;
      const file = (await response.json()) as LibraryFile;
      setSelected(file);
      await refresh();
    } finally {
      setSaving(false);
    }
  };

  const selectedLabel = useMemo(() => selected?.name ?? "Select a file", [selected]);
  if (!open) return null;

  return (
    <div className="absolute inset-y-0 left-0 z-50 flex w-full max-w-[min(92vw,52rem)] border-r border-cyan-300/15 bg-[#07100d]/95 shadow-[24px_0_70px_rgba(0,0,0,0.45)] backdrop-blur-xl">
      <aside className="flex w-56 shrink-0 flex-col border-r border-white/8 bg-black/15">
        <div className="flex items-center justify-between border-b border-white/8 px-3 py-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-cyan-50">
            <FolderOpen size={15} className="text-cyan-300" /> DeepSpace Library
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close library"
            className="text-foreground/50 hover:text-foreground rounded-md p-1 hover:bg-white/5"
          >
            <X size={15} />
          </button>
        </div>
        <div className="border-b border-white/8 p-2">
          <button
            type="button"
            onClick={() => {
              setCreating(true);
              setNewName(defaultNameForType(newType));
            }}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-cyan-300/20 bg-cyan-300/[0.07] px-2 py-2 text-[11px] font-semibold text-cyan-100 hover:bg-cyan-300/[0.12]"
          >
            <Plus size={13} /> New file
          </button>
        </div>
        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-2">
          {loading && !files.length ? (
            <div className="flex justify-center p-5">
              <Loader2 size={16} className="animate-spin text-cyan-300" />
            </div>
          ) : null}
          {files.length === 0 && !loading ? (
            <p className="text-foreground/45 px-2 py-4 text-center text-[11px] leading-5">
              No separate files yet. Create one here, or ask DeepSpace to create a named file.
            </p>
          ) : null}
          {files.map((file) => (
            <button
              key={file.id}
              type="button"
              onClick={() => void selectFile(file)}
              className={`mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[11px] transition ${selected?.id === file.id ? "bg-cyan-300/[0.12] text-cyan-50" : "text-foreground/65 hover:bg-white/[0.045]"}`}
            >
              {file.name.endsWith(".py") ||
              file.name.endsWith(".ts") ||
              file.name.endsWith(".js") ? (
                <FileCode2 size={14} className="shrink-0 text-violet-300" />
              ) : (
                <FileText size={14} className="shrink-0 text-cyan-300/80" />
              )}
              <span className="min-w-0 flex-1 truncate">{file.name}</span>
            </button>
          ))}
        </div>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-white/8 px-4 py-3">
          <div className="text-foreground/85 min-w-0 truncate text-xs font-semibold">
            {selectedLabel}
          </div>
          {selected ? (
            <button
              type="button"
              disabled={saving}
              onClick={() => void saveFile()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300/20 bg-emerald-300/[0.08] px-2.5 py-1.5 text-[10px] font-semibold text-emerald-100 disabled:opacity-50"
            >
              <Save size={12} /> Save
            </button>
          ) : null}
        </header>
        {creating ? (
          <div className="space-y-3 border-b border-white/8 p-4">
            <div className="text-[10px] font-semibold tracking-[0.16em] text-cyan-100/65 uppercase">
              New workspace file
            </div>
            <div className="flex gap-2">
              <select
                value={newType}
                onChange={(event) => {
                  const type = event.target.value as typeof newType;
                  setNewType(type);
                  setNewName(defaultNameForType(type));
                }}
                className="rounded-lg border border-white/10 bg-black/20 px-2 text-xs"
              >
                <option value="markdown">Markdown</option>
                <option value="text">Text</option>
                <option value="code">Code</option>
              </select>
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs outline-none focus:border-cyan-300/40"
              />
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void createFile()}
                disabled={saving}
                className="rounded-lg bg-cyan-300/15 px-3 py-1.5 text-xs text-cyan-50"
              >
                Create
              </button>
              <button
                type="button"
                onClick={() => setCreating(false)}
                className="text-foreground/55 rounded-lg px-3 py-1.5 text-xs hover:bg-white/5"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}
        <div className="custom-scrollbar min-h-0 flex-1 overflow-auto p-4">
          {selected ? (
            <>
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                spellCheck={false}
                className="text-foreground/85 min-h-[45%] w-full resize-y rounded-xl border border-white/10 bg-black/20 p-3 font-mono text-xs leading-6 outline-none focus:border-cyan-300/35"
              />
              <div className="mt-5 border-t border-white/8 pt-4">
                <div className="text-foreground/40 mb-2 text-[10px] font-semibold tracking-[0.14em] uppercase">
                  Preview
                </div>
                {selectedIsMarkdown ? (
                  <DeepSpaceMarkdownRenderer content={draft} />
                ) : (
                  <pre className="overflow-auto rounded-xl border border-white/10 bg-black/25 p-3 text-xs leading-6 text-cyan-100">
                    <code>{draft}</code>
                  </pre>
                )}
              </div>
            </>
          ) : (
            <div className="text-foreground/45 text-sm">Select a file to preview it.</div>
          )}
        </div>
      </section>
    </div>
  );
}
