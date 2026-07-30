"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Columns2,
  GripVertical,
  Loader2,
  PanelRightClose,
  Bot,
  Database,
  PanelLeftClose,
  History,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { fetchWithAuth } from "@/lib/api";
import type { Transition } from "framer-motion";
import toast from "react-hot-toast";

import DeepSpaceChatClient from "./DeepSpaceChatClient";
import DeepSpaceEditor, { type DeepSpaceEditorHandle } from "./DeepSpaceEditor";
import MemoryPanel from "./MemoryPanel";

export interface DeepSpaceNote {
  id: string;
  title: string;
  updated_at: string;
  content_html?: string | null;
}

const STORAGE_KEY = "averqel_deepspace_draft";
const ACTIVE_NOTE_KEY = "averqel_deepspace_active_conversation";
const MIN_LEFT_WIDTH = 32;
const MAX_LEFT_WIDTH = 68;
const DEFAULT_NOTE_TITLE = "Untitled Note";
const MOBILE_STACKED_BREAKPOINT = 1024;
const DEEPSPACE_INITIAL_LOAD_GRACE_MS = 2_500;

function IconTooltipButton({
  label,
  active,
  icon,
  onClick,
}: {
  label: string;
  active: boolean;
  icon: ReactNode;
  onClick: () => void;
}) {
  const [open, setOpen] = useState(false);
  const pressTimerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (pressTimerRef.current) window.clearTimeout(pressTimerRef.current);
    },
    [],
  );

  const hide = () => {
    setOpen(false);
    if (pressTimerRef.current) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
  };

  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") setOpen(true);
      }}
      onPointerLeave={hide}
      onFocus={() => setOpen(true)}
      onBlur={hide}
      onPointerDown={(event) => {
        if (event.pointerType === "touch" || event.pointerType === "pen") {
          pressTimerRef.current = window.setTimeout(() => setOpen(true), 450);
        }
      }}
      onPointerUp={hide}
      onPointerCancel={hide}
      className={`group relative inline-flex h-8 w-8 items-center justify-center rounded-full transition-all sm:h-10 sm:w-10 ${
        active
          ? "bg-primary text-primary-foreground shadow-[0_0_15px_rgba(var(--primary),0.3)]"
          : "text-foreground/70 hover:bg-surface-2 hover:text-primary"
      }`}
    >
      {icon}
      <span
        className={`pointer-events-none absolute top-full left-1/2 z-40 mt-2 -translate-x-1/2 rounded-full border border-white/10 bg-black/85 px-3 py-1 text-[10px] font-semibold tracking-[0.22em] whitespace-nowrap text-white uppercase shadow-[0_12px_30px_rgba(0,0,0,0.35)] transition ${
          open ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"
        }`}
      >
        {label}
      </span>
    </button>
  );
}

function stripHtml(html: string): string {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function deriveNoteTitleFromContent(html: string): string | null {
  const plainText = stripHtml(html);
  if (!plainText) return null;
  const normalized = plainText.slice(0, 60).trim();
  if (!normalized) return null;
  return normalized.length < plainText.length ? `${normalized}...` : normalized;
}

export default function DeepSpacePageClient() {
  const [notes, setNotes] = useState<DeepSpaceNote[]>([]);
  const [activeNote, setActiveNote] = useState<DeepSpaceNote | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [panelMode, setPanelMode] = useState<"split" | "notes" | "chat" | "memory">("split");
  const editorRef = useRef<DeepSpaceEditorHandle>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [serviceWarnings, setServiceWarnings] = useState<string[]>([]);
  const [serviceRetryKey, setServiceRetryKey] = useState(0);

  const [leftWidth, setLeftWidth] = useState(48);
  const [isDragging, setIsDragging] = useState(false);
  const [containerWidth, setContainerWidth] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(0);
  const splitContainerRef = useRef<HTMLDivElement | null>(null);
  const activeDividerPointerIdRef = useRef<number | null>(null);
  const [mounted, setMounted] = useState(false);

  const addServiceWarning = useCallback((message: string) => {
    setServiceWarnings((previous) =>
      previous.includes(message) ? previous : [...previous, message].slice(-3),
    );
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  // ── Data Fetching ────────────────────────────────────────────────────────

  const fetchNotes = useCallback(async () => {
    try {
      const res = (await fetchWithAuth("/deepspace/chats", { timeoutMs: 5_000 })) as Response;
      if (res.ok) {
        const data = await res.json();
        const items = data.items as DeepSpaceNote[];
        setNotes(items);
        return items;
      }
    } catch (err) {
      console.error("Failed to fetch notes", err);
    }
    return null;
  }, []);

  const createNote = async (title = "Untitled Note", content = "") => {
    try {
      const res = (await fetchWithAuth("/deepspace/chats", {
        method: "POST",
        timeoutMs: 5_000,
        body: JSON.stringify({ title, content_html: content }),
      })) as Response;
      if (res.ok) {
        const newNote = await res.json();
        setNotes((prev) => [newNote, ...prev]);
        setActiveNote(newNote);
        return newNote;
      }
    } catch (err) {
      console.error("Failed to create note", err);
    }
    return null;
  };

  const activeNoteId = activeNote?.id ?? null;

  // ── Lifecycle & Migration ────────────────────────────────────────────────

  useEffect(() => {
    let mounted = true;
    const releaseTimer = window.setTimeout(() => {
      if (!mounted) return;
      setIsInitialLoading(false);
      addServiceWarning(
        "Conversation history is taking longer than expected; the workspace remains available.",
      );
    }, DEEPSPACE_INITIAL_LOAD_GRACE_MS);

    const init = async () => {
      const items = await fetchNotes();
      if (!mounted) return;
      window.clearTimeout(releaseTimer);
      if (items === null) {
        // Do not create a replacement conversation when the VPS is briefly
        // unavailable; that would make the real history appear lost.
        setIsInitialLoading(false);
        addServiceWarning("Conversation history is temporarily unavailable.");
        return;
      }
      if (items.length === 0) {
        const localDraft = window.localStorage.getItem(STORAGE_KEY);
        if (localDraft) {
          await createNote("My First Note", localDraft);
          window.localStorage.removeItem(STORAGE_KEY);
        } else {
          await createNote();
        }
      } else {
        const savedId = window.localStorage.getItem(ACTIVE_NOTE_KEY);
        setActiveNote(items.find((item) => item.id === savedId) || items[0] || null);
      }
      setIsInitialLoading(false);
      setServiceWarnings((previous) =>
        previous.filter((warning) => !warning.toLowerCase().includes("conversation history")),
      );
    };
    void init();

    return () => {
      mounted = false;
      window.clearTimeout(releaseTimer);
    };
  }, [addServiceWarning, fetchNotes, serviceRetryKey]);

  // Keep the selected conversation stable across route changes, refreshes,
  // browser restarts, and returning from another dashboard page. The message
  // history itself remains server-owned; this key stores only the selection.
  useEffect(() => {
    if (activeNote?.id) {
      window.localStorage.setItem(ACTIVE_NOTE_KEY, activeNote.id);
    }
  }, [activeNote?.id]);

  // ── Auto-save ────────────────────────────────────────────────────────────

  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);

  const handleEditorChange = (html: string) => {
    if (!activeNote) return;
    const nextAutoTitle =
      activeNote.title === DEFAULT_NOTE_TITLE ? deriveNoteTitleFromContent(html) : null;
    setActiveNote((prev) =>
      prev ? { ...prev, content_html: html, title: nextAutoTitle ?? prev.title } : null,
    );
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setIsSaving(true);
    saveTimerRef.current = setTimeout(async () => {
      try {
        await fetchWithAuth(`/deepspace/chats/${activeNote.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            content_html: html,
            ...(nextAutoTitle ? { title: nextAutoTitle } : {}),
          }),
        });
      } finally {
        setIsSaving(false);
      }
    }, 1500);
  };

  // ── Layout & Resizing ────────────────────────────────────────────────────

  useEffect(() => {
    const container = splitContainerRef.current;
    if (!container) return;
    const updateWidth = () => setContainerWidth(container.getBoundingClientRect().width);
    updateWidth();
    const observer = new ResizeObserver(() => updateWidth());
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const updateViewport = () =>
      setViewportWidth(window.visualViewport?.width || window.innerWidth || 0);
    updateViewport();
    window.addEventListener("resize", updateViewport);
    window.visualViewport?.addEventListener("resize", updateViewport);
    return () => {
      window.removeEventListener("resize", updateViewport);
      window.visualViewport?.removeEventListener("resize", updateViewport);
    };
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    const handlePointerMove = (event: PointerEvent) => {
      if (
        activeDividerPointerIdRef.current !== null &&
        event.pointerId !== activeDividerPointerIdRef.current
      )
        return;
      if (event.cancelable) event.preventDefault();
      const container = splitContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const nextWidth = ((event.clientX - rect.left) / rect.width) * 100;
      setLeftWidth(Math.min(MAX_LEFT_WIDTH, Math.max(MIN_LEFT_WIDTH, nextWidth)));
    };
    const stopDragging = () => {
      activeDividerPointerIdRef.current = null;
      setIsDragging(false);
    };
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDragging);
    window.addEventListener("pointercancel", stopDragging);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDragging);
      window.removeEventListener("pointercancel", stopDragging);
    };
  }, [isDragging]);

  const insertAnswer = (content: string) => {
    if (!content.trim()) return;
    editorRef.current?.insertMarkdown(content.trim());
  };

  const isStackedLayout = viewportWidth > 0 && viewportWidth < MOBILE_STACKED_BREAKPOINT;
  const showNotesPanel = panelMode === "split" || panelMode === "notes";
  const showChatPanel = panelMode === "split" || panelMode === "chat";
  const showMemoryPanel = panelMode === "memory";
  const panelTransition: Transition = isStackedLayout
    ? { duration: 0.16, ease: "easeOut" }
    : { type: "spring", damping: 24, stiffness: 220 };
  const shellTransitionClass = isStackedLayout ? "duration-150" : "duration-300";

  useEffect(() => {
    if (isStackedLayout && panelMode === "split") setPanelMode("chat");
  }, [isStackedLayout, panelMode]);

  const collapseChat = () => {
    setPanelMode("notes");
  };

  if (isInitialLoading) {
    return (
      <div className="theme-panel-muted flex h-full w-full items-center justify-center rounded-2xl">
        <Loader2 className="text-primary h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="relative flex h-full w-full overflow-hidden rounded-2xl bg-transparent">
      {serviceWarnings.length > 0 && (
        <div className="pointer-events-none absolute top-2 right-2 left-2 z-30 flex justify-center">
          <div
            role="status"
            className="pointer-events-auto flex max-w-3xl items-center gap-3 rounded-xl border border-amber-400/25 bg-amber-950/80 px-4 py-3 text-xs text-amber-100 shadow-xl backdrop-blur-xl"
          >
            <span className="min-w-0 flex-1">{serviceWarnings.join(" ")}</span>
            <button
              type="button"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-amber-300/25 px-2.5 py-1.5 font-semibold hover:bg-amber-300/10"
              onClick={() => {
                setServiceWarnings([]);
                setIsInitialLoading(true);
                setServiceRetryKey((value) => value + 1);
              }}
            >
              <RefreshCw size={12} />
              Retry
            </button>
          </div>
        </div>
      )}

      <div
        className={`relative flex h-full flex-1 flex-col overflow-hidden ${
          isDragging
            ? "cursor-col-resize transition-none select-none"
            : `transition-colors ${shellTransitionClass}`
        }`}
      >
        {(() => {
          const portalTarget =
            typeof document !== "undefined"
              ? document.getElementById("header-layout-controls")
              : null;
          const shouldRenderPortal = mounted && portalTarget;

          if (shouldRenderPortal) {
            return createPortal(
              <div className="border-glass-border bg-surface-0/90 pointer-events-auto flex items-center gap-0.5 rounded-full border p-0.5 shadow-xl backdrop-blur-md sm:gap-1 sm:p-1">
                <IconTooltipButton
                  label="Chat"
                  active={panelMode === "chat"}
                  icon={<Bot size={18} />}
                  onClick={() => setPanelMode("chat")}
                />
                <IconTooltipButton
                  label="Memory"
                  active={panelMode === "memory"}
                  icon={<Database size={18} />}
                  onClick={() => setPanelMode("memory")}
                />
                <IconTooltipButton
                  label="Split view"
                  active={panelMode === "split"}
                  icon={<Columns2 size={15} />}
                  onClick={() => setPanelMode("split")}
                />
                <IconTooltipButton
                  label="Notes only"
                  active={panelMode === "notes"}
                  icon={<PanelRightClose size={15} />}
                  onClick={() => setPanelMode("notes")}
                />
                <IconTooltipButton
                  label="History"
                  active={isHistoryOpen}
                  icon={<History size={16} />}
                  onClick={() => setIsHistoryOpen(!isHistoryOpen)}
                />
              </div>,
              portalTarget,
            );
          }

          return null;
        })()}

        <div
          ref={splitContainerRef}
          className={`relative flex h-full max-h-full min-h-0 flex-1 overflow-hidden ${isStackedLayout ? "flex-col" : "flex-row"}`}
        >
          <AnimatePresence initial={false} mode="popLayout">
            {showNotesPanel ? (
              <motion.section
                key="notes-panel"
                initial={{ opacity: 0, x: isStackedLayout ? 0 : -24, y: isStackedLayout ? -24 : 0 }}
                animate={{ opacity: 1, x: 0, y: 0 }}
                exit={{ opacity: 0, x: isStackedLayout ? 0 : -24, y: isStackedLayout ? -24 : 0 }}
                transition={panelTransition}
                className={`relative flex min-h-0 min-w-0 flex-col overflow-hidden ${isStackedLayout ? "h-full w-full flex-[1_1_auto]" : showChatPanel ? "h-full flex-[0_0_auto]" : "h-full w-full"}`}
                style={
                  !isStackedLayout && showChatPanel ? { flexBasis: `${leftWidth}%` } : undefined
                }
              >
                <DeepSpaceEditor
                  ref={editorRef}
                  initialContent={activeNote?.content_html || ""}
                  onChange={handleEditorChange}
                  conversationId={activeNote?.id}
                  isSaving={isSaving}
                  showCollapseControls={false}
                  panelMode={panelMode}
                  onSetPanelMode={setPanelMode}
                />
              </motion.section>
            ) : null}
          </AnimatePresence>

          {showNotesPanel && showChatPanel && !isStackedLayout ? (
            <div
              role="separator"
              aria-label="Resize deepspace panels"
              onPointerDown={(e) => {
                e.preventDefault();
                e.currentTarget.setPointerCapture(e.pointerId);
                activeDividerPointerIdRef.current = e.pointerId;
                setIsDragging(true);
              }}
              onPointerUp={(e) => {
                if (isDragging) {
                  e.currentTarget.releasePointerCapture(e.pointerId);
                  activeDividerPointerIdRef.current = null;
                  setIsDragging(false);
                }
              }}
              className={`relative z-10 w-5 shrink-0 cursor-col-resize touch-none ${isDragging ? "bg-primary/10" : "hover:bg-primary/5"}`}
            >
              <div
                className={`bg-glass-border absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors ${isDragging ? "bg-primary/40" : ""}`}
              />
              <div className="pointer-events-none absolute inset-y-0 left-1/2 flex -translate-x-1/2 items-center justify-center">
                <div className="bg-surface-0 border-glass-border rounded-full border p-1 opacity-40 shadow-lg group-hover:opacity-100">
                  <GripVertical size={10} />
                </div>
              </div>
            </div>
          ) : null}

          <AnimatePresence initial={false} mode="popLayout">
            {showMemoryPanel ? (
              <motion.section
                key="memory-panel"
                initial={{ opacity: 0, x: 24 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 24 }}
                transition={panelTransition}
                className="h-full min-h-0 min-w-0 flex-1 overflow-hidden"
              >
                <MemoryPanel />
              </motion.section>
            ) : null}
            {showChatPanel ? (
              <motion.section
                key="chat-panel"
                initial={{ opacity: 0, x: isStackedLayout ? 0 : 24, y: isStackedLayout ? 24 : 0 }}
                animate={{ opacity: 1, x: 0, y: 0 }}
                exit={{ opacity: 0, x: isStackedLayout ? 0 : 24, y: isStackedLayout ? 24 : 0 }}
                transition={panelTransition}
                className="h-full min-h-0 min-w-0 flex-1 overflow-hidden"
              >
                <DeepSpaceChatClient
                  activeConversationId={activeNote?.id ?? null}
                  currentContent={activeNote?.content_html ?? ""}
                  onConversationRenamed={(note) => {
                    setNotes((prev) => prev.map((item) => (item.id === note.id ? note : item)));
                    setActiveNote((prev) => (prev?.id === note.id ? note : prev));
                  }}
                  onSelectNote={(noteId) => {
                    const note = notes.find((n) => n.id === noteId);
                    if (note) {
                      setActiveNote(note);
                    }
                  }}
                  onNewNote={() => {
                    createNote();
                  }}
                  onInsertLatestAnswer={insertAnswer}
                  panelMode={panelMode}
                  onSetPanelMode={setPanelMode}
                  isHistoryOpen={isHistoryOpen}
                  onSetHistoryOpen={setIsHistoryOpen}
                />
              </motion.section>
            ) : null}
          </AnimatePresence>
        </div>

      </div>
    </div>
  );
}
