"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  CheckSquare,
  History,
  MessageSquare,
  Pencil,
  Plus,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { fetchWithAuth } from "@/lib/api";
import ConfirmationModal from "@/app/components/ui/ConfirmationModal";

interface Conversation {
  id: string;
  title: string;
  updated_at: string;
  live_status?: string | null;
  live_mission_id?: string | null;
}

interface ChatSidebarProps {
  currentConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  endpointBase?: string;
  variant?: "dock" | "floating";
  onClose?: () => void;
  enableRename?: boolean;
  onConversationRenamed?: (conversation: Conversation) => void;
  children?: React.ReactNode;
}

export default function ChatSidebar({
  currentConversationId,
  onSelectConversation,
  onNewChat,
  endpointBase = "/chats",
  variant = "dock",
  onClose,
  enableRename = true,
  onConversationRenamed,
  children,
}: ChatSidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteDialog, setDeleteDialog] = useState<
    { type: "single"; id: string; title: string } | { type: "bulk"; ids: string[] } | null
  >(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const fetchConversations = useCallback(async () => {
    try {
      const res = (await fetchWithAuth(endpointBase)) as Response;
      if (res.ok) {
        const data = await res.json();
        setConversations(data.items);
        setError(null);
      } else {
        // Keep the last known list visible during an API/VPS outage. Clearing
        // it makes persisted chats appear deleted and loses the operator's
        // ability to see which session was last active.
        setError(
          res.status === 401
            ? "Session expired. Redirecting to login..."
            : "Failed to load conversations.",
        );
      }
    } catch (error) {
      console.error("Failed to fetch conversations", error);
      // Stale-but-visible history is safer than an empty history during a
      // transient disconnect or server restart.
      setError("Failed to load conversations.");
    } finally {
      setLoading(false);
    }
  }, [endpointBase]);

  useEffect(() => {
    fetchConversations();
    const interval = setInterval(fetchConversations, 10000);
    return () => clearInterval(interval);
  }, [fetchConversations]);

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    const conversation = conversations.find((item) => item.id === id);
    setDeleteDialog({
      type: "single",
      id,
      title: conversation?.title ?? "this conversation",
    });
  };

  const handleBulkDelete = () => {
    if (selectedIds.size === 0) return;
    setDeleteDialog({ type: "bulk", ids: Array.from(selectedIds) });
  };

  const confirmDelete = async () => {
    if (!deleteDialog || deleteBusy) return;

    setDeleteBusy(true);
    try {
      if (deleteDialog.type === "single") {
        const res = (await fetchWithAuth(`${endpointBase}/${deleteDialog.id}`, {
          method: "DELETE",
        })) as Response;
        if (res.ok || res.status === 404) {
          setConversations((prev) => prev.filter((item) => item.id !== deleteDialog.id));
          if (deleteDialog.id === currentConversationId) onNewChat();
        } else {
          return;
        }
      } else {
        const res = (await fetchWithAuth(`${endpointBase}/bulk-delete`, {
          method: "POST",
          body: JSON.stringify({ conversation_ids: deleteDialog.ids }),
        })) as Response;

        if (!res.ok) {
          return;
        }

        setConversations((prev) => prev.filter((item) => !deleteDialog.ids.includes(item.id)));
        if (deleteDialog.ids.includes(currentConversationId || "")) {
          onNewChat();
        }
        setSelectedIds(new Set());
        setSelectionMode(false);
      }
      setDeleteDialog(null);
    } catch (error) {
      console.error("Delete failed", error);
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleRename = async (e: React.MouseEvent, conversation: Conversation) => {
    e.stopPropagation();
    const nextTitle = window.prompt("Rename conversation", conversation.title)?.trim();
    if (!nextTitle || nextTitle === conversation.title) {
      return;
    }

    try {
      const res = (await fetchWithAuth(`${endpointBase}/${conversation.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: nextTitle }),
      })) as Response;

      if (!res.ok) {
        throw new Error(`Rename failed with status ${res.status}`);
      }

      const updated = (await res.json()) as Conversation;
      setConversations((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      onConversationRenamed?.(updated);
    } catch (error) {
      console.error("Rename failed", error);
    }
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === conversations.length && conversations.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(conversations.map((c) => c.id)));
    }
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  return (
    <aside
      className={
        variant === "floating"
          ? "theme-panel relative flex h-full w-full flex-col rounded-[1.75rem] border p-4 shadow-[0_22px_80px_rgba(0,0,0,0.34)] backdrop-blur-xl sm:p-5"
          : "theme-panel hidden w-80 shrink-0 border-l p-4 lg:flex lg:flex-col lg:p-5"
      }
    >
      <div className="border-glass-border mb-5 flex items-center justify-between border-b pb-4">
        <div className="text-foreground/86 flex items-center gap-3">
          <History size={18} className="!stroke-primary text-primary stroke-[2.5]" />

          <h2 className="text-sm font-semibold tracking-[0.18em] uppercase">
            {selectionMode ? "Select Items" : "History"}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {conversations.length > 0 && (
            <button
              onClick={() => {
                setSelectionMode(!selectionMode);
                setSelectedIds(new Set());
              }}
              className={`inline-flex h-9 items-center gap-2 rounded-2xl border px-3 text-xs font-bold transition ${
                selectionMode
                  ? "border-primary bg-primary/10 text-primary"
                  : "text-foreground/60 hover:text-foreground border-white/10 bg-white/5"
              }`}
            >
              {selectionMode ? "Cancel" : "Select"}
            </button>
          )}
          {!selectionMode && (
            <button
              onClick={onNewChat}
              className="bg-primary/10 text-primary border-primary/20 hover:bg-primary/20 inline-flex h-9 w-9 items-center justify-center rounded-2xl border transition"
              title="New conversation"
            >
              <Plus size={16} className="!stroke-primary text-primary stroke-[3]" />
            </button>
          )}
          {variant === "floating" && onClose ? (
            <button
              onClick={onClose}
              className="text-foreground/56 hover:text-foreground inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-white/10 transition"
              title="Close"
            >
              <X size={16} />
            </button>
          ) : null}
        </div>
      </div>

      {selectionMode && conversations.length > 0 && (
        <div className="mb-4 flex items-center justify-between rounded-xl bg-white/5 p-2 px-3">
          <button
            onClick={toggleSelectAll}
            className="text-foreground/70 hover:text-foreground flex items-center gap-2 text-xs font-medium"
          >
            {selectedIds.size === conversations.length ? (
              <CheckSquare size={14} className="text-primary" />
            ) : (
              <Square size={14} />
            )}
            Select All
          </button>
          <span className="text-foreground/40 text-[10px] font-bold tracking-wider uppercase">
            {selectedIds.size} Selected
          </span>
        </div>
      )}

      <div className="custom-scrollbar scrollbar-hide flex-1 space-y-2 overflow-y-auto pr-1">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((index) => (
              <div
                key={index}
                className="bg-foreground/[0.05] h-16 animate-pulse rounded-2xl dark:bg-white/[0.04]"
              />
            ))}
          </div>
        ) : error ? (
          <div className="border-glass-border bg-foreground/[0.02] text-foreground/48 rounded-2xl border px-4 py-6 text-center text-sm dark:bg-white/[0.025]">
            {error}
          </div>
        ) : conversations.length > 0 ? (
          <AnimatePresence mode="popLayout">
            {conversations.map((conv) => (
              <motion.div
                key={conv.id}
                layout
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 8 }}
                role="button"
                tabIndex={0}
                onClick={() =>
                  selectionMode ? toggleSelect(conv.id) : onSelectConversation(conv.id)
                }
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    if (selectionMode) {
                      toggleSelect(conv.id);
                    } else {
                      onSelectConversation(conv.id);
                    }
                  }
                }}
                className={`group relative w-full rounded-2xl border px-4 py-3 text-left transition-all duration-200 ${
                  currentConversationId === conv.id && !selectionMode
                    ? "border-primary/30 bg-primary/10 text-primary dark:border-primary/40 dark:bg-primary/20 dark:text-primary shadow-sm dark:shadow-[0_12px_32px_-8px_rgba(0,0,0,0.5)]"
                    : selectedIds.has(conv.id)
                      ? "text-foreground border-primary/30 bg-primary/5"
                      : "border-glass-border bg-foreground/[0.02] text-foreground/78 hover:border-glass-border hover:bg-foreground/[0.04] dark:bg-white/[0.025] dark:hover:bg-white/[0.04]"
                }`}
              >
                <div className="flex items-start gap-3">
                  {selectionMode ? (
                    <div
                      className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition ${
                        selectedIds.has(conv.id)
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-white/20 bg-white/5"
                      }`}
                    >
                      {selectedIds.has(conv.id) && <Check size={12} strokeWidth={4} />}
                    </div>
                  ) : (
                    <MessageSquare
                      size={15}
                      className={`mt-0.5 shrink-0 ${currentConversationId === conv.id ? "text-primary dark:text-primary" : "text-foreground/62"}`}
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <p
                      className={`truncate text-sm font-semibold ${currentConversationId === conv.id && !selectionMode ? "text-primary dark:text-primary" : ""}`}
                    >
                      {conv.title}
                    </p>
                    {conv.live_status ? (
                      <span className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold tracking-[0.12em] text-emerald-500 uppercase">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                        {conv.live_status === "awaiting_approval"
                          ? "Needs approval"
                          : conv.live_status}
                      </span>
                    ) : null}
                    <p
                      className={`mt-1 text-[11px] font-medium ${currentConversationId === conv.id && !selectionMode ? "text-primary/70 dark:text-primary/70" : "text-foreground/45"}`}
                      suppressHydrationWarning
                    >
                      {new Date(conv.updated_at).toLocaleDateString([], {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                  {!selectionMode ? (
                    <div
                      className={`flex items-center gap-1.5 transition ${
                        currentConversationId === conv.id
                          ? "opacity-100"
                          : "opacity-0 group-hover:opacity-100"
                      }`}
                    >
                      {enableRename ? (
                        <button
                          onClick={(e) => handleRename(e, conv)}
                          className={`flex h-8 w-8 items-center justify-center rounded-full transition-all duration-200 ${
                            currentConversationId === conv.id
                              ? "text-primary/70 hover:bg-primary/20 hover:text-primary dark:text-primary/70 dark:hover:bg-primary/20 dark:hover:text-primary"
                              : "text-foreground/30 hover:bg-primary/10 hover:text-primary"
                          }`}
                          title="Rename conversation"
                        >
                          <Pencil size={14} />
                        </button>
                      ) : null}
                      <button
                        onClick={(e) => handleDelete(e, conv.id)}
                        className={`flex h-8 w-8 items-center justify-center rounded-full transition-all duration-200 ${
                          currentConversationId === conv.id
                            ? "text-primary/70 dark:text-primary/70 hover:bg-red-500/20 hover:text-red-500 dark:hover:bg-red-500/20 dark:hover:text-red-400"
                            : "text-foreground/30 hover:bg-red-500/10 hover:text-red-500"
                        }`}
                        title="Delete conversation"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ) : null}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        ) : (
          <div className="border-glass-border bg-foreground/[0.02] text-foreground/48 rounded-2xl border px-4 py-6 text-center text-sm dark:bg-white/[0.025]">
            No conversation history yet.
          </div>
        )}
      </div>

      {selectionMode && selectedIds.size > 0 && (
        <div className="mt-4 border-t border-white/10 pt-4">
          <button
            onClick={handleBulkDelete}
            className="flex w-full items-center justify-center gap-2 rounded-2xl border border-red-500/20 bg-red-500/10 py-3 text-sm font-bold text-red-400 transition hover:bg-red-500/20"
          >
            <Trash2 size={16} />
            Delete Selected ({selectedIds.size})
          </button>
        </div>
      )}

      {children && <div className="mt-4 border-t border-white/5 pt-4">{children}</div>}

      <ConfirmationModal
        isOpen={deleteDialog !== null}
        onClose={() => {
          if (deleteBusy) return;
          setDeleteDialog(null);
        }}
        onConfirm={() => void confirmDelete()}
        title={
          deleteDialog?.type === "bulk"
            ? `Delete ${deleteDialog.ids.length} conversations?`
            : `Delete “${deleteDialog?.title ?? "this conversation"}”?`
        }
        message={
          deleteDialog?.type === "bulk"
            ? "This permanently removes the selected conversations from AverQel history. You can’t undo this action."
            : "This permanently removes the conversation from AverQel history. You can’t undo this action."
        }
        confirmLabel={deleteDialog?.type === "bulk" ? "Delete Conversations" : "Delete"}
        loading={deleteBusy}
      />
    </aside>
  );
}
