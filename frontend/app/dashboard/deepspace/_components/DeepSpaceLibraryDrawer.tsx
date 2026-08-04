"use client";

import {
  ArrowLeft,
  Check,
  FileCode2,
  FileText,
  FolderOpen,
  Loader2,
  Pencil,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { fetchWithAuth } from "@/lib/api";

import DeepSpaceLibraryFileWorkspace from "./DeepSpaceLibraryFileWorkspace";

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
  embedded?: boolean;
  conversationId: string | null;
  onClose: () => void;
};

export default function DeepSpaceLibraryDrawer({
  open,
  embedded = false,
  conversationId,
  onClose,
}: DeepSpaceLibraryDrawerProps) {
  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [selected, setSelected] = useState<LibraryFile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState("");
  const [drawerWidth, setDrawerWidth] = useState(320);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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

  const startRename = (file: LibraryFile) => {
    setActionError(null);
    setRenamingId(file.id);
    setRenameValue(file.name);
  };

  const renameFile = async (file: LibraryFile) => {
    const name = renameValue.trim();
    if (!conversationId || !name) return;
    if (!name.includes(".")) {
      setActionError("Include a file extension, for example notes.md.");
      return;
    }

    setSaving(true);
    setActionError(null);
    try {
      const response = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/files/${file.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ name }),
        },
      )) as Response;
      if (!response.ok) {
        setActionError("That name could not be saved. Choose a different valid filename.");
        return;
      }
      const renamed = (await response.json()) as LibraryFile;
      setSelected((current) => (current?.id === renamed.id ? { ...current, ...renamed } : current));
      setRenamingId(null);
      await refresh();
    } finally {
      setSaving(false);
    }
  };

  const deleteFile = async (file: LibraryFile) => {
    if (!conversationId) return;
    const confirmed = window.confirm(`Delete ${file.name}? This cannot be undone.`);
    if (!confirmed) return;

    setDeletingId(file.id);
    setActionError(null);
    try {
      const response = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/files/${file.id}`,
        { method: "DELETE" },
      )) as Response;
      if (!response.ok) {
        setActionError("The file could not be deleted. Please try again.");
        return;
      }
      if (selected?.id === file.id) {
        setSelected(null);
        setDraft("");
      }
      await refresh();
    } finally {
      setDeletingId(null);
    }
  };

  const selectedLabel = useMemo(() => selected?.name ?? "DeepSpace Library", [selected]);
  if (!open) return null;

  return (
    <div
      className={
        embedded
          ? "relative flex h-full w-full min-w-0 flex-col overflow-hidden bg-[#07100d]/95"
          : "absolute inset-y-0 left-0 z-50 flex max-w-[92vw] min-w-[16rem] flex-col border-r border-cyan-300/15 bg-[#07100d]/95 shadow-[24px_0_70px_rgba(0,0,0,0.45)] backdrop-blur-xl"
      }
      style={embedded ? undefined : { width: drawerWidth }}
    >
      {!embedded ? (
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
      ) : null}
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
          <DeepSpaceLibraryFileWorkspace
            name={selected.name}
            contentType={selected.content_type}
            value={draft}
            onChange={setDraft}
          />
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
          {actionError ? (
            <p className="mb-2 rounded-lg border border-rose-300/15 bg-rose-300/[0.06] px-2 py-1.5 text-[10px] leading-4 text-rose-200">
              {actionError}
            </p>
          ) : null}
          {files.map((file) => (
            <div key={file.id} className="mb-1 rounded-lg hover:bg-white/[0.045]">
              <div className="flex items-center gap-0.5">
                <button
                  type="button"
                  onClick={() => void selectFile(file)}
                  className="text-foreground/65 flex min-w-0 flex-1 items-center gap-2 rounded-l-lg px-2 py-2 text-left text-[11px] transition hover:text-cyan-50"
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
                <button
                  type="button"
                  onClick={() => startRename(file)}
                  aria-label={`Rename ${file.name}`}
                  title="Rename file"
                  className="text-foreground/40 rounded-md p-1.5 transition hover:bg-cyan-300/10 hover:text-cyan-100"
                >
                  <Pencil size={12} />
                </button>
                <button
                  type="button"
                  disabled={deletingId === file.id}
                  onClick={() => void deleteFile(file)}
                  aria-label={`Delete ${file.name}`}
                  title="Delete file"
                  className="text-foreground/40 mr-1 rounded-md p-1.5 transition hover:bg-rose-300/10 hover:text-rose-200 disabled:opacity-40"
                >
                  {deletingId === file.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Trash2 size={12} />
                  )}
                </button>
              </div>
              {renamingId === file.id ? (
                <form
                  className="flex gap-1 px-2 pb-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void renameFile(file);
                  }}
                >
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(event) => setRenameValue(event.target.value)}
                    aria-label="New file name"
                    className="min-w-0 flex-1 rounded-md border border-cyan-300/25 bg-black/25 px-2 py-1 text-[11px] text-cyan-50 outline-none focus:border-cyan-300/60"
                  />
                  <button
                    type="submit"
                    disabled={saving}
                    aria-label="Save new file name"
                    className="rounded-md border border-emerald-300/20 bg-emerald-300/[0.08] p-1 text-emerald-100 disabled:opacity-50"
                  >
                    <Check size={13} />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setRenamingId(null);
                      setActionError(null);
                    }}
                    aria-label="Cancel rename"
                    className="text-foreground/45 hover:text-foreground rounded-md p-1 hover:bg-white/5"
                  >
                    <X size={13} />
                  </button>
                </form>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
