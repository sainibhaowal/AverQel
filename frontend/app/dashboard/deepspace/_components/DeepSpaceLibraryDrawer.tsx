"use client";

import { ArrowLeft, FileCode2, FileText, FolderOpen, Loader2, Save, X } from "lucide-react";
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

export default function DeepSpaceLibraryDrawer({
  open,
  conversationId,
  onClose,
}: DeepSpaceLibraryDrawerProps) {
  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [selected, setSelected] = useState<LibraryFile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState("");
  const [drawerWidth, setDrawerWidth] = useState(320);

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

  const selectedLabel = useMemo(() => selected?.name ?? "DeepSpace Library", [selected]);
  if (!open) return null;

  return (
    <div
      className="absolute inset-y-0 left-0 z-50 flex max-w-[92vw] min-w-[16rem] flex-col border-r border-cyan-300/15 bg-[#07100d]/95 shadow-[24px_0_70px_rgba(0,0,0,0.45)] backdrop-blur-xl"
      style={{ width: drawerWidth }}
    >
      <div
        role="separator"
        aria-label="Resize DeepSpace Library"
        onPointerDown={(event) => {
          event.preventDefault();
          const startX = event.clientX;
          const startWidth = drawerWidth;
          const resize = (move: PointerEvent) => {
            const maximum = Math.min(680, Math.floor(window.innerWidth * 0.92));
            setDrawerWidth(Math.max(256, Math.min(maximum, startWidth + move.clientX - startX)));
          };
          const stop = () => {
            window.removeEventListener("pointermove", resize);
            window.removeEventListener("pointerup", stop);
          };
          window.addEventListener("pointermove", resize);
          window.addEventListener("pointerup", stop);
        }}
        className="absolute inset-y-0 right-0 z-10 w-1 cursor-col-resize bg-cyan-300/0 transition hover:bg-cyan-300/40"
      />
      <header className="flex items-center justify-between border-b border-white/8 px-3 py-3">
        <div className="flex min-w-0 items-center gap-2 text-xs font-semibold text-cyan-50">
          {selected ? (
            <button
              type="button"
              onClick={() => {
                setSelected(null);
                setDraft("");
              }}
              aria-label="Back to files"
              className="text-foreground/60 rounded-md p-1 hover:bg-white/5 hover:text-cyan-100"
            >
              <ArrowLeft size={14} />
            </button>
          ) : (
            <FolderOpen size={15} className="shrink-0 text-cyan-300" />
          )}
          <span className="truncate">{selectedLabel}</span>
        </div>
        <div className="flex items-center gap-1">
          {selected ? (
            <button
              type="button"
              disabled={saving}
              onClick={() => void saveFile()}
              className="inline-flex items-center gap-1 rounded-lg border border-emerald-300/20 bg-emerald-300/[0.08] px-2 py-1 text-[10px] font-semibold text-emerald-100 disabled:opacity-50"
            >
              <Save size={12} /> Save
            </button>
          ) : null}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close library"
            className="text-foreground/50 hover:text-foreground rounded-md p-1 hover:bg-white/5"
          >
            <X size={15} />
          </button>
        </div>
      </header>
      {selected ? (
        <section className="custom-scrollbar min-h-0 flex-1 overflow-auto p-3">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
            className="text-foreground/85 min-h-56 w-full resize-y rounded-xl border border-white/10 bg-black/20 p-3 font-mono text-xs leading-6 outline-none focus:border-cyan-300/35"
          />
          <div className="mt-4 border-t border-white/8 pt-3">
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
        </section>
      ) : (
        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-2">
          {loading && !files.length ? (
            <div className="flex justify-center p-5">
              <Loader2 size={16} className="animate-spin text-cyan-300" />
            </div>
          ) : null}
          {files.length === 0 && !loading ? (
            <p className="text-foreground/45 px-2 py-4 text-center text-[11px] leading-5">
              Save a named copy from the note editor, or ask DeepSpace to create a named file.
            </p>
          ) : null}
          {files.map((file) => (
            <button
              key={file.id}
              type="button"
              onClick={() => void selectFile(file)}
              className="text-foreground/65 mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[11px] transition hover:bg-white/[0.045] hover:text-cyan-50"
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
      )}
    </div>
  );
}
