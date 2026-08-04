"use client";

import {
  ArrowLeft,
  Check,
  FileCode2,
  FileText,
  FolderOpen,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Save,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { fetchWithAuth } from "@/lib/api";

import ConfirmationModal from "@/app/components/ui/ConfirmationModal";

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

const LIBRARY_FILES_COLLAPSED_KEY = "deepspace.library.files.collapsed";

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
  const [isFilesCollapsed, setIsFilesCollapsed] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<LibraryFile | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!embedded) return;
    try {
      setIsFilesCollapsed(window.localStorage.getItem(LIBRARY_FILES_COLLAPSED_KEY) === "true");
    } catch {
      // Storage can be unavailable in privacy-restricted browser contexts.
    }
  }, [embedded]);

  const toggleFilesCollapsed = () => {
    setIsFilesCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(LIBRARY_FILES_COLLAPSED_KEY, String(next));
      } catch {
        // Keep the in-memory toggle working when storage is unavailable.
      }
      return next;
    });
  };

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

  const deleteFile = async (file: LibraryFile): Promise<boolean> => {
    if (!conversationId) return false;

    setDeletingId(file.id);
    setActionError(null);
    try {
      const response = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/files/${file.id}`,
        { method: "DELETE" },
      )) as Response;
      if (!response.ok) {
        setActionError("The file could not be deleted. Please try again.");
        return false;
      }
      if (selected?.id === file.id) {
        setSelected(null);
        setDraft("");
      }
      await refresh();
      return true;
    } finally {
      setDeletingId(null);
    }
  };

  const importFile = async (file: File) => {
    if (!conversationId) return;
    const maxBytes = 4 * 1024 * 1024;
    if (file.size > maxBytes) {
      setActionError("Files must be 4 MB or smaller for secure Library preview.");
      return;
    }
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    const fallbackTypes: Record<string, string> = {
      md: "text/markdown",
      csv: "text/csv",
      json: "application/json",
      yaml: "application/yaml",
      yml: "application/yaml",
      diff: "text/x-diff",
      patch: "text/x-diff",
      svg: "image/svg+xml",
      pdf: "application/pdf",
      docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      zip: "application/zip",
    };
    const contentType = file.type || fallbackTypes[extension] || "text/plain";
    const isText = contentType.startsWith("text/") || ["json", "yaml", "yml"].includes(extension);
    setImporting(true);
    setActionError(null);
    try {
      const content = isText
        ? await file.text()
        : await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result ?? ""));
            reader.onerror = () => reject(new Error("The file could not be read."));
            reader.readAsDataURL(file);
          });
      const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/files`, {
        method: "POST",
        body: JSON.stringify({ name: file.name, content, content_type: contentType }),
      })) as Response;
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        setActionError(
          String(
            payload?.detail?.message ??
              payload?.error?.message ??
              "The file could not be imported.",
          ),
        );
        return;
      }
      const created = (await response.json()) as LibraryFile;
      setSelected(created);
      setDraft(created.content ?? content);
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The file could not be imported.");
    } finally {
      setImporting(false);
    }
  };

  const selectedLabel = useMemo(
    () => (embedded ? "DeepSpace Library" : (selected?.name ?? "DeepSpace Library")),
    [embedded, selected],
  );
  const fileList = (
    <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-2">
      <div className="mb-2 flex items-center justify-end">
        <label className="border-glass-border bg-surface-1 text-muted-foreground hover:bg-surface-2 hover:text-primary inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-2 py-1.5 text-[10px] font-semibold transition">
          {importing ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
          Import file
          <input
            type="file"
            className="sr-only"
            disabled={importing}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void importFile(file);
            }}
          />
        </label>
      </div>
      {loading && !files.length ? (
        <div className="flex justify-center p-5">
          <Loader2 size={16} className="text-primary animate-spin" />
        </div>
      ) : null}
      {files.length === 0 && !loading ? (
        <p className="text-foreground/45 px-2 py-4 text-center text-[11px] leading-5">
          Import a file, save a named copy from the note editor, or ask DeepSpace to create a named
          file.
        </p>
      ) : null}
      {actionError ? (
        <p className="mb-2 rounded-lg border border-rose-300/15 bg-rose-300/[0.06] px-2 py-1.5 text-[10px] leading-4 text-rose-200">
          {actionError}
        </p>
      ) : null}
      {files.map((file) => (
        <div key={file.id} className="hover:bg-surface-2 mb-1 rounded-lg">
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              onClick={() => void selectFile(file)}
              className="text-foreground/65 hover:bg-surface-2 hover:text-primary flex min-w-0 flex-1 items-center gap-2 rounded-l-lg px-2 py-2 text-left text-[11px] transition"
            >
              {file.name.endsWith(".py") ||
              file.name.endsWith(".ts") ||
              file.name.endsWith(".js") ? (
                <FileCode2 size={14} className="text-primary shrink-0" />
              ) : (
                <FileText size={14} className="text-primary shrink-0 opacity-80" />
              )}
              <span className="min-w-0 flex-1 truncate">{file.name}</span>
            </button>
            <button
              type="button"
              onClick={() => startRename(file)}
              aria-label={`Rename ${file.name}`}
              title="Rename file"
              className="text-foreground/40 hover:bg-surface-2 hover:text-primary rounded-md p-1.5 transition"
            >
              <Pencil size={12} />
            </button>
            <button
              type="button"
              disabled={deletingId === file.id}
              onClick={() => setDeleteTarget(file)}
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
                className="border-glass-border bg-surface-0 text-foreground focus:border-primary/60 min-w-0 flex-1 rounded-md border px-2 py-1 text-[11px] outline-none"
              />
              <button
                type="submit"
                disabled={saving}
                aria-label="Save new file name"
                className="border-glass-border bg-surface-2 text-primary rounded-md border p-1 disabled:opacity-50"
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
                className="text-foreground/45 hover:bg-surface-2 hover:text-foreground rounded-md p-1"
              >
                <X size={13} />
              </button>
            </form>
          ) : null}
        </div>
      ))}
    </div>
  );
  if (!open) return null;

  return (
    <div
      className={
        embedded
          ? "bg-surface-0 relative flex h-full w-full min-w-0 flex-col overflow-hidden"
          : "bg-surface-0 border-glass-border absolute inset-y-0 left-0 z-50 flex max-w-[92vw] min-w-[16rem] flex-col border-r shadow-[24px_0_70px_rgba(0,0,0,0.45)] backdrop-blur-xl"
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
          className="bg-primary/0 hover:bg-primary/40 absolute inset-y-0 right-0 z-10 w-1 cursor-col-resize transition"
        />
      ) : null}
      <header className="border-glass-border bg-surface-1/40 flex items-center justify-between border-b px-3 py-3">
        <div className="text-foreground flex min-w-0 items-center gap-2 text-xs font-semibold">
          {selected && !embedded ? (
            <button
              type="button"
              onClick={() => {
                setSelected(null);
                setDraft("");
              }}
              aria-label="Back to files"
              className="text-foreground/60 hover:bg-surface-2 hover:text-primary rounded-md p-1"
            >
              <ArrowLeft size={14} />
            </button>
          ) : (
            <FolderOpen size={15} className="text-primary shrink-0" />
          )}
          <span className="truncate">{selectedLabel}</span>
        </div>
        <div className="flex items-center gap-1">
          {selected ? (
            <button
              type="button"
              disabled={saving}
              onClick={() => void saveFile()}
              className="border-glass-border bg-surface-2 text-primary inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-semibold disabled:opacity-50"
            >
              <Save size={12} /> Save
            </button>
          ) : null}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close library"
            className="text-foreground/50 hover:bg-surface-2 hover:text-foreground rounded-md p-1"
          >
            <X size={15} />
          </button>
        </div>
      </header>
      {embedded ? (
        <div className="flex min-h-0 flex-1">
          <aside
            className={`border-glass-border flex min-h-0 shrink-0 flex-col border-r transition-[width] duration-200 ease-out ${
              isFilesCollapsed ? "w-11" : "w-[min(30%,18rem)] max-w-[18rem] min-w-[13rem]"
            }`}
          >
            <div
              className={`border-glass-border text-foreground/50 flex items-center border-b py-2 text-[10px] font-semibold tracking-[0.16em] uppercase ${
                isFilesCollapsed ? "justify-center px-1" : "justify-between px-3"
              }`}
            >
              {!isFilesCollapsed ? <span>Files</span> : null}
              <button
                type="button"
                onClick={toggleFilesCollapsed}
                aria-expanded={!isFilesCollapsed}
                aria-label={isFilesCollapsed ? "Expand files" : "Collapse files"}
                title={isFilesCollapsed ? "Expand files" : "Collapse files"}
                className="text-foreground/55 hover:bg-surface-2 hover:text-primary rounded-md p-1 transition"
              >
                {isFilesCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
              </button>
            </div>
            {!isFilesCollapsed ? fileList : null}
          </aside>
          <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-3">
            {selected ? (
              <DeepSpaceLibraryFileWorkspace
                key={selected.id}
                name={selected.name}
                contentType={selected.content_type}
                value={draft}
                onChange={setDraft}
              />
            ) : (
              <div className="border-glass-border bg-surface-1/40 text-foreground/45 flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed px-6 text-center text-xs">
                Select a file to edit and preview it here.
              </div>
            )}
          </section>
        </div>
      ) : selected ? (
        <section className="flex min-h-0 flex-1 flex-col overflow-auto p-3">
          <DeepSpaceLibraryFileWorkspace
            key={selected.id}
            name={selected.name}
            contentType={selected.content_type}
            value={draft}
            onChange={setDraft}
          />
        </section>
      ) : (
        fileList
      )}
      <ConfirmationModal
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (!deleteTarget) return;
          const deleted = await deleteFile(deleteTarget);
          if (deleted) setDeleteTarget(null);
        }}
        title="Delete library file?"
        message={
          deleteTarget
            ? `Delete “${deleteTarget.name}”? This file and its contents cannot be recovered.`
            : ""
        }
        confirmLabel="Delete file"
        cancelLabel="Keep file"
        variant="danger"
        loading={deleteTarget !== null && deletingId === deleteTarget.id}
      />
    </div>
  );
}
