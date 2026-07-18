"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  File,
  Folder,
  FolderPlus,
  FilePlus,
  MoreVertical,
  X,
  RefreshCw,
  Download,
  Trash2,
  Edit2,
  ChevronRight,
  ChevronDown,
  Monitor,
  Cpu,
  Zap,
  Copy,
  ArrowRightLeft,
  ChevronLeft,
  FolderOpen,
} from "lucide-react";
import React, { useEffect, useState, useCallback, useRef } from "react";
import { fetchWithAuth } from "@/lib/api";
import toast from "react-hot-toast";
import FolderPickerDialog from "./FolderPickerDialog";

interface WorkspaceFile {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number;
  modified_at: string;
  extension?: string;
}

interface TauriDialogApi {
  open(options: { directory: boolean; multiple: boolean; defaultPath: string }): Promise<string | string[] | null>;
}

interface TauriWindow extends Window {
  __TAURI__?: { dialog?: TauriDialogApi };
}

interface FileExplorerProps {
  onFileSelect: (path: string) => void;
  onFolderSelect?: (path: string) => void;
  isOpen: boolean;
  onClose: () => void;
  variant?: "drawer" | "sidebar";
}

export default function FileExplorer({
  onFileSelect,
  onFolderSelect,
  isOpen,
  onClose,
  variant = "drawer",
}: FileExplorerProps) {
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentPath, setCurrentPath] = useState("");
  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [newName, setNewName] = useState("");
  const [clipboard, setClipboard] = useState<{ path: string; action: "copy" | "move" } | null>(
    null,
  );
  const [tempPath, setTempPath] = useState("");
  const [isFolderPickerOpen, setIsFolderPickerOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resolveAndLoadFolder = async (folderName: string) => {
    try {
      setLoading(true);
      const res = await fetchWithAuth("/workspace/resolve-folder", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: folderName,
          current_path: currentPath,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.path) {
          fetchFiles(data.path);
        } else {
          toast.error("Could not resolve directory path");
        }
      } else {
        toast.error("Failed to resolve directory path");
      }
    } catch (error) {
      console.error("Failed to resolve native directory path", error);
      toast.error("Error selecting folder");
    } finally {
      setLoading(false);
    }
  };

  const triggerFolderPicker = async () => {
    // 1. Tauri native dialog check
    const tauri = typeof window !== "undefined" ? (window as TauriWindow).__TAURI__ : undefined;
    if (tauri?.dialog) {
      try {
        const selected = await tauri.dialog.open({
          directory: true,
          multiple: false,
          defaultPath: currentPath || "/home/sephi-asi",
        });
        if (selected && typeof selected === "string") {
          fetchFiles(selected);
          return;
        }
      } catch (err) {
        console.error("Tauri dialog error, falling back to Web APIs", err);
      }
    }

    // 2. Browser mode: open the custom folder dialog picker
    // This allows the user to browse their host filesystem reliably,
    // avoiding blind path guessing and browser upload security warnings.
    setIsFolderPickerOpen(true);
  };

  const handleNativeFolderSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const filesList = e.target.files;
    if (!filesList || filesList.length === 0) return;

    const relativePath = filesList[0].webkitRelativePath;
    if (!relativePath) {
      toast.error("Browser did not return directory relative path");
      return;
    }

    const folderName = relativePath.split("/")[0];
    if (!folderName) return;

    await resolveAndLoadFolder(folderName);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const fetchFiles = useCallback(async (path?: string) => {
    setLoading(true);
    let targetPath = path || "";
    if (!targetPath) {
      const saved = window.localStorage.getItem("deepspace_active_folder_path");
      if (saved) {
        targetPath = saved;
      } else {
        const rootRes = await fetchWithAuth("/workspace/root");
        if (rootRes.ok) {
          const rootData = await rootRes.json();
          targetPath = rootData.path || "/home/sephi-asi/AverQel";
        } else {
          targetPath = "/home/sephi-asi/AverQel";
        }
      }
    }
    // Collapse duplicate slashes in the path (excluding protocol if there is one)
    const cleanedPath = targetPath.replace(/([^:]\/)\/+/g, "$1").trim();
    try {
      const res = await fetchWithAuth(`/workspace/files?path=${encodeURIComponent(cleanedPath)}`);
      if (res.ok) {
        const data = await res.json();
        setFiles(data);
        setCurrentPath(cleanedPath);
        setTempPath(cleanedPath);
        window.localStorage.setItem("deepspace_active_folder_path", cleanedPath);
        onFolderSelect?.(cleanedPath);
      }
    } catch (error) {
      console.error("Failed to fetch workspace files", error);
      toast.error("Failed to load files");
    } finally {
      setLoading(false);
    }
  }, [onFolderSelect]);

  useEffect(() => {
    const initializePath = async () => {
      try {
        const savedFolder = window.localStorage.getItem("deepspace_active_folder_path");
        if (savedFolder) {
          setCurrentPath(savedFolder);
          setTempPath(savedFolder);
          fetchFiles(savedFolder);
        } else {
          const res = await fetchWithAuth("/workspace/root");
          if (res.ok) {
            const data = await res.json();
            if (data.path) {
              setCurrentPath(data.path);
              setTempPath(data.path);
              window.localStorage.setItem("deepspace_active_folder_path", data.path);
              fetchFiles(data.path);
            }
          }
        }
      } catch (err) {
        console.error("Failed to initialize workspace folder path", err);
      }
    };
    void initializePath();
  }, []);

  useEffect(() => {
    if (isOpen && currentPath) {
      fetchFiles(currentPath);
    }
  }, [isOpen, fetchFiles, currentPath]);

  useEffect(() => {
    const handleWorkspaceRefresh = () => {
      if (currentPath) {
        fetchFiles(currentPath);
      }
    };
    window.addEventListener("averqel_workspace_refresh", handleWorkspaceRefresh);
    return () => {
      window.removeEventListener("averqel_workspace_refresh", handleWorkspaceRefresh);
    };
  }, [fetchFiles, currentPath]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;

    const path = currentPath === "." ? newName.trim() : `${currentPath}/${newName.trim()}`;
    const fullPath = isCreatingFolder ? `${path}/` : path;

    try {
      const res = await fetchWithAuth(`/workspace/file?path=${encodeURIComponent(fullPath)}`, {
        method: "POST",
      });
      if (res.ok) {
        toast.success(`${isCreatingFolder ? "Folder" : "File"} created`);
        setNewName("");
        setIsCreatingFile(false);
        setIsCreatingFolder(false);
        fetchFiles(currentPath);
      }
    } catch (error) {
      toast.error("Creation failed");
    }
  };

  const handleDelete = async (path: string) => {
    if (!confirm(`Permanently delete ${path}?`)) return;
    try {
      const res = await fetchWithAuth(
        `/workspace/file?path=${encodeURIComponent(path)}&recursive=true`,
        {
          method: "DELETE",
        },
      );
      if (res.ok) {
        toast.success("Deleted successfully");
        fetchFiles(currentPath);
      }
    } catch (error) {
      toast.error("Failed to delete");
    }
  };

  const handleRename = async (oldPath: string) => {
    const name = prompt("Enter new name:", oldPath.split("/").pop());
    if (!name || name === oldPath.split("/").pop()) return;

    const parent = oldPath.includes("/") ? oldPath.substring(0, oldPath.lastIndexOf("/")) : "";
    const newPath = parent ? `${parent}/${name}` : name;

    try {
      const res = await fetchWithAuth(
        `/workspace/file?old_path=${encodeURIComponent(oldPath)}&new_path=${encodeURIComponent(newPath)}`,
        {
          method: "PATCH",
        },
      );
      if (res.ok) {
        toast.success("Renamed successfully");
        fetchFiles(currentPath);
      }
    } catch (error) {
      toast.error("Rename failed");
    }
  };

  const handleCopyClipboard = (path: string) => {
    setClipboard({ path, action: "copy" });
    toast.success("Copied to clipboard. Navigate to destination folder and click Paste.");
  };

  const handleCutClipboard = (path: string) => {
    setClipboard({ path, action: "move" });
    toast.success("Cut to clipboard. Navigate to destination folder and click Paste.");
  };

  const handlePaste = async () => {
    if (!clipboard) return;
    const filename = clipboard.path.split("/").pop() || "";
    const destPath = currentPath === "." ? filename : `${currentPath}/${filename}`;

    if (clipboard.path === destPath) {
      toast.error("Source and destination paths are the same.");
      return;
    }

    setLoading(true);
    try {
      if (clipboard.action === "copy") {
        const res = await fetchWithAuth(
          `/workspace/copy?source_path=${encodeURIComponent(clipboard.path)}&destination_path=${encodeURIComponent(destPath)}`,
          {
            method: "POST",
          },
        );
        if (res.ok) {
          toast.success("Pasted copy successfully");
          setClipboard(null);
          fetchFiles(currentPath);
        } else {
          toast.error("Failed to paste copy");
        }
      } else {
        const res = await fetchWithAuth(
          `/workspace/file?old_path=${encodeURIComponent(clipboard.path)}&new_path=${encodeURIComponent(destPath)}`,
          {
            method: "PATCH",
          },
        );
        if (res.ok) {
          toast.success("Moved successfully");
          setClipboard(null);
          fetchFiles(currentPath);
        } else {
          toast.error("Failed to move");
        }
      }
    } catch (error) {
      toast.error("Operation failed");
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (path: string, name: string) => {
    try {
      const res = await fetchWithAuth(`/workspace/file/download?path=${encodeURIComponent(path)}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        a.click();
        window.URL.revokeObjectURL(url);
      } else {
        toast.error("Download failed");
      }
    } catch (error) {
      toast.error("Download failed");
    }
  };

  const renderFileIcon = (file: WorkspaceFile) => {
    if (file.type === "directory")
      return <Folder className="text-primary fill-primary/10 h-4 w-4" />;
    const ext = file.extension?.toLowerCase();
    if ([".js", ".ts", ".tsx", ".py", ".html", ".css"].includes(ext || ""))
      return <Cpu className="h-4 w-4 text-indigo-400" />;
    if (ext === ".pdf") return <File className="h-4 w-4 text-rose-400" />;
    if (ext === ".md") return <Zap className="h-4 w-4 fill-emerald-400/10 text-emerald-400" />;
    return <File className="text-foreground/40 h-4 w-4" />;
  };

  const goBack = () => {
    if (currentPath === "." || currentPath === "/") return;
    if (currentPath.startsWith("/")) {
      const parts = currentPath.split("/");
      parts.pop();
      const parent = parts.join("/") || "/";
      fetchFiles(parent);
    } else {
      const parts = currentPath.split("/");
      parts.pop();
      const parent = parts.length === 0 ? "." : parts.join("/");
      fetchFiles(parent);
    }
  };

  const containerClasses =
    variant === "sidebar"
      ? "flex h-full w-full flex-col overflow-hidden"
      : "theme-panel border-glass-border fixed top-24 bottom-6 left-6 z-50 flex w-80 flex-col overflow-hidden shadow-2xl backdrop-blur-2xl";

  return (
    <div className={containerClasses}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.02] p-4">
        <div className="flex items-center gap-3">
          <div className="bg-primary/10 rounded-lg p-2">
            <Monitor className="text-primary h-4 w-4" />
          </div>
          <div>
            <h3 className="text-[10px] font-black tracking-widest uppercase">Explorer</h3>
            <p className="text-foreground/40 text-[9px] font-bold">Workspace Root</p>
          </div>
        </div>
        {variant === "drawer" && (
          <button
            onClick={onClose}
            className="hover:bg-foreground/5 text-foreground/40 rounded-lg p-1.5 transition-colors"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Breadcrumbs / Back */}
      <div className="flex items-center gap-1.5 border-b border-white/5 bg-white/[0.01] px-3 py-2">
        <button
          onClick={goBack}
          disabled={currentPath === "." || currentPath === "/"}
          className="text-foreground/40 hover:text-foreground hover:bg-white/5 disabled:opacity-10 rounded-lg p-1.5 transition-all flex-shrink-0"
          title="Back to parent directory"
        >
          <ChevronLeft size={15} />
        </button>

        <div className="flex-1 flex items-center bg-black/40 border border-white/10 rounded-xl px-2.5 py-1 gap-2 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all min-w-0">
          <input
            type="text"
            value={tempPath}
            onChange={(e) => setTempPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                fetchFiles(tempPath.trim() || "/home/sephi-asi/AverQel");
              }
            }}
            placeholder="Type host path, e.g. /home/sephi-asi"
            className="flex-1 bg-transparent text-foreground text-[10px] font-mono outline-none placeholder:text-foreground/20 min-w-0"
          />
          {tempPath !== currentPath && (
            <button
              onClick={() => fetchFiles(tempPath.trim() || "/home/sephi-asi/AverQel")}
              className="px-2 py-0.5 rounded-md bg-primary/20 hover:bg-primary/30 text-primary text-[9px] font-bold uppercase tracking-wider transition-all flex-shrink-0"
            >
              Go
            </button>
          )}
          <button
            onClick={triggerFolderPicker}
            className="text-foreground/40 hover:text-primary transition-colors p-0.5 flex-shrink-0"
            title="Open native folder selector"
          >
            <FolderOpen size={14} />
          </button>
        </div>

        <button
          onClick={() => fetchFiles(currentPath)}
          className="text-foreground/40 hover:text-primary hover:bg-white/5 rounded-lg p-1.5 transition-all flex-shrink-0"
          title="Refresh directory"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* IDE Toolbar */}
      <div className="flex items-center gap-1 border-b border-white/5 bg-white/[0.03] p-1.5">
        <ToolbarButton
          icon={<FilePlus size={14} />}
          title="New File"
          onClick={() => {
            setIsCreatingFile(true);
            setIsCreatingFolder(false);
          }}
        />
        <ToolbarButton
          icon={<FolderPlus size={14} />}
          title="New Folder"
          onClick={() => {
            setIsCreatingFolder(true);
            setIsCreatingFile(false);
          }}
        />
        <div className="mx-1 h-4 w-px bg-white/5" />
        {clipboard && (
          <>
            <ToolbarButton
              icon={<ArrowRightLeft size={14} className="text-primary animate-pulse" />}
              title={`Paste (${clipboard.action === "copy" ? "Copy" : "Move"})`}
              onClick={handlePaste}
            />
            <ToolbarButton
              icon={<X size={14} className="text-foreground/40" />}
              title="Clear Clipboard"
              onClick={() => setClipboard(null)}
            />
          </>
        )}
      </div>

      {/* Inline Creation Form */}
      <AnimatePresence>
        {(isCreatingFile || isCreatingFolder) && (
          <motion.form
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            onSubmit={handleCreate}
            className="border-primary/20 bg-primary/5 space-y-2 overflow-hidden border-b p-3"
          >
            <div className="flex items-center gap-2">
              {isCreatingFolder ? (
                <Folder size={14} className="text-primary" />
              ) : (
                <File size={14} className="text-primary" />
              )}
              <input
                autoFocus
                placeholder={isCreatingFolder ? "Folder name..." : "file.txt..."}
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="text-foreground flex-1 bg-transparent text-xs font-bold outline-none"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setIsCreatingFile(false);
                  setIsCreatingFolder(false);
                  setNewName("");
                }}
                className="text-foreground/40 hover:text-foreground text-[9px] font-black tracking-widest uppercase"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="text-primary text-[9px] font-black tracking-widest uppercase hover:brightness-125"
              >
                Create
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {/* File Tree */}
      <div className="custom-scrollbar flex-1 overflow-y-auto bg-black/10 p-1">
        {files.length === 0 && !loading ? (
          <div className="flex h-full flex-col items-center justify-center p-8 text-center opacity-20">
            <Folder size={32} strokeWidth={1} />
            <p className="mt-2 text-[10px] font-bold tracking-widest uppercase">Empty</p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {files.map((file) => (
              <FileRow
                key={file.path}
                file={file}
                onSelect={(p) => (file.type === "directory" ? fetchFiles(p) : onFileSelect(p))}
                onDelete={handleDelete}
                onDownload={handleDownload}
                onRename={handleRename}
                onCopy={handleCopyClipboard}
                onCut={handleCutClipboard}
                renderIcon={renderFileIcon}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-white/5 bg-white/[0.02] px-4 py-2">
        <div className="text-foreground/20 flex items-center justify-between text-[8px] font-black tracking-[0.2em] uppercase">
          <span>{files.length} ITEMS</span>
          <span className="text-primary/40">IDE MODE</span>
        </div>
      </div>

      <FolderPickerDialog
        isOpen={isFolderPickerOpen}
        onClose={() => setIsFolderPickerOpen(false)}
        onSelect={(selectedPath) => {
          fetchFiles(selectedPath);
        }}
        initialPath={currentPath.startsWith("/") ? currentPath : "/home/sephi-asi"}
      />

      <input
        type="file"
        ref={fileInputRef}
        style={{ display: "none" }}
        {...({
          webkitdirectory: true,
          directory: true,
        } as unknown as React.InputHTMLAttributes<HTMLInputElement>)}
        onChange={handleNativeFolderSelect}
      />
    </div>
  );
}

function ToolbarButton({
  icon,
  title,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="hover:text-primary text-foreground/40 flex h-7 w-7 items-center justify-center rounded transition-all hover:bg-white/5"
    >
      {icon}
    </button>
  );
}

function FileRow({
  file,
  onSelect,
  onDelete,
  onDownload,
  onRename,
  onCopy,
  onCut,
  renderIcon,
}: {
  file: WorkspaceFile;
  onSelect: (path: string) => void;
  onDelete: (path: string) => void;
  onDownload: (path: string, name: string) => void;
  onRename: (path: string) => void;
  onCopy: (path: string) => void;
  onCut: (path: string) => void;
  renderIcon: (file: WorkspaceFile) => React.ReactNode;
}) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <div
      className="group relative flex cursor-pointer items-center rounded px-2 py-1 transition-all hover:bg-white/[0.04]"
      onClick={() => onSelect(file.path)}
    >
      <div className="mr-2 opacity-70 transition-opacity group-hover:opacity-100">
        {renderIcon(file)}
      </div>
      <span className="text-foreground/70 group-hover:text-foreground flex-1 truncate text-[11px] leading-none font-medium">
        {file.name}
      </span>

      <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        <RowAction
          icon={<Download size={12} />}
          onClick={(e) => {
            e.stopPropagation();
            onDownload(file.path, file.name);
          }}
          title="Download"
        />
        <RowAction
          icon={<Copy size={12} />}
          onClick={(e) => {
            e.stopPropagation();
            onCopy(file.path);
          }}
          title="Copy to clipboard"
        />
        <RowAction
          icon={<ArrowRightLeft size={12} />}
          onClick={(e) => {
            e.stopPropagation();
            onCut(file.path);
          }}
          title="Cut / Move path"
        />
        <RowAction
          icon={<Edit2 size={12} />}
          onClick={(e) => {
            e.stopPropagation();
            onRename(file.path);
          }}
          title="Rename"
        />
        <RowAction
          icon={<Trash2 size={12} />}
          onClick={(e) => {
            e.stopPropagation();
            onDelete(file.path);
          }}
          title="Delete"
          tone="rose"
        />
      </div>
    </div>
  );
}

function RowAction({
  icon,
  onClick,
  title,
  tone = "primary",
}: {
  icon: React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  title: string;
  tone?: "primary" | "rose";
}) {
  const toneClass = tone === "rose" ? "hover:text-rose-400" : "hover:text-primary";
  return (
    <button
      onClick={onClick}
      title={title}
      className={`text-foreground/20 p-1 transition-colors ${toneClass}`}
    >
      {icon}
    </button>
  );
}
