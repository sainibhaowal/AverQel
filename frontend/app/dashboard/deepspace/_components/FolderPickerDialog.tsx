"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Folder, ChevronLeft, RefreshCw, X, FolderPlus, ArrowUpRight } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import toast from "react-hot-toast";

interface FolderPickerDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  initialPath?: string;
}

interface WorkspaceFolder {
  name: string;
  path: string;
  type: "directory";
}

export default function FolderPickerDialog({
  isOpen,
  onClose,
  onSelect,
  initialPath = "/home/ravi",
}: FolderPickerDialogProps) {
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [folders, setFolders] = useState<WorkspaceFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");

  const fetchFolders = useCallback(async (path: string) => {
    setLoading(true);
    setSelectedPath(null);
    try {
      const res = await fetchWithAuth(`/workspace/files?path=${encodeURIComponent(path)}`);
      if (res.ok) {
        const data = await res.json();
        // Filter only directories
        const directories = Array.isArray(data)
          ? data.filter(
              (item): item is WorkspaceFolder =>
                Boolean(item) &&
                typeof item === "object" &&
                (item as { type?: unknown }).type === "directory",
            )
          : [];
        setFolders(directories);
        setCurrentPath(path);
      } else {
        toast.error("Failed to load path directory content");
      }
    } catch (error) {
      console.error("Failed to fetch folders", error);
      toast.error("Failed to read location");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchFolders(initialPath);
    }
  }, [isOpen, fetchFolders, initialPath]);

  const handleFolderDoubleClick = (path: string) => {
    fetchFolders(path);
  };

  const handleGoUp = () => {
    if (currentPath === "/" || currentPath === ".") return;
    const parts = currentPath.split("/");
    parts.pop();
    const parent = parts.join("/") || "/";
    fetchFolders(parent);
  };

  const handleCreateFolder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFolderName.trim()) return;

    const fullPath = currentPath === "/" ? `/${newFolderName.trim()}/` : `${currentPath}/${newFolderName.trim()}/`;
    try {
      const res = await fetchWithAuth(`/workspace/file?path=${encodeURIComponent(fullPath)}`, {
        method: "POST",
      });
      if (res.ok) {
        toast.success("Folder created successfully");
        setNewFolderName("");
        setIsCreatingFolder(false);
        fetchFolders(currentPath);
      }
    } catch (error) {
      toast.error("Failed to create folder");
    }
  };

  const handleSelect = () => {
    const finalSelection = selectedPath || currentPath;
    onSelect(finalSelection);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="border-glass-border bg-[#050507]/95 flex h-[480px] w-full max-w-lg flex-col overflow-hidden rounded-2xl border shadow-2xl transition duration-200">

        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.02] p-4 select-none">
          <div className="flex items-center gap-3">
            <div className="bg-primary/10 rounded-lg p-2">
              <Folder className="text-primary h-4 w-4" />
            </div>
            <div>
              <h3 className="text-xs font-black tracking-widest uppercase text-foreground">Open Folder</h3>
              <p className="text-foreground/40 text-[9px] font-bold">Select working directory location</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="hover:bg-white/5 text-foreground/40 hover:text-foreground rounded-lg p-1.5 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Toolbar Path Input & Back Control */}
        <div className="flex items-center gap-2 border-b border-white/5 bg-white/[0.01] px-4 py-2 select-none">
          <button
            onClick={handleGoUp}
            disabled={currentPath === "/" || currentPath === "."}
            className="text-foreground/60 rounded p-1 transition-all hover:bg-white/5 disabled:opacity-20"
            title="Go up one folder"
          >
            <ChevronLeft size={14} />
          </button>

          <input
            type="text"
            value={currentPath}
            onChange={(e) => setCurrentPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                fetchFolders(currentPath.trim() || "/home/ravi");
              }
            }}
            className="flex-1 bg-black/35 text-foreground border border-white/10 rounded-lg px-2.5 py-1 text-[10px] font-mono outline-none focus:border-primary/50"
          />

          <button
            onClick={() => fetchFolders(currentPath)}
            className="hover:text-primary text-foreground/40 transition-colors"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>

          <button
            onClick={() => setIsCreatingFolder(!isCreatingFolder)}
            className={`p-1 rounded hover:bg-white/5 transition ${isCreatingFolder ? "text-primary" : "text-foreground/40"}`}
            title="Create new folder"
          >
            <FolderPlus size={14} />
          </button>
        </div>

        {/* Inline Create Folder Input */}
        {isCreatingFolder && (
          <form onSubmit={handleCreateFolder} className="border-b border-white/5 bg-primary/5 px-4 py-2 flex items-center gap-2">
            <input
              type="text"
              autoFocus
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="New folder name..."
              className="flex-1 bg-transparent text-[11px] font-semibold text-foreground border-none outline-none"
            />
            <button type="submit" className="text-primary text-[9px] font-bold uppercase hover:brightness-110">Create</button>
            <button type="button" onClick={() => setIsCreatingFolder(false)} className="text-foreground/30 text-[9px] font-bold uppercase hover:text-foreground">Cancel</button>
          </form>
        )}

        {/* Folders List Area */}
        <div className="custom-scrollbar flex-1 overflow-y-auto bg-black/10 p-2">
          {loading ? (
            <div className="flex h-full items-center justify-center opacity-25">
              <RefreshCw className="animate-spin text-foreground h-6 w-6" />
            </div>
          ) : folders.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center p-8 text-center opacity-20 select-none">
              <Folder size={32} strokeWidth={1} />
              <p className="mt-2 text-[10px] font-bold tracking-widest uppercase">No Subfolders</p>
            </div>
          ) : (
            <div className="space-y-0.5 select-none">
              {folders.map((f) => (
                <div
                  key={f.path}
                  onClick={() => setSelectedPath(f.path)}
                  onDoubleClick={() => handleFolderDoubleClick(f.path)}
                  className={`group flex cursor-pointer items-center rounded px-3 py-1.5 transition-all ${
                    selectedPath === f.path
                      ? "bg-primary/20 border-l-2 border-primary"
                      : "hover:bg-white/[0.03]"
                  }`}
                >
                  <Folder className="mr-2.5 text-primary fill-primary/10 h-3.5 w-3.5 flex-shrink-0" />
                  <span className={`text-[11px] truncate flex-1 font-semibold ${selectedPath === f.path ? "text-primary font-bold" : "text-foreground/70"}`}>
                    {f.name}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleFolderDoubleClick(f.path);
                    }}
                    title="Open folder contents"
                    className="p-1 text-foreground/20 hover:text-primary transition rounded hover:bg-white/5 opacity-0 group-hover:opacity-100"
                  >
                    <ArrowUpRight size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="border-t border-white/5 bg-white/[0.02] px-4 py-3 flex items-center justify-between select-none">
          <div className="text-[10px] truncate max-w-[55%] text-foreground/45 font-mono">
            {selectedPath ? `Selected: ${selectedPath.split("/").pop()}` : `Current: ${currentPath.split("/").pop() || "/"}`}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="border border-white/10 hover:bg-white/5 text-foreground/60 hover:text-foreground text-[10px] font-bold tracking-wider uppercase rounded-xl px-4 py-1.5 transition"
            >
              Cancel
            </button>
            <button
              onClick={handleSelect}
              className="bg-primary hover:bg-primary/80 text-primary-foreground text-[10px] font-bold tracking-wider uppercase rounded-xl px-4 py-1.5 transition shadow-[0_0_15px_rgba(var(--primary),0.3)]"
            >
              Select Folder
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
