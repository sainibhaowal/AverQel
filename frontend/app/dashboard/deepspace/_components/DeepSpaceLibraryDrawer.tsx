"use client";

import { motion } from "framer-motion";
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
  Clipboard,
  ClipboardPaste,
  Scissors,
  FolderPlus,
  FilePlus2,
  Download,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { fetchWithAuth, uploadWithAuthProgress } from "@/lib/api";

import ConfirmationModal from "@/app/components/ui/ConfirmationModal";
import {
  deletePersistedUpload,
  getPersistedUpload,
  savePersistedUpload,
} from "../_lib/library-uploads";

import DeepSpaceLibraryFileWorkspace from "./DeepSpaceLibraryFileWorkspace";

type LibraryFile = {
  id: string;
  name: string;
  content_type: string;
  source: string;
  size_bytes: number;
  content?: string | null;
  parent_folder_id?: string | null;
  version?: number;
  is_binary?: boolean;
  extracted_text?: string | null;
  download_url?: string | null;
  archive_entries?:
    | { name: string; directory: boolean; compressedSize: number; size: number }[]
    | null;
};

type LibraryFolder = { id: string; name: string; parent_folder_id?: string | null };
type ArchiveSelection = { name: string; contentType: string };
type UploadItem = {
  id: string;
  uploadId?: string;
  name: string;
  size: number;
  loaded: number;
  status: "queued" | "uploading" | "processing" | "complete" | "cancelled" | "error";
  error?: string;
};

type LibraryUpload = {
  id: string;
  name: string;
  content_type: string;
  expected_size: number;
  chunk_size: number;
  total_chunks: number;
  received_chunks: number[];
  bytes_received: number;
  progress_percent: number;
  status: "pending" | "uploading" | "queued" | "processing" | "completed" | "failed" | "cancelled";
  file_id?: string | null;
  error?: string | null;
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
  const [folders, setFolders] = useState<LibraryFolder[]>([]);
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
  const [folderStack, setFolderStack] = useState<string[]>([]);
  const [selected, setSelected] = useState<LibraryFile | null>(null);
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState("");
  const [drawerWidth, setDrawerWidth] = useState(320);
  const [isFilesCollapsed, setIsFilesCollapsed] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [uploadItems, setUploadItems] = useState<UploadItem[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<LibraryFile | null>(null);
  const [deleteFolderTarget, setDeleteFolderTarget] = useState<LibraryFolder | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [newFileName, setNewFileName] = useState("");
  const [renamingFolderId, setRenamingFolderId] = useState<string | null>(null);
  const [folderRenameValue, setFolderRenameValue] = useState("");
  const [clipboardFile, setClipboardFile] = useState<LibraryFile | null>(null);
  const [clipboardMode, setClipboardMode] = useState<"copy" | "move">("copy");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [archiveSelection, setArchiveSelection] = useState<ArchiveSelection | null>(null);
  const [filesPanelWidth, setFilesPanelWidth] = useState(320);
  const [isResizingFilesPanel, setIsResizingFilesPanel] = useState(false);
  const [draggedEntry, setDraggedEntry] = useState<{
    kind: "file" | "folder";
    id: string;
    name: string;
  } | null>(null);
  const [dropTargetFolderId, setDropTargetFolderId] = useState<string | null>(null);
  const [movingEntryId, setMovingEntryId] = useState<string | null>(null);
  const uploadControllersRef = useRef<Record<string, AbortController>>({});
  const activeUploadIdsRef = useRef<Set<string>>(new Set());
  const draggedEntryRef = useRef<{
    kind: "file" | "folder";
    id: string;
    name: string;
  } | null>(null);
  const filesPanelRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!embedded) return;
    try {
      setIsFilesCollapsed(window.localStorage.getItem(LIBRARY_FILES_COLLAPSED_KEY) === "true");
    } catch {
      // Storage can be unavailable in privacy-restricted browser contexts.
    }
  }, [embedded]);

  useEffect(() => {
    setCurrentFolderId(null);
    setFolderStack([]);
    setSelected(null);
    setSelectedFileIds(new Set());
    setDraft("");
  }, [conversationId]);

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
      const query = currentFolderId
        ? `?parent_folder_id=${encodeURIComponent(currentFolderId)}`
        : "";
      const response = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/entries${query}`,
        {
          timeoutMs: 8_000,
        },
      )) as Response;
      if (!response.ok) return;
      const entries = (await response.json()) as { files: LibraryFile[]; folders: LibraryFolder[] };
      const nextFiles = entries.files ?? [];
      setFolders(entries.folders ?? []);
      setFiles(nextFiles);
      setSelectedFileIds((current) => {
        const visibleIds = new Set(nextFiles.map((file) => file.id));
        return new Set([...current].filter((id) => visibleIds.has(id)));
      });
      const retained = selected && nextFiles.some((file) => file.id === selected.id);
      if (selected && !retained) setDraft("");
      setSelected(retained ? selected : (nextFiles[0] ?? null));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void refresh();
  }, [open, conversationId, currentFolderId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (open && conversationId) void resumeUploads();
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
      setDraft(detail.content ?? detail.extracted_text ?? "");
      setArchiveSelection(null);
      setPreviewUrl(null);
      if (detail.is_binary) {
        const contentResponse = (await fetchWithAuth(
          `/deepspace/library/${conversationId}/files/${file.id}/content`,
          { timeoutMs: 30_000 },
        )) as Response;
        if (contentResponse.ok) {
          const blob = await contentResponse.blob();
          setPreviewUrl(URL.createObjectURL(blob));
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const openArchiveEntry = async (entry: { name: string; directory: boolean }) => {
    if (!conversationId || !selected || entry.directory) return;
    const response = (await fetchWithAuth(
      `/deepspace/library/${conversationId}/files/${selected.id}/archive/${entry.name.split("/").map(encodeURIComponent).join("/")}`,
      { timeoutMs: 30_000 },
    )) as Response;
    if (!response.ok) return;
    const extension = entry.name.split(".").pop()?.toLowerCase() ?? "";
    const textExtensions = new Set([
      "md",
      "mdx",
      "txt",
      "json",
      "yaml",
      "yml",
      "xml",
      "html",
      "htm",
      "css",
      "js",
      "ts",
      "tsx",
      "jsx",
      "py",
      "sql",
      "diff",
      "patch",
      "java",
      "go",
      "rs",
      "c",
      "cpp",
      "h",
    ]);
    const contentType =
      response.headers.get("content-type")?.split(";", 1)[0] ||
      (textExtensions.has(extension) ? "text/plain" : "application/octet-stream");
    setArchiveSelection({ name: entry.name, contentType });
    if (
      contentType.startsWith("text/") ||
      contentType.includes("json") ||
      contentType.includes("xml") ||
      contentType.includes("yaml") ||
      textExtensions.has(extension)
    ) {
      setPreviewUrl(null);
      setDraft(await response.text());
    } else {
      const blob = await response.blob();
      setDraft("");
      setPreviewUrl(URL.createObjectURL(blob));
    }
  };

  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );

  const createFolder = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = newFolderName.trim();
    if (!conversationId || !name) return;
    const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/folders`, {
      method: "POST",
      body: JSON.stringify({ name, parent_folder_id: currentFolderId }),
    })) as Response;
    if (!response.ok) {
      setActionError("The folder could not be created.");
      return;
    }
    setNewFolderName("");
    await refresh();
  };

  const createFile = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = newFileName.trim();
    if (!conversationId || !name) return;
    const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/files`, {
      method: "POST",
      body: JSON.stringify({
        name,
        parent_folder_id: currentFolderId,
        content_type: "text/markdown",
        content: "",
      }),
    })) as Response;
    if (!response.ok) {
      setActionError("The file could not be created.");
      return;
    }
    const created = (await response.json()) as LibraryFile;
    setNewFileName("");
    await refresh();
    await selectFile(created);
  };

  const pasteFile = async () => {
    if (!conversationId || !clipboardFile) return;
    const response = (await fetchWithAuth(
      `/deepspace/library/${conversationId}/files/${clipboardFile.id}/copy`,
      {
        method: "POST",
        body: JSON.stringify({ parent_folder_id: currentFolderId, mode: clipboardMode }),
      },
    )) as Response;
    if (!response.ok) {
      setActionError("The file could not be pasted here.");
      return;
    }
    setClipboardFile(null);
    await refresh();
  };

  const moveEntryToFolder = async (
    entry: { kind: "file" | "folder"; id: string; name: string },
    parentFolderId: string,
    mode: "move" | "copy" = "move",
  ) => {
    if (!conversationId || entry.id === parentFolderId) return;
    setMovingEntryId(entry.id);
    setActionError(null);
    try {
      const endpoint =
        entry.kind === "file"
          ? `/deepspace/library/${conversationId}/files/${entry.id}/copy`
          : `/deepspace/library/${conversationId}/folders/${entry.id}`;
      const response = (await fetchWithAuth(endpoint, {
        method: entry.kind === "file" ? "POST" : "PATCH",
        body: JSON.stringify(
          entry.kind === "file"
            ? { parent_folder_id: parentFolderId, mode }
            : { parent_folder_id: parentFolderId },
        ),
      })) as Response;
      if (!response.ok) {
        const message = entry.kind === "file" ? "file" : "folder";
        setActionError(`The ${message} could not be moved there.`);
        return;
      }
      await refresh();
    } finally {
      setMovingEntryId(null);
      setDraggedEntry(null);
      draggedEntryRef.current = null;
      setDropTargetFolderId(null);
    }
  };

  const renameFolder = async (folder: LibraryFolder) => {
    const name = folderRenameValue.trim();
    if (!conversationId || !name) return;
    const response = (await fetchWithAuth(
      `/deepspace/library/${conversationId}/folders/${folder.id}`,
      { method: "PATCH", body: JSON.stringify({ name }) },
    )) as Response;
    if (!response.ok) {
      setActionError("The folder could not be renamed.");
      return;
    }
    setRenamingFolderId(null);
    await refresh();
  };

  const deleteFolder = async (folder: LibraryFolder) => {
    if (!conversationId) return;
    const response = (await fetchWithAuth(
      `/deepspace/library/${conversationId}/folders/${folder.id}?recursive=true`,
      { method: "DELETE" },
    )) as Response;
    if (!response.ok) {
      setActionError("The folder could not be removed.");
      return;
    }
    await refresh();
  };

  const saveFile = async () => {
    if (!conversationId || !selected || selected.is_binary) return;
    setSaving(true);
    try {
      const response = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/files/${selected.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ content: draft, expected_version: selected.version ?? 1 }),
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

  const downloadBlobResponse = async (response: Response, fallbackName: string) => {
    if (!response.ok) {
      setActionError("The selected file(s) could not be downloaded.");
      return false;
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") ?? "";
    const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
    const filename = filenameMatch?.[1]
      ? decodeURIComponent(filenameMatch[1].replace(/\"/g, ""))
      : fallbackName;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    return true;
  };

  const downloadFile = async (file: LibraryFile) => {
    if (!conversationId) return;
    setActionError(null);
    const response = (await fetchWithAuth(
      `/deepspace/library/${conversationId}/files/${file.id}/content?download=true`,
      { timeoutMs: 120_000 },
    )) as Response;
    await downloadBlobResponse(response, file.name);
  };

  const exportSelectedFiles = async () => {
    if (!conversationId || selectedFileIds.size === 0) return;
    const chosen = files.filter((file) => selectedFileIds.has(file.id));
    if (chosen.length === 1) {
      await downloadFile(chosen[0]);
      return;
    }
    setActionError(null);
    const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/files/export`, {
      method: "POST",
      body: JSON.stringify({ file_ids: chosen.map((file) => file.id) }),
      timeoutMs: 120_000,
    })) as Response;
    const downloaded = await downloadBlobResponse(response, "deepspace-library-export.zip");
    if (downloaded) setSelectedFileIds(new Set());
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

  const updateUploadItem = (id: string, update: Partial<UploadItem>) => {
    setUploadItems((items) =>
      items.map((item) => (item.id === id ? { ...item, ...update } : item)),
    );
  };

  const readUpload = async (uploadId: string): Promise<LibraryUpload | null> => {
    if (!conversationId) return null;
    const response = (await fetchWithAuth(
      `/deepspace/library/${conversationId}/uploads/${uploadId}`,
      { timeoutMs: 8_000 },
    )) as Response;
    return response.ok ? ((await response.json()) as LibraryUpload) : null;
  };

  const runUploadSession = async (session: LibraryUpload, file: File, itemId: string) => {
    if (!conversationId || activeUploadIdsRef.current.has(session.id)) return;
    activeUploadIdsRef.current.add(session.id);
    const controller = new AbortController();
    uploadControllersRef.current[session.id] = controller;
    try {
      let current = session;
      updateUploadItem(itemId, {
        uploadId: session.id,
        status: "uploading",
        loaded: current.bytes_received,
      });
      for (let index = 0; index < current.total_chunks; index += 1) {
        if (controller.signal.aborted) throw new DOMException("Upload cancelled", "AbortError");
        if (current.received_chunks.includes(index)) continue;
        const chunk = file.slice(
          index * current.chunk_size,
          Math.min(file.size, (index + 1) * current.chunk_size),
        );
        const baseLoaded = current.bytes_received;
        const response = await uploadWithAuthProgress(
          `/deepspace/library/${conversationId}/uploads/${current.id}/chunks/${index}`,
          chunk,
          {
            method: "PUT",
            signal: controller.signal,
            timeoutMs: 120_000,
            onProgress: (loaded) =>
              updateUploadItem(itemId, { loaded: Math.min(file.size, baseLoaded + loaded) }),
          },
        );
        if (!response.ok) throw new Error("The upload chunk was rejected by the server.");
        current = (await response.json()) as LibraryUpload;
        updateUploadItem(itemId, { loaded: current.bytes_received });
      }
      const completeResponse = (await fetchWithAuth(
        `/deepspace/library/${conversationId}/uploads/${current.id}/complete`,
        { method: "POST", timeoutMs: 15_000 },
      )) as Response;
      if (!completeResponse.ok) throw new Error("The upload could not be queued for processing.");
      current = (await completeResponse.json()) as LibraryUpload;
      updateUploadItem(itemId, { status: "processing", loaded: file.size });
      for (let attempt = 0; attempt < 180; attempt += 1) {
        if (controller.signal.aborted) throw new DOMException("Upload cancelled", "AbortError");
        if (current.status === "completed") {
          updateUploadItem(itemId, { status: "complete", loaded: file.size });
          await deletePersistedUpload(current.id);
          await refresh();
          return;
        }
        if (current.status === "failed" || current.status === "cancelled") {
          throw new Error(current.error ?? "The file could not be imported.");
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const next = await readUpload(current.id);
        if (!next) throw new Error("The upload session could not be found.");
        current = next;
        updateUploadItem(itemId, {
          status:
            current.status === "processing" || current.status === "queued"
              ? "processing"
              : "uploading",
          loaded: current.bytes_received,
        });
      }
      throw new Error("The file is taking longer than expected. It will resume automatically.");
    } catch (error) {
      if (controller.signal.aborted) {
        updateUploadItem(itemId, { status: "cancelled", error: "Cancelled" });
      } else {
        const message = error instanceof Error ? error.message : "The file could not be imported.";
        updateUploadItem(itemId, { status: "error", error: message });
      }
    } finally {
      activeUploadIdsRef.current.delete(session.id);
      delete uploadControllersRef.current[session.id];
      setImporting((value) => value && Object.keys(uploadControllersRef.current).length > 0);
    }
  };

  const createUploadSession = async (file: File): Promise<LibraryUpload> => {
    if (!conversationId) throw new Error("No DeepSpace conversation is active.");
    const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/uploads`, {
      method: "POST",
      body: JSON.stringify({
        name: file.name,
        size_bytes: file.size,
        content_type: file.type || "application/octet-stream",
        parent_folder_id: currentFolderId,
      }),
      timeoutMs: 15_000,
    })) as Response;
    if (!response.ok) throw new Error("The upload session could not be created.");
    return (await response.json()) as LibraryUpload;
  };

  const resumeUploads = async () => {
    if (!conversationId) return;
    const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/uploads`, {
      timeoutMs: 8_000,
    })) as Response;
    if (!response.ok) return;
    const sessions = (await response.json()) as LibraryUpload[];
    for (const session of sessions) {
      if (activeUploadIdsRef.current.has(session.id)) continue;
      if (session.status === "failed") {
        setUploadItems((items) =>
          items.some((item) => item.uploadId === session.id)
            ? items
            : [
                ...items,
                {
                  id: `resume-${session.id}`,
                  uploadId: session.id,
                  name: session.name,
                  size: session.expected_size,
                  loaded: session.bytes_received,
                  status: "error",
                  error: session.error ?? "The file import failed.",
                },
              ],
        );
        continue;
      }
      const persisted = await getPersistedUpload(session.id);
      if (!persisted) {
        setUploadItems((items) =>
          items.some((item) => item.uploadId === session.id)
            ? items
            : [
                ...items,
                {
                  id: `resume-${session.id}`,
                  uploadId: session.id,
                  name: session.name,
                  size: session.expected_size,
                  loaded: session.bytes_received,
                  status: "error",
                  error: "Select this file again to resume.",
                },
              ],
        );
        continue;
      }
      const itemId = `resume-${session.id}`;
      setUploadItems((items) =>
        items.some((item) => item.uploadId === session.id)
          ? items
          : [
              ...items,
              {
                id: itemId,
                uploadId: session.id,
                name: session.name,
                size: session.expected_size,
                loaded: session.bytes_received,
                status: "queued",
              },
            ],
      );
      void runUploadSession(session, persisted.file, itemId);
    }
  };

  const importFiles = async (input: File[] | FileList) => {
    if (!conversationId) return;
    const maxBytes = 25 * 1024 * 1024;
    const filesToUpload = Array.from(input).filter((file) => file.size <= maxBytes);
    const oversized = Array.from(input).filter((file) => file.size > maxBytes);
    if (oversized.length)
      setActionError(`${oversized.length} file(s) exceeded the 25 MB secure upload limit.`);
    if (!filesToUpload.length) return;
    setImporting(true);
    setActionError(null);
    const sessions = await Promise.all(
      filesToUpload.map(async (file, index) => {
        try {
          const session = await createUploadSession(file);
          await savePersistedUpload({ uploadId: session.id, conversationId, file });
          const item = {
            id: `${Date.now()}-${index}-${file.name}`,
            uploadId: session.id,
            name: file.name,
            size: file.size,
            loaded: 0,
            status: "queued" as const,
          };
          setUploadItems((items) => [...items, item]);
          return { session, file, itemId: item.id };
        } catch (error) {
          setActionError(
            error instanceof Error ? error.message : "The upload session could not be created.",
          );
          return null;
        }
      }),
    );
    let next = 0;
    const workers = Array.from(
      { length: Math.min(3, sessions.filter(Boolean).length) },
      async () => {
        while (next < sessions.length) {
          const index = next;
          next += 1;
          const item = sessions[index];
          if (item) await runUploadSession(item.session, item.file, item.itemId);
        }
      },
    );
    await Promise.all(workers);
    setImporting(false);
  };

  const cancelUpload = async (item: UploadItem) => {
    if (!conversationId || !item.uploadId) return;
    uploadControllersRef.current[item.uploadId]?.abort();
    const response = (await fetchWithAuth(
      `/deepspace/library/${conversationId}/uploads/${item.uploadId}/cancel`,
      { method: "POST", timeoutMs: 15_000 },
    )) as Response;
    if (response.ok) {
      await deletePersistedUpload(item.uploadId);
      updateUploadItem(item.id, { status: "cancelled", error: "Cancelled" });
    }
  };

  const handleClipboardPaste = (event: React.ClipboardEvent) => {
    const files = Array.from(event.clipboardData.files);
    if (!files.length) return;
    event.preventDefault();
    void importFiles(files);
  };

  useEffect(() => {
    if (!open) return;
    const handleWindowPaste = (event: ClipboardEvent) => {
      const files = Array.from(event.clipboardData?.files ?? []);
      if (!files.length) return;
      event.preventDefault();
      void importFiles(files);
    };
    window.addEventListener("paste", handleWindowPaste);
    return () => window.removeEventListener("paste", handleWindowPaste);
  }, [open, conversationId, currentFolderId]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedLabel = useMemo(
    () => (embedded ? "DeepSpace Library" : (selected?.name ?? "DeepSpace Library")),
    [embedded, selected],
  );
  const fileList = (
    <motion.div
      key={currentFolderId ?? "library-root"}
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
      className={`custom-scrollbar min-h-0 flex-1 overflow-y-auto p-2 ${dragActive ? "bg-primary/[0.06]" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setDragActive(true);
      }}
      onDragLeave={(event) => {
        if (event.currentTarget === event.target) setDragActive(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        event.stopPropagation();
        setDragActive(false);
        if (event.dataTransfer.files.length) void importFiles(event.dataTransfer.files);
      }}
      onPaste={handleClipboardPaste}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-1">
        <div className="flex items-center gap-1">
          {currentFolderId ? (
            <button
              type="button"
              onClick={() => {
                const next = [...folderStack];
                next.pop();
                setFolderStack(next);
                setCurrentFolderId(next.length ? next[next.length - 1] : null);
                setSelected(null);
                setDraft("");
              }}
              className="text-foreground/55 hover:bg-surface-2 hover:text-primary rounded-md p-1.5"
              title="Back to parent folder"
            >
              <ArrowLeft size={13} />
            </button>
          ) : null}
          <form onSubmit={createFolder} className="flex items-center gap-1">
            <input
              value={newFolderName}
              onChange={(event) => setNewFolderName(event.target.value)}
              placeholder="New folder"
              className="border-glass-border bg-surface-0 text-foreground w-24 rounded-md border px-2 py-1.5 text-[10px] outline-none"
            />
            <button
              type="submit"
              title="Create folder"
              className="border-glass-border bg-surface-1 text-primary rounded-md border p-1.5"
            >
              <FolderPlus size={12} />
            </button>
          </form>
          <form onSubmit={createFile} className="flex items-center gap-1">
            <input
              value={newFileName}
              onChange={(event) => setNewFileName(event.target.value)}
              placeholder="New file.md"
              className="border-glass-border bg-surface-0 text-foreground w-24 rounded-md border px-2 py-1.5 text-[10px] outline-none"
            />
            <button
              type="submit"
              title="Create file"
              className="border-glass-border bg-surface-1 text-primary rounded-md border p-1.5"
            >
              <FilePlus2 size={12} />
            </button>
          </form>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={!clipboardFile}
            onClick={() => void pasteFile()}
            title={clipboardMode === "move" ? "Move file here" : "Paste copied file here"}
            className="border-glass-border bg-surface-1 text-primary rounded-md border p-1.5 disabled:opacity-40"
          >
            <ClipboardPaste size={12} />
          </button>
          <label className="border-glass-border bg-surface-1 text-muted-foreground hover:bg-surface-2 hover:text-primary inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-2 py-1.5 text-[10px] font-semibold transition">
            {importing ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            Import files
            <input
              type="file"
              multiple
              className="sr-only"
              disabled={importing}
              onChange={(event) => {
                // Copy the FileList before clearing the input.  Some browsers
                // clear the FileList immediately when value is reset, which
                // made the button appear to do nothing while drag/drop still
                // worked.
                const files = Array.from(event.target.files ?? []);
                event.target.value = "";
                if (files.length) void importFiles(files);
              }}
            />
          </label>
        </div>
      </div>
      <div
        className={`mb-2 rounded-lg border border-dashed px-3 py-2 text-center text-[10px] transition ${dragActive ? "border-primary/70 bg-primary/[0.08] text-primary" : "border-glass-border text-foreground/45"}`}
      >
        Drop multiple files here or paste copied files with Ctrl/Cmd+V
      </div>
      {files.length ? (
        <div className="border-glass-border bg-surface-1/40 mb-2 flex items-center justify-between gap-2 rounded-lg border px-2 py-1.5">
          <button
            type="button"
            onClick={() =>
              setSelectedFileIds((current) =>
                current.size === files.length ? new Set() : new Set(files.map((file) => file.id)),
              )
            }
            className="text-foreground/55 hover:text-primary text-[10px] transition"
          >
            {selectedFileIds.size === files.length ? "Clear selection" : "Select all"}
          </button>
          <button
            type="button"
            disabled={selectedFileIds.size === 0}
            onClick={() => void exportSelectedFiles()}
            className="border-glass-border bg-surface-2 text-primary inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-40"
            title="Download selected files; multiple files are packaged as a ZIP"
          >
            <Download size={12} />
            {selectedFileIds.size > 1 ? "Export selected" : "Download selected"}
          </button>
        </div>
      ) : null}
      {uploadItems.length
        ? (() => {
            const total = uploadItems.reduce((sum, item) => sum + item.size, 0);
            const loaded = uploadItems.reduce(
              (sum, item) => sum + Math.min(item.loaded, item.size),
              0,
            );
            const percent = total ? Math.round((loaded / total) * 100) : 0;
            return (
              <div className="border-glass-border bg-surface-1/60 mb-2 rounded-lg border p-2">
                <div className="text-foreground/65 mb-1 flex items-center justify-between text-[10px]">
                  <span>Uploading {uploadItems.length} file(s)</span>
                  <span>{percent}%</span>
                </div>
                <div className="bg-surface-0 h-1.5 overflow-hidden rounded-full">
                  <div
                    className="bg-primary h-full transition-[width]"
                    style={{ width: `${percent}%` }}
                  />
                </div>
                <div className="mt-2 max-h-28 space-y-1 overflow-auto">
                  {uploadItems.map((item) => (
                    <div key={item.id} className="flex items-center gap-2 text-[10px]">
                      <span className="text-foreground/60 min-w-0 flex-1 truncate">
                        {item.name}
                      </span>
                      <span
                        className={
                          item.status === "error"
                            ? "text-rose-300"
                            : item.status === "complete"
                              ? "text-emerald-300"
                              : item.status === "cancelled"
                                ? "text-foreground/40"
                                : "text-foreground/40"
                        }
                      >
                        {item.status === "error"
                          ? "failed"
                          : item.status === "complete"
                            ? "Done"
                            : item.status === "cancelled"
                              ? "cancelled"
                              : item.status === "processing"
                                ? "processing"
                                : `${Math.round((item.loaded / Math.max(item.size, 1)) * 100)}%`}
                      </span>
                      {(item.status === "queued" ||
                        item.status === "uploading" ||
                        item.status === "processing") &&
                      item.uploadId ? (
                        <button
                          type="button"
                          onClick={() => void cancelUpload(item)}
                          className="text-foreground/50 hover:text-rose-300"
                          title="Cancel upload"
                        >
                          <X size={12} />
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            );
          })()
        : null}
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
      {folders.map((folder) => (
        <div
          key={folder.id}
          draggable
          onDragStart={(event) => {
            const entry = { kind: "folder" as const, id: folder.id, name: folder.name };
            draggedEntryRef.current = entry;
            setDraggedEntry(entry);
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", folder.id);
          }}
          onDragEnd={() => {
            setDraggedEntry(null);
            draggedEntryRef.current = null;
            setDropTargetFolderId(null);
          }}
          onDragOver={(event) => {
            const entry = draggedEntryRef.current;
            if (!entry || entry.id === folder.id) return;
            event.preventDefault();
            event.dataTransfer.dropEffect =
              entry.kind === "file" && (event.ctrlKey || event.metaKey) ? "copy" : "move";
            setDropTargetFolderId(folder.id);
          }}
          onDragLeave={() =>
            setDropTargetFolderId((current) => (current === folder.id ? null : current))
          }
          onDrop={(event) => {
            event.preventDefault();
            event.stopPropagation();
            const entry = draggedEntryRef.current ?? draggedEntry;
            if (entry) {
              const mode =
                entry.kind === "file" && (event.ctrlKey || event.metaKey) ? "copy" : "move";
              void moveEntryToFolder(entry, folder.id, mode);
            }
          }}
          className={`hover:bg-surface-2 mb-1 flex items-center rounded-lg transition-colors duration-200 ${dropTargetFolderId === folder.id ? "bg-primary/[0.12] ring-primary/40 ring-1" : ""}`}
        >
          {renamingFolderId === folder.id ? (
            <form
              className="flex min-w-0 flex-1 gap-1 px-2 py-1"
              onSubmit={(event) => {
                event.preventDefault();
                void renameFolder(folder);
              }}
            >
              <input
                autoFocus
                value={folderRenameValue}
                onChange={(event) => setFolderRenameValue(event.target.value)}
                className="border-glass-border bg-surface-0 text-foreground min-w-0 flex-1 rounded border px-2 py-1 text-[10px] outline-none"
              />
              <button type="submit" className="text-primary p-1">
                <Check size={12} />
              </button>
            </form>
          ) : (
            <>
              <button
                type="button"
                onClick={() => {
                  setFolderStack((stack) => [...stack, folder.id]);
                  setCurrentFolderId(folder.id);
                  setSelected(null);
                  setDraft("");
                }}
                draggable
                onDragStart={(event) => {
                  const entry = { kind: "folder" as const, id: folder.id, name: folder.name };
                  draggedEntryRef.current = entry;
                  setDraggedEntry(entry);
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData("text/plain", folder.id);
                }}
                className="text-foreground/70 hover:text-primary flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-2 text-left text-[11px] transition-colors duration-200"
              >
                <FolderOpen size={14} className="text-primary shrink-0" />
                <span className="truncate">{folder.name}</span>
              </button>
              <button
                type="button"
                title="Rename folder"
                onClick={() => {
                  setRenamingFolderId(folder.id);
                  setFolderRenameValue(folder.name);
                }}
                className="text-foreground/40 hover:text-primary p-1"
              >
                <Pencil size={11} />
              </button>
              <button
                type="button"
                title="Delete folder"
                onClick={() => setDeleteFolderTarget(folder)}
                className="text-foreground/40 mr-1 p-1 hover:text-rose-200"
              >
                <Trash2 size={11} />
              </button>
            </>
          )}
        </div>
      ))}
      {files.map((file) => (
        <div
          key={file.id}
          draggable
          onDragStart={(event) => {
            const entry = { kind: "file" as const, id: file.id, name: file.name };
            draggedEntryRef.current = entry;
            setDraggedEntry(entry);
            event.dataTransfer.effectAllowed = "copyMove";
            event.dataTransfer.setData("text/plain", file.id);
          }}
          onDragEnd={() => {
            setDraggedEntry(null);
            draggedEntryRef.current = null;
            setDropTargetFolderId(null);
          }}
          className={`hover:bg-surface-2 mb-1 rounded-lg transition-colors duration-200 ${movingEntryId === file.id ? "opacity-50" : ""}`}
        >
          <div className="flex cursor-grab items-center gap-0.5 active:cursor-grabbing">
            <input
              type="checkbox"
              checked={selectedFileIds.has(file.id)}
              onChange={(event) => {
                event.stopPropagation();
                setSelectedFileIds((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.add(file.id);
                  else next.delete(file.id);
                  return next;
                });
              }}
              onClick={(event) => event.stopPropagation()}
              aria-label={`Select ${file.name} for download`}
              className="accent-primary mx-0.5 h-3 w-3 shrink-0 cursor-pointer"
            />
            <button
              type="button"
              onClick={() => {
                setClipboardFile(file);
                setClipboardMode("copy");
              }}
              aria-label={`Copy ${file.name}`}
              title="Copy file"
              className="text-foreground/40 hover:bg-surface-2 hover:text-primary rounded-md p-1.5 transition"
            >
              <Clipboard size={12} />
            </button>
            <button
              type="button"
              onClick={() => {
                setClipboardFile(file);
                setClipboardMode("move");
              }}
              aria-label={`Cut ${file.name}`}
              title="Move file"
              className="text-foreground/40 hover:bg-surface-2 hover:text-primary rounded-md p-1.5 transition"
            >
              <Scissors size={12} />
            </button>
            <button
              type="button"
              draggable
              onDragStart={(event) => {
                const entry = { kind: "file" as const, id: file.id, name: file.name };
                draggedEntryRef.current = entry;
                setDraggedEntry(entry);
                event.dataTransfer.effectAllowed = "copyMove";
                event.dataTransfer.setData("text/plain", file.id);
              }}
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
              onClick={() => void downloadFile(file)}
              aria-label={`Download ${file.name}`}
              title="Download file"
              className="text-foreground/40 hover:bg-surface-2 hover:text-primary rounded-md p-1.5 transition"
            >
              <Download size={12} />
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
    </motion.div>
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
                setArchiveSelection(null);
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
              onClick={() => void downloadFile(selected)}
              className="border-glass-border bg-surface-2 text-primary inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-semibold"
              title="Download this file"
            >
              <Download size={12} /> Download
            </button>
          ) : null}
          {selected && !selected.is_binary ? (
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
            ref={filesPanelRef}
            className={`border-glass-border relative flex min-h-0 shrink-0 flex-col border-r ${isFilesCollapsed ? "w-11" : isResizingFilesPanel ? "transition-none" : "transition-[width] duration-200 ease-out"}`}
            style={isFilesCollapsed ? undefined : { width: `min(${filesPanelWidth}px, 100%)` }}
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
            {!isFilesCollapsed ? (
              <div
                role="separator"
                aria-label="Resize Library files panel"
                title="Resize files panel"
                onPointerDown={(event) => {
                  event.preventDefault();
                  event.currentTarget.setPointerCapture?.(event.pointerId);
                  setIsResizingFilesPanel(true);
                  const startX = event.clientX;
                  const startWidth = filesPanelWidth;
                  let latestWidth = startWidth;
                  let frame: number | null = null;
                  const maxWidth = () =>
                    Math.max(220, Math.min(560, Math.floor(window.innerWidth * 0.45)));
                  const applyWidth = (width: number) => {
                    latestWidth = Math.max(220, Math.min(maxWidth(), width));
                    if (frame !== null) window.cancelAnimationFrame(frame);
                    frame = window.requestAnimationFrame(() => {
                      if (filesPanelRef.current) {
                        filesPanelRef.current.style.width = `${latestWidth}px`;
                      }
                      frame = null;
                    });
                  };
                  const resize = (move: PointerEvent) => {
                    applyWidth(startWidth + move.clientX - startX);
                  };
                  const stop = () => {
                    if (frame !== null) window.cancelAnimationFrame(frame);
                    setFilesPanelWidth(latestWidth);
                    setIsResizingFilesPanel(false);
                    window.removeEventListener("pointermove", resize);
                    window.removeEventListener("pointerup", stop);
                    window.removeEventListener("pointercancel", stop);
                  };
                  window.addEventListener("pointermove", resize);
                  window.addEventListener("pointerup", stop);
                  window.addEventListener("pointercancel", stop);
                }}
                className="bg-primary/0 hover:bg-primary/40 absolute inset-y-0 right-[-3px] z-20 w-1.5 cursor-col-resize touch-none transition-colors"
              />
            ) : null}
          </aside>
          <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-3">
            {selected ? (
              <DeepSpaceLibraryFileWorkspace
                key={`${selected.id}:${archiveSelection?.name ?? "archive"}`}
                name={archiveSelection?.name ?? selected.name}
                contentType={archiveSelection?.contentType ?? selected.content_type}
                value={draft}
                onChange={setDraft}
                previewUrl={previewUrl}
                archiveEntries={archiveSelection ? null : selected.archive_entries}
                onArchiveEntrySelect={archiveSelection ? undefined : openArchiveEntry}
                archiveEntryName={archiveSelection?.name}
                onArchiveBack={
                  archiveSelection
                    ? () => {
                        setArchiveSelection(null);
                        setPreviewUrl(null);
                        setDraft(selected.extracted_text ?? "");
                      }
                    : undefined
                }
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
            key={`${selected.id}:${archiveSelection?.name ?? "archive"}`}
            name={archiveSelection?.name ?? selected.name}
            contentType={archiveSelection?.contentType ?? selected.content_type}
            value={draft}
            onChange={setDraft}
            previewUrl={previewUrl}
            archiveEntries={archiveSelection ? null : selected.archive_entries}
            onArchiveEntrySelect={archiveSelection ? undefined : openArchiveEntry}
            archiveEntryName={archiveSelection?.name}
            onArchiveBack={
              archiveSelection
                ? () => {
                    setArchiveSelection(null);
                    setPreviewUrl(null);
                    setDraft(selected.extracted_text ?? "");
                  }
                : undefined
            }
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
      <ConfirmationModal
        isOpen={deleteFolderTarget !== null}
        onClose={() => setDeleteFolderTarget(null)}
        onConfirm={async () => {
          if (!deleteFolderTarget) return;
          await deleteFolder(deleteFolderTarget);
          setDeleteFolderTarget(null);
        }}
        title="Delete library folder?"
        message={
          deleteFolderTarget ? `Delete “${deleteFolderTarget.name}” and everything inside it?` : ""
        }
        confirmLabel="Delete folder"
        cancelLabel="Keep folder"
        variant="danger"
      />
    </div>
  );
}
